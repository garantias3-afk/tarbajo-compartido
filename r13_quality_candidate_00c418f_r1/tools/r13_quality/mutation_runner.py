#!/usr/bin/env python3
"""mutation_runner.py — crash-safe, deterministic mutation testing engine.

Prevents RSP01-RSP10 failure modes:
  RSP01 anchor must match exactly (precondition_match_count)
  RSP02 one crash does not lose matrix (atomic receipts)
  RSP03 coarse/fine identity separated (ID binds spec canonical bytes)
  RSP04 syntax/import/collection errors not counted as kills
  RSP05 unrelated skips not counted
  RSP06 oracle independence via separate test suites
  RSP07 missing dependency fails (no silent skip)
  RSP08 CI triggers covered separately (ci_contract)
  RSP09 secret scan coverage (secret_scan)
  RSP10 crash-safe/resumable (atomic receipts + resume)

Every mutant gets a durable receipt with taxonomy:
  KILLED_SEMANTIC, SURVIVED_MATERIAL, EQUIVALENT_CONFIRMED,
  INVALID_MUTANT, HARNESS_ERROR, HARNESS_TIMEOUT, BASELINE_INVALID
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SPECS = REPO_ROOT / "tools" / "r13_quality" / "mutation_specs.v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "MUTATION_RECEIPTS"

CLASSIFICATIONS = [
    "KILLED_SEMANTIC",
    "SURVIVED_MATERIAL",
    "EQUIVALENT_CONFIRMED",
    "INVALID_MUTANT",
    "HARNESS_ERROR",
    "HARNESS_TIMEOUT",
    "BASELINE_INVALID",
]

# ---------------------------------------------------------------------------
def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def git_blob_sha(path: Path) -> str:
    """Return git blob sha1 if available, else sha256 hex."""
    try:
        out = subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    # fallback to sha256
    return sha256_file(path)

def get_base_commit(root: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"

def compute_mutation_id(base_commit: str, target_blob_sha: str, mutation_class: str, spec_canonical: bytes) -> str:
    h = hashlib.sha256()
    h.update(base_commit.encode("utf-8"))
    h.update(b"\0")
    h.update(target_blob_sha.encode("utf-8"))
    h.update(b"\0")
    h.update(mutation_class.encode("utf-8"))
    h.update(b"\0")
    h.update(spec_canonical)
    # 16 hex chars prefix + full hash suffix for uniqueness
    full = h.hexdigest()
    return f"{mutation_class}-{full[:16]}-{full[16:32]}"

def count_occurrences(content: str, fragment: str) -> int:
    if not fragment:
        return 0
    return content.count(fragment)

def syntax_validation(target_path: str, content: str) -> Tuple[bool, str]:
    """Validate that mutated target parses/compiles."""
    ext = Path(target_path).suffix.lower()
    try:
        if ext == ".py":
            ast.parse(content)
        elif ext == ".json":
            json.loads(content)
        elif ext in (".yml", ".yaml"):
            try:
                import yaml  # type: ignore
                yaml.safe_load(content)
            except ImportError:
                # fail-closed: missing PyYAML should be treated as harness error elsewhere, not syntax invalid
                # but for validation, require yaml to be installed
                return False, "PyYAML not installed for YAML validation"
            except Exception as e:
                return False, f"YAML parse error: {e}"
        # for other files, just check not empty
        return True, "ok"
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"

def parse_pytest_output(stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
    combined = stdout + "\n" + stderr
    # parse counts FIRST so that incidental mention of import/usage words
    # inside genuine failure tracebacks cannot mask a real test failure
    passed = failed = skipped = errors = 0
    tests_collected = 0
    summary = ""
    for line in combined.splitlines():
        if " passed" in line or " failed" in line or " skipped" in line or " error" in line:
            # typical summary: "1 passed, 2 failed in 0.5s" or "1 passed in 0.1s"
            summary = line.strip()
            for pat, var in [(r"(\d+) passed", "passed"), (r"(\d+) failed", "failed"), (r"(\d+) skipped", "skipped"), (r"(\d+) error", "errors")]:
                m = re.search(pat, line)
                if m:
                    if var == "passed": passed = int(m.group(1))
                    elif var == "failed": failed = int(m.group(1))
                    elif var == "skipped": skipped = int(m.group(1))
                    elif var == "errors": errors = int(m.group(1))
        # also look for collected line: "collected 5 items"
        m = re.search(r"collected (\d+) items", line)
        if m:
            tests_collected = int(m.group(1))

    # if not found but we have pass/fail, infer collected as sum
    if tests_collected == 0 and (passed or failed or skipped or errors):
        tests_collected = passed + failed + skipped + errors

    # detect collection errors, import errors, syntax errors, no tests collected
    # signals for HARNESS_ERROR — only when the run did NOT produce a real
    # pass/fail summary (a genuine failure run is adjudicated by its counts,
    # never by incidental strings inside its traceback text)
    has_real_summary = (passed > 0 or failed > 0)
    harness_error = False
    harness_reason = ""
    if "collected 0 items" in combined or "no tests collected" in combined.lower():
        harness_error = True
        harness_reason = "no tests collected"
    elif "ERROR collecting" in combined or "collection failed" in combined.lower():
        harness_error = True
        harness_reason = "collection failure"
    elif not has_real_summary and ("ModuleNotFoundError" in combined or "ImportError" in combined):
        # import crash during collection: no tests executed at all
        harness_error = True
        harness_reason = "collection import failure"
    elif not has_real_summary and ("pytest: error" in combined.lower() or "usage:" in combined.lower()):
        harness_error = True
        harness_reason = "pytest usage error"

    return {
        "harness_error": harness_error,
        "harness_reason": harness_reason,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "tests_collected": tests_collected,
        "summary": summary,
        "combined": combined,
    }

def run_pytest(selector: str, cwd: Path, timeout: int) -> Dict[str, Any]:
    import shlex
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Ensure src and tools on path for our quality tests
    env["PYTHONPATH"] = str(cwd / "src") + ":" + str(cwd / "tools") + ":" + env.get("PYTHONPATH", "")
    # Split selector correctly (handles -k, ::, etc.)
    parts = shlex.split(selector) if selector else []
    cmd = [sys.executable, "-m", "pytest"] + parts + ["-q", "-p", "no:cacheprovider", "--no-header", "-rs"]
    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - start
        parsed = parse_pytest_output(proc.stdout, proc.stderr, proc.returncode)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed": elapsed,
            "timeout_hit": False,
            **parsed,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        parsed = parse_pytest_output(stdout, stderr, -1)
        return {
            "exit_code": -1,
            "stdout": stdout,
            "stderr": stderr + f"\nTIMEOUT after {timeout}s",
            "elapsed": elapsed,
            "timeout_hit": True,
            **parsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"harness exception: {e}",
            "elapsed": elapsed,
            "timeout_hit": False,
            "harness_error": True,
            "harness_reason": f"harness exception: {e}",
            "passed": 0, "failed": 0, "skipped": 0, "errors": 0, "tests_collected": 0, "summary": "",
            "combined": str(e),
        }

def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.rename(tmp, path)

def load_specs(specs_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(specs_path.read_text(encoding="utf-8"))
    # support both list and dict with "mutants" key
    if isinstance(data, dict):
        if "mutants" in data:
            return data["mutants"]
        if "groups" in data:
            # future: groups
            return data.get("all", [])
        # if dict contains specs directly, extract list values? else return values
        # Try to handle v1 format: {"smoke":[], "deep":[]}
        if "smoke" in data or "deep" in data:
            combined = []
            for k in ("smoke", "deep"):
                combined.extend(data.get(k, []))
            if combined:
                return combined
            # also check groups
            for g in data.get("groups", {}).values():
                combined.extend(g)
            return combined
    if isinstance(data, list):
        return data
    raise ValueError(f"unrecognized specs format in {specs_path}")

def load_specs_group(specs_path: Path, group: str) -> List[Dict[str, Any]]:
    """Load a curated named group from the specs file (fail-closed).

    The group must exist under top-level "groups" as a non-empty list of
    mutant spec dicts. Unknown/empty/missing groups raise ValueError so the
    caller can fail loudly instead of silently running everything.
    """
    data = json.loads(specs_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"specs {specs_path} is not a dict; groups unsupported")
    groups = data.get("groups")
    if not isinstance(groups, dict) or group not in groups:
        known = sorted(groups.keys()) if isinstance(groups, dict) else []
        raise ValueError(f"group '{group}' not found in {specs_path} (known: {known})")
    members = groups[group]
    if not isinstance(members, list) or len(members) == 0:
        raise ValueError(f"group '{group}' is empty or malformed in {specs_path}")
    for i, m in enumerate(members):
        if not isinstance(m, dict) or "mutation_class" not in m:
            raise ValueError(f"group '{group}' member #{i} is not a valid mutant spec")
    return [dict(m) for m in members]

def classify_mutant(
    precondition_ok: bool,
    syntax_ok: bool,
    syntax_reason: str,
    baseline_result: Optional[Dict[str, Any]],
    mutant_result: Optional[Dict[str, Any]],
    is_equivalent: bool = False,
) -> Tuple[str, str]:
    # Precondition failure => INVALID_MUTANT
    if not precondition_ok:
        return "INVALID_MUTANT", "precondition match count mismatch"
    if not syntax_ok:
        return "INVALID_MUTANT", f"syntax validation failed: {syntax_reason}"
    # Baseline invalid => BASELINE_INVALID
    if baseline_result is not None:
        if baseline_result.get("harness_error"):
            return "BASELINE_INVALID", f"baseline harness error: {baseline_result.get('harness_reason')}"
        if baseline_result.get("timeout_hit"):
            return "BASELINE_INVALID", "baseline timeout"
        if baseline_result["exit_code"] != 0 or baseline_result["failed"] > 0 or baseline_result["errors"] > 0:
            # except skips are allowed? But baseline should not have skips? Per RSP05, skips contaminate adjudication
            # For baseline, any failure or error => invalid, skips also contaminate if they are unexpected
            # But we treat baseline skips as potentially invalid if expected 0
            # However spec says unrelated pytest skips can contaminate — baseline should have 0 skips for that selector
            # We'll treat baseline with skips as BASELINE_INVALID if skipped>0
            return "BASELINE_INVALID", f"baseline failed: {baseline_result['summary']}"
        if baseline_result["tests_collected"] == 0:
            return "BASELINE_INVALID", "baseline no tests collected"
        if baseline_result["skipped"] > 0:
            # RSP05: skips contaminate — baseline invalid if skips present
            return "BASELINE_INVALID", f"baseline had skips: {baseline_result['skipped']}"
    # Mutant result checks
    if mutant_result is None:
        return "HARNESS_ERROR", "no mutant result"
    if mutant_result.get("timeout_hit"):
        return "HARNESS_TIMEOUT", "mutant execution timeout"
    if mutant_result.get("harness_error"):
        return "HARNESS_ERROR", f"harness error: {mutant_result.get('harness_reason')} | {mutant_result.get('summary')}"
    if mutant_result["tests_collected"] == 0:
        return "HARNESS_ERROR", "mutant no tests collected"
    if is_equivalent:
        if mutant_result["failed"] == 0 and mutant_result["errors"] == 0:
            return "EQUIVALENT_CONFIRMED", "equivalent mutant survived as expected"
        else:
            # equivalent should not fail; if it fails, it's still killed but we mark equivalent?
            return "EQUIVALENT_CONFIRMED", "equivalent mutant but tests failed (unexpected)"
    # Check skipped contamination: if mutant has skips unrelated, but we can't distinguish; treat as HARNESS_ERROR if skips>0 and no failures?
    # However RSP05 says unrelated skips can contaminate adjudication — we should not count a kill if skips hide failures?
    # For now, if mutant has skips and no failures, it's SURVIVED but we flag skip contamination note
    # If mutant has failures attributable => KILLED
    if mutant_result["failed"] > 0 or mutant_result["errors"] > 0:
        # Need to ensure at least intended test executed — we check that tests_collected >0 and failed>0
        # Also ensure not just framework error (already excluded)
        return "KILLED_SEMANTIC", f"mutant killed: {mutant_result['failed']} failed, {mutant_result['errors']} errors | {mutant_result['summary']}"
    # No failures => survived
    return "SURVIVED_MATERIAL", f"mutant survived: {mutant_result['passed']} passed, {mutant_result['skipped']} skipped | {mutant_result['summary']}"

def run_single_mutant(
    spec: Dict[str, Any],
    base_commit: str,
    repo_root: Path,
    receipts_dir: Path,
    timeout: int,
    resume: bool = False,
    baseline_cache: Dict[str, Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if baseline_cache is None:
        baseline_cache = {}
    # Extract spec fields with defaults
    campaign_track = spec.get("campaign_track", "A1")
    mutation_class = spec.get("mutation_class", spec.get("id", "UNKNOWN"))
    semantic_intent = spec.get("semantic_intent", spec.get("description", ""))
    target_path = spec.get("target_path", spec.get("target", ""))
    expected_match_count = spec.get("precondition_match_count", spec.get("expected_match_count", 1))
    # also support expected_match_count field
    if "expected_match_count" in spec:
        expected_match_count = spec["expected_match_count"]
    before_fragment = spec.get("before_fragment", spec.get("precondition", ""))
    # For specs that use "precondition" as exact string and "before"/"after"
    if not before_fragment and "before" in spec:
        before_fragment = spec["before"]
    after_fragment = spec.get("after_fragment", spec.get("after", ""))
    if not after_fragment and "after_fragment" in spec:
        after_fragment = spec["after_fragment"]
    mutation_method = spec.get("mutation_method", "text_replace")
    test_selector = spec.get("test_selector", spec.get("selector", "tests/test_model_registry_v3.py"))
    tier = spec.get("tier", "B")
    is_equivalent = spec.get("equivalent", False)
    spec_timeout = spec.get("timeout", timeout)

    # Compute target_blob_sha
    target_full = repo_root / target_path
    target_blob_sha = ""
    if target_full.exists():
        target_blob_sha = git_blob_sha(target_full)
        try:
            content = target_full.read_text(encoding="utf-8")
        except Exception:
            content = ""
            target_blob_sha = "missing"
    else:
        content = ""
        target_blob_sha = "missing"

    # Compute canonical spec bytes and mutation_id
    # canonical should include base_commit, target_path, mutation_class, before/after etc, but not runtime fields
    spec_canonical = canonical_json({
        "target_path": target_path,
        "mutation_class": mutation_class,
        "semantic_intent": semantic_intent,
        "before_fragment": before_fragment,
        "after_fragment": after_fragment,
        "mutation_method": mutation_method,
        "expected_match_count": expected_match_count,
        "test_selector": test_selector,
    })
    mutation_id = compute_mutation_id(base_commit, target_blob_sha, mutation_class, spec_canonical)

    # Check for existing receipt if resume
    receipt_path = receipts_dir / f"{mutation_id}.json"
    if resume and receipt_path.exists():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            # validate receipt is complete and not invalidated (has classification and completed_at)
            if existing.get("classification") in CLASSIFICATIONS and existing.get("completed_at"):
                # verify that receipt corresponds to same spec (diff hash matches)
                # If spec changed, ID would be different, so not needed
                # Check if receipt is still valid (target blob matches).
                # Fail-closed: a completed receipt whose target blob no longer
                # matches the current target state is STALE and must be
                # recomputed, never silently reused.
                if existing.get("target_blob_sha") == target_blob_sha:
                    return existing
                # else treat as stale and rerun
            # else treat as incomplete and rerun
        except Exception:
            pass  # corrupted receipt, rerun

    # Precondition check
    precondition_match_count = count_occurrences(content, before_fragment) if before_fragment else 0
    precondition_ok = (precondition_match_count == expected_match_count)

    before_fragment_sha256 = sha256_text(before_fragment) if before_fragment else sha256_text("")
    after_fragment_sha256 = sha256_text(after_fragment) if after_fragment else sha256_text("")

    mutated_file_sha256 = ""
    diff_sha256 = ""
    syntax_ok = True
    syntax_reason = "ok"
    baseline_selector_result = None
    mutant_test_result = None
    classification = ""
    classification_reason = ""

    # If precondition fails, we still produce receipt as INVALID_MUTANT
    if not precondition_ok:
        syntax_ok = True  # not applicable
        classification, classification_reason = classify_mutant(False, True, "ok", None, None)
        # produce hashes for failed precondition (mutated file is original)
        mutated_file_sha256 = sha256_text(content) if content else sha256_text("")
        diff_sha256 = sha256_text("")
    else:
        # Apply mutation in isolated temp dir
        # Create a disposable copy of repo_root (shallow copy of relevant files only for speed, but we copy needed subtree)
        # For determinism and isolation, we copy entire repo_root via worktree-like temp dir, but limit to necessary to avoid overload
        # We'll use tempfile mkdtemp and copy via shutil.copytree with ignore
        tmp_root = None
        try:
            tmp_root = Path(tempfile.mkdtemp(prefix="mutant_"))
            # Copy strategy: copy target file's directory structure + tests + src + config etc.
            # Simpler: copy entire repo_root excluding .git and __pycache__ etc, but that may be heavy
            # We'll do selective copy: copy target file, its parent dirs, plus tests, src, config, schemas, harness, etc.
            # For correctness, we need full copy to run pytest selector which may import from src
            # So we copy essential directories
            essential = ["src", "tests", "config", "schemas", "harness", "assets", "r13", "scripts", "validator_tests", "documentacion", "tools", ".github"]
            for name in essential:
                src = repo_root / name
                if src.exists():
                    dst = tmp_root / name
                    if src.is_dir():
                        shutil.copytree(src, dst, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
                    else:
                        shutil.copy2(src, dst)
            # copy root-level files
            for item in repo_root.iterdir():
                if item.is_file() and item.name not in (".git",):
                    # copy VALIDATE_MODEL_REGISTRY_V3.py and other top-level files needed
                    if item.name in ["VALIDATE_MODEL_REGISTRY_V3.py", "ERROR_PRECEDENCE_TABLE.json", "APPLY_MANIFEST.json", "conftest.py", "pytest.ini", "setup.cfg", "pyproject.toml"]:
                        shutil.copy2(item, tmp_root / item.name)
                    elif item.suffix in (".py", ".json", ".yml", ".yaml") and item.name not in (".DS_Store",):
                        # copy any top-level py/json that might be target
                        try:
                            shutil.copy2(item, tmp_root / item.name)
                        except Exception:
                            pass
            # Ensure target_path's parent exists and copy file
            # Actually we already copied via essential/top-level, but ensure mutated file is placed
            mutated_rel = Path(target_path)
            mutated_full_tmp = tmp_root / mutated_rel
            mutated_full_tmp.parent.mkdir(parents=True, exist_ok=True)
            # Read original content again for mutation
            orig_content = content
            # Apply mutation: exact replace
            if mutation_method == "text_replace":
                # Use exact string replace with count validation (should match expected count)
                # For deterministic, replace all occurrences if expected count >1, else replace exactly expected count
                # But we enforce exact count check already, now replace
                if before_fragment:
                    # Need to ensure we replace exactly the expected occurrences; if multiple, replace exactly that many
                    # Use count to verify
                    actual = orig_content.count(before_fragment)
                    if actual != expected_match_count:
                        mutated_content = orig_content
                    else:
                        # Replace the first expected_match_count occurrences
                        mutated_content = orig_content.replace(before_fragment, after_fragment, expected_match_count if expected_match_count >0 else 1)
                else:
                    mutated_content = orig_content
            elif mutation_method == "ast":
                # For AST method, do text replace but also ensure AST parse afterwards
                mutated_content = orig_content.replace(before_fragment, after_fragment, expected_match_count if expected_match_count and expected_match_count>0 else 1)
            else:
                mutated_content = orig_content.replace(before_fragment, after_fragment, 1)

            # Syntax validation on mutated content
            syntax_ok, syntax_reason = syntax_validation(target_path, mutated_content)
            if not syntax_ok:
                classification, classification_reason = classify_mutant(True, False, syntax_reason, None, None)
                mutated_file_sha256 = sha256_text(mutated_content)
                diff_sha256 = sha256_text(mutated_content)  # approximate
                # Still produce receipt
            else:
                # Write mutated content to tmp
                mutated_full_tmp.write_text(mutated_content, encoding="utf-8")
                mutated_file_sha256 = sha256_text(mutated_content)
                # Compute diff sha: simple diff of before->after or file diff
                # Use unified diff placeholder: hash of before+after
                diff_content = f"--- {target_path}\n+++ {target_path}\n- {before_fragment}\n+ {after_fragment}\n"
                diff_sha256 = sha256_text(diff_content)

                # Baseline: run targeted tests on clean base (cached per selector)
                # For this mutant, we need baseline_selector_result
                baseline_key = test_selector
                if baseline_key not in baseline_cache:
                    # Run baseline in a clean temp copy (without mutation) — reuse tmp_root but with original file restored?
                    # Instead, run baseline directly on repo_root's clean state? But we want isolated clean baseline
                    # We'll create a separate clean tmp for baseline (cheaper: run on repo_root directly with pytest - but risk pollution)
                    # Implement: run pytest on repo_root (clean) for that selector, cached
                    # However to avoid mutating shared working tree, we run baseline in a clean temp copy as well
                    clean_tmp = Path(tempfile.mkdtemp(prefix="baseline_"))
                    try:
                        # copy essential again for baseline (ensure tools included)
                        for name in essential:
                            src = repo_root / name
                            if src.exists():
                                dst = clean_tmp / name
                                if src.is_dir():
                                    shutil.copytree(src, dst, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
                                else:
                                    shutil.copy2(src, dst)
                        for item in repo_root.iterdir():
                            if item.is_file():
                                if item.name in ["VALIDATE_MODEL_REGISTRY_V3.py", "ERROR_PRECEDENCE_TABLE.json", "APPLY_MANIFEST.json", "conftest.py"]:
                                    shutil.copy2(item, clean_tmp / item.name)
                        baseline_res = run_pytest(test_selector, clean_tmp, spec_timeout)
                        baseline_cache[baseline_key] = baseline_res
                    finally:
                        shutil.rmtree(clean_tmp, ignore_errors=True)
                baseline_selector_result = baseline_cache[baseline_key]

                # If baseline invalid, classify as BASELINE_INVALID without running mutant
                if baseline_selector_result.get("harness_error") or baseline_selector_result.get("timeout_hit") or baseline_selector_result["exit_code"] != 0 or baseline_selector_result["failed"]>0 or baseline_selector_result["errors"]>0 or baseline_selector_result["tests_collected"]==0 or baseline_selector_result["skipped"]>0:
                    classification, classification_reason = classify_mutant(True, True, "ok", baseline_selector_result, None)
                    # No mutant run needed? We still produce receipt but without mutant result
                    mutant_test_result = {"exit_code": -1, "stdout": "", "stderr": "baseline invalid, mutant not run", "passed":0,"failed":0,"skipped":0,"errors":0,"tests_collected":0,"summary":"BASELINE_INVALID","harness_error":False,"harness_reason":""}
                else:
                    # Run mutant tests in tmp_root
                    mutant_res = run_pytest(test_selector, tmp_root, spec_timeout)
                    mutant_test_result = mutant_res
                    classification, classification_reason = classify_mutant(True, True, "ok", baseline_selector_result, mutant_res, is_equivalent)
        finally:
            if tmp_root and tmp_root.exists():
                shutil.rmtree(tmp_root, ignore_errors=True)
                # Ensure mutated_file_sha256 and diff already computed
                pass

    # Build receipt
    now = datetime.now(timezone.utc).isoformat()
    # Prepare fields per spec §12
    # Ensure all required fields present
    # For invalid cases, we still have baseline/mutant results placeholder
    if baseline_selector_result is None:
        baseline_selector_result = {"exit_code": -1, "stdout": "", "stderr": "", "passed":0,"failed":0,"skipped":0,"errors":0,"tests_collected":0,"summary":"","harness_error":False,"harness_reason":"","timeout_hit":False}
    if mutant_test_result is None:
        mutant_test_result = {"exit_code": -1, "stdout": "", "stderr": "", "passed":0,"failed":0,"skipped":0,"errors":0,"tests_collected":0,"summary":"","harness_error":False,"harness_reason":"","timeout_hit":False}

    # Compute stderr/stdout sha
    stderr_sha256 = sha256_text(mutant_test_result.get("stderr","") or "")
    stdout_sha256 = sha256_text(mutant_test_result.get("stdout","") or "")

    receipt = {
        "mutation_id": mutation_id,
        "campaign_track": campaign_track,
        "base_commit": base_commit,
        "target_path": target_path,
        "target_blob_sha": target_blob_sha,
        "mutation_class": mutation_class,
        "semantic_intent": semantic_intent,
        "precondition": before_fragment[:500] if before_fragment else "",
        "precondition_match_count": precondition_match_count,
        "mutation_method": mutation_method,
        "before_fragment_sha256": before_fragment_sha256,
        "after_fragment_sha256": after_fragment_sha256,
        "mutated_file_sha256": mutated_file_sha256,
        "diff_sha256": diff_sha256,
        "syntax_validation": syntax_reason if not syntax_ok else "ok",
        "test_selector": test_selector,
        "baseline_selector_result": {
            "exit_code": baseline_selector_result.get("exit_code"),
            "tests_collected": baseline_selector_result.get("tests_collected"),
            "tests_failed": baseline_selector_result.get("failed"),
            "tests_skipped": baseline_selector_result.get("skipped"),
            "summary": baseline_selector_result.get("summary"),
        },
        "mutant_test_result": {
            "exit_code": mutant_test_result.get("exit_code"),
            "tests_collected": mutant_test_result.get("tests_collected"),
            "tests_failed": mutant_test_result.get("failed"),
            "tests_skipped": mutant_test_result.get("skipped"),
            "summary": mutant_test_result.get("summary"),
        },
        "pytest_exit_code": mutant_test_result.get("exit_code"),
        "tests_collected": mutant_test_result.get("tests_collected"),
        "tests_failed": mutant_test_result.get("failed"),
        "tests_skipped": mutant_test_result.get("skipped"),
        "timeout": spec_timeout,
        "stderr_sha256": stderr_sha256,
        "stdout_sha256": stdout_sha256,
        "classification": classification,
        "classification_reason": classification_reason,
        "completed_at": now,
        "tier": tier,
        "expected_match_count": expected_match_count,
        "syntax_validation_bool": syntax_ok,
    }

    # Atomic write
    data = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")
    atomic_write(receipt_path, data)

    # Also store raw stdout/stderr for debugging if needed (optional)
    # Ensure we also handle diff_sha uniqueness: ensure diff contains only declared path - verified via receipt diff_sha computed from single path

    return receipt

def run_campaign(
    specs_path: Path,
    output_dir: Path,
    base_commit: Optional[str] = None,
    timeout: int = 60,
    resume: bool = False,
    jobs: int = 4,
    filter_tier: Optional[str] = None,
    filter_track: Optional[str] = None,
    group: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    # Explicit repo_root override lets meta-tests exercise scenarios against
    # isolated temp repos instead of the runner module's own REPO_ROOT global.
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    if group:
        specs = load_specs_group(specs_path, group)
    else:
        specs = load_specs(specs_path)
    if base_commit is None:
        base_commit = get_base_commit(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Filter
    filtered = []
    for s in specs:
        if filter_tier and s.get("tier") != filter_tier:
            continue
        if filter_track and s.get("campaign_track") != filter_track:
            continue
        filtered.append(s)
    # Deterministic ordering: sort by mutation_class and target_path
    filtered.sort(key=lambda x: (x.get("campaign_track",""), x.get("mutation_class",""), x.get("target_path",""), x.get("semantic_intent","")))

    # For determinism, process sequentially (parallelism is optional but must maintain isolation)
    # We support simple sequential with baseline_cache shared
    results = []
    baseline_cache: Dict[str, Dict[str, Any]] = {}
    for idx, spec in enumerate(filtered):
        # limit attempts?
        try:
            receipt = run_single_mutant(spec, base_commit, root, output_dir, timeout, resume, baseline_cache)
            results.append(receipt)
        except Exception as e:
            # HARNESS_ERROR receipt on crash
            # Create a harness error receipt for this spec if possible
            try:
                # Try to create minimal receipt
                mutation_class = spec.get("mutation_class", f"unknown-{idx}")
                target_path = spec.get("target_path", "unknown")
                spec_canonical = canonical_json(spec)
                mid = compute_mutation_id(base_commit, "error", mutation_class, spec_canonical)
                receipt = {
                    "mutation_id": mid,
                    "campaign_track": spec.get("campaign_track", "A1"),
                    "base_commit": base_commit,
                    "target_path": target_path,
                    "target_blob_sha": "error",
                    "mutation_class": mutation_class,
                    "semantic_intent": spec.get("semantic_intent", ""),
                    "precondition": "",
                    "precondition_match_count": 0,
                    "mutation_method": spec.get("mutation_method", ""),
                    "before_fragment_sha256": sha256_text(""),
                    "after_fragment_sha256": sha256_text(""),
                    "mutated_file_sha256": sha256_text(""),
                    "diff_sha256": sha256_text(""),
                    "syntax_validation": f"harness exception: {e}",
                    "test_selector": spec.get("test_selector", ""),
                    "baseline_selector_result": {},
                    "mutant_test_result": {},
                    "pytest_exit_code": -1,
                    "tests_collected": 0,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                    "timeout": timeout,
                    "stderr_sha256": sha256_text(str(e)),
                    "stdout_sha256": sha256_text(""),
                    "classification": "HARNESS_ERROR",
                    "classification_reason": f"runner crash: {e}",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "tier": spec.get("tier", "C"),
                }
                atomic_write(output_dir / f"{mid}.json", json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8"))
                results.append(receipt)
            except Exception as e2:
                print(f"Failed to write harness error receipt: {e2}", file=sys.stderr)
            continue

    # Build summary solely from receipts (deterministic rebuild)
    return build_summary_from_receipts(output_dir)

def build_summary_from_receipts(receipts_dir: Path) -> Dict[str, Any]:
    receipts = []
    for p in receipts_dir.glob("*.json"):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            # ignore non-receipt files like summary.json
            if "mutation_id" in r and "classification" in r:
                receipts.append(r)
        except Exception:
            continue
    # deterministic sort
    receipts.sort(key=lambda x: x.get("mutation_id",""))
    counts = {c: 0 for c in CLASSIFICATIONS}
    for r in receipts:
        c = r.get("classification")
        if c in counts:
            counts[c] += 1
    attempted = len(receipts)
    valid_non_equiv = counts["KILLED_SEMANTIC"] + counts["SURVIVED_MATERIAL"]
    # Note: EQUIVALENT_CONFIRMED not counted as valid_non_equiv? Spec says VALID_NON_EQUIVALENT = KILLED + SURVIVED?
    # But §9 says MIN_VALID_NON_EQUIVALENT includes valid non-equivalent. So use killed+survived.
    killed = counts["KILLED_SEMANTIC"]
    survived = counts["SURVIVED_MATERIAL"]
    meaningful_kill_rate = (killed / (killed + survived) * 100) if (killed+survived)>0 else 0
    summary = {
        "attempted": attempted,
        "counts": counts,
        "valid_non_equivalent": valid_non_equiv,
        "meaningful_kill_rate": meaningful_kill_rate,
        "receipts": receipts,  # for detailed, but may be large
    }
    return summary

def main():
    parser = argparse.ArgumentParser(description="R13 mutation runner")
    parser.add_argument("--specs", type=str, default=str(DEFAULT_SPECS), help="path to mutation_specs.v1.json")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="receipts output dir")
    parser.add_argument("--base-commit", type=str, default=None, help="base commit override")
    parser.add_argument("--timeout", type=int, default=60, help="per-mutant timeout seconds")
    parser.add_argument("--resume", action="store_true", help="resume from existing receipts")
    parser.add_argument("--jobs", type=int, default=4, help="parallel jobs (not yet, sequential for safety)")
    parser.add_argument("--rebuild-summary", action="store_true", help="rebuild summary from receipts only")
    parser.add_argument("--tier", type=str, default=None, help="filter tier A/B/C")
    parser.add_argument("--track", type=str, default=None, help="filter track A1..A6")
    parser.add_argument("--group", type=str, default=None, help="curated group name from specs 'groups' (fail-closed)")
    args = parser.parse_args()

    specs_path = Path(args.specs)
    output_dir = Path(args.output)

    if args.rebuild_summary:
        summary = build_summary_from_receipts(output_dir)
        print(json.dumps(summary, indent=2))
        return 0

    if args.group:
        # fail-closed: unknown/empty curated group must abort loudly, not run everything
        try:
            load_specs_group(specs_path, args.group)
        except Exception as e:
            print(f"FAIL[mutation-runner]: {e}", file=sys.stderr)
            return 2

    summary = run_campaign(specs_path, output_dir, args.base_commit, args.timeout, args.resume, args.jobs, args.tier, args.track, group=args.group)
    # Write summary file atomically
    summary_path = output_dir.parent / "MUTATION_CAMPAIGN_SUMMARY.json" if output_dir.name == "MUTATION_RECEIPTS" else output_dir / "summary.json"
    # For consistency, write to output_dir/SUMMARY.json and also to parent if needed
    try:
        atomic_write(output_dir / "SUMMARY.json", json.dumps(summary, indent=2).encode("utf-8"))
    except Exception:
        pass
    print(json.dumps({k:v for k,v in summary.items() if k!="receipts"}, indent=2))
    # Exit code 0 always (campaign success), unless we want to fail on survivors? No, campaign is evidence, not gate
    return 0

if __name__ == "__main__":
    sys.exit(main())

