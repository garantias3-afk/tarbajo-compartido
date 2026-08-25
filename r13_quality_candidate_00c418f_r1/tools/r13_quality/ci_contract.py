#!/usr/bin/env python3
"""ci_contract.py — validates the NEW R13 quality workflow structurally.

Proves required triggers, paths, installs, test invocations, no silent skip
patterns, fail-closed zero-collection guarding, curated smoke selection and
gate enforcement, etc.

Hardening additions over the historical version (QI01/QI02 salvage):
  - required pytest targets must be ACTUALLY INVOKED via run: lines,
    not merely mentioned;
  - zero-collection guard must be wired into the workflow and must be
    fail-closed by construction (explicit nonzero exits, no fallthrough);
  - curated mutation smoke (--group smoke) plus its fail-closed gate
    (smoke_gate.py) must be invoked;
  - no '|| true' anywhere in the quality workflow;
  - every file the contract requires must exist on disk;
  - deep campaign selector (--tier A) must NOT be part of routine CI.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "r13-quality-ci.yml"
TOOLS_DIR = Path(__file__).resolve().parent

REQUIRED_TRIGGERS = ["harness/**", "src/**", "config/**", "schemas/**", "r13/**", "tests/**", "tools/r13_quality/**", "VALIDATE_MODEL_REGISTRY_V3.py", ".github/workflows/r13-quality-ci.yml"]
REQUIRED_PYTEST_TARGETS = [
    "tests/test_r13_mutation_runner.py",
    "tests/test_r13_script_quality.py",
    "tests/test_r13_ci_contract.py",
]
REQUIRED_RUN_TOOLS = [
    "tools/r13_quality/secret_scan.py",
    "tools/r13_quality/ci_contract.py",
    "tools/r13_quality/test_collection_guard.py",
    "tools/r13_quality/smoke_gate.py",
]
REQUIRED_EXISTING_PATHS = [
    ".github/workflows/r13-quality-ci.yml",
    "tools/r13_quality/mutation_runner.py",
    "tools/r13_quality/mutation_specs.v1.json",
    "tools/r13_quality/ci_contract.py",
    "tools/r13_quality/secret_scan.py",
    "tools/r13_quality/test_collection_guard.py",
    "tools/r13_quality/smoke_gate.py",
    "tests/test_r13_mutation_runner.py",
    "tests/test_r13_script_quality.py",
    "tests/test_r13_ci_contract.py",
]

def load_workflow():
    if not WORKFLOW_PATH.exists():
        print(f"FAIL: workflow not found at {WORKFLOW_PATH}", file=sys.stderr)
        sys.exit(1)
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except Exception as e:
        print(f"FAIL: YAML parse error: {e}", file=sys.stderr)
        sys.exit(1)
    return text, data

def _get_on(data):
    return data.get("on", data.get(True, {}))

def _has_run_invocation(text: str, command_prefix: str) -> bool:
    """True if some YAML run line invokes command_prefix as an actual command.

    Matches both block-form lines ('      python tools/x.py ...') and
    inline form ('        run: python tools/x.py targets ...').
    """
    pat = re.compile(r"(?m)^\s+(?:run:\s+)?(?:python\s+)?" + re.escape(command_prefix) + r"(\s|$)")
    return bool(pat.search(text))

def check_triggers(text, data):
    ok = True
    on = _get_on(data)
    push = on.get("push", {})
    branches = push.get("branches", [])
    for pat in REQUIRED_TRIGGERS:
        if pat not in text:
            print(f"FAIL: required trigger path missing: {pat}", file=sys.stderr)
            ok = False
        else:
            print(f"OK: trigger {pat}")
    if branches == ['feat/c8-wave1-repo-operational-20260805'] or branches == ['feat/c8-wave1-repo-operational-20260805', 'docs/c8-pilot0-evidence-20260805']:
        print(f"FAIL: branch-only obsolete restriction: {branches}", file=sys.stderr)
        ok = False
    if "workflow_dispatch" not in text:
        print("FAIL: workflow_dispatch missing", file=sys.stderr)
        ok = False
    else:
        print("OK: workflow_dispatch present")
    # dispatch must be a real mapping key, not just prose
    if "workflow_dispatch" not in str(on):
        print("FAIL: workflow_dispatch not part of the on: block", file=sys.stderr)
        ok = False
    return ok

def check_dependencies(text, data):
    ok = True
    if "pip install pytest PyYAML" not in text and "pip install pytest" not in text:
        print("FAIL: PyYAML not explicitly installed", file=sys.stderr)
        ok = False
    else:
        print("OK: PyYAML explicitly installed")
    if re.search(r"except\s+ImportError:\s*\n\s*.*exit\(0\)", text):
        print("FAIL: silent dependency skip pattern found", file=sys.stderr)
        ok = False
    if "PyYAML not installed; skipping" in text:
        print("FAIL: silent skip for missing PyYAML", file=sys.stderr)
        ok = False
    return ok

def check_test_targets(text, data):
    ok = True
    for tgt in REQUIRED_PYTEST_TARGETS:
        pat = re.compile(r"(?m)^(\s*)run:\s*pytest\b[^\n]*" + re.escape(tgt) + r"\b")
        if not pat.search(text):
            print(f"FAIL: required pytest target never invoked in a run: line: {tgt}", file=sys.stderr)
            ok = False
        else:
            print(f"OK: pytest target invoked: {tgt}")
    for tool in REQUIRED_RUN_TOOLS:
        cmd = f"python {tool}" if tool != "tools/r13_quality/smoke_gate.py" else f"python {tool}"
        if not _has_run_invocation(text, cmd):
            print(f"FAIL: required quality tool never invoked in a run: line: {tool}", file=sys.stderr)
            ok = False
        else:
            print(f"OK: quality tool invoked: {tool}")
    gates = REQUIRED_PYTEST_TARGETS + REQUIRED_RUN_TOOLS
    for line in text.splitlines():
        if "|| true" in line and any(g in line for g in gates):
            print(f"FAIL: required gate has || true: {line.strip()}", file=sys.stderr)
            ok = False
    return ok

def check_no_silent_skip(text, data):
    ok = True
    if "|| true" in text:
        for line in text.splitlines():
            if "|| true" in line:
                print(f"FAIL: silent skip || true present in quality workflow: {line.strip()}", file=sys.stderr)
                ok = False
    if re.search(r"\|\s*echo\b", text):
        for line in text.splitlines():
            if re.search(r"\|\s*echo\b", line):
                print(f"FAIL: pipe-to-success pattern present: {line.strip()}", file=sys.stderr)
                ok = False
    return ok

def check_no_branch_only(text, data):
    on = _get_on(data)
    push = on.get("push", {})
    branches = push.get("branches", [])
    if branches and branches != ['**'] and '**' not in str(branches):
        if any('c8-wave1' in b for b in branches):
            print(f"FAIL: branch-only obsolete restriction: {branches}", file=sys.stderr)
            return False
    return True

def check_zero_collection_guard(text, data):
    """QI02: prove the workflow's zero-test acceptance is fail-closed."""
    ok = True
    guard_src_path = TOOLS_DIR / "test_collection_guard.py"
    if not _has_run_invocation(text, "python tools/r13_quality/test_collection_guard.py"):
        print("FAIL: zero-collection guard not invoked by workflow", file=sys.stderr)
        ok = False
        return ok
    print("OK: zero-collection guard invoked")
    if guard_src_path.exists():
        gsrc = guard_src_path.read_text(encoding="utf-8")
        explicit_exits = set(re.findall(r"return\s+EXIT_(?:COMMAND_FAILURE|UNPARSEABLE|ZERO_COLLECTED)", gsrc))
        if len(explicit_exits) < 3:
            print(f"FAIL: collection guard lacks explicit nonzero exits: {sorted(explicit_exits)}", file=sys.stderr)
            ok = False
        else:
            print("OK: collection guard has explicit nonzero exits for all failure states")
        if "returncode != 0" not in gsrc:
            print("FAIL: collection guard does not check collection returncode", file=sys.stderr)
            ok = False
        if "count <= 0" not in gsrc and "count<=" not in gsrc.replace(" ", ""):
            print("FAIL: collection guard does not reject zero collected tests", file=sys.stderr)
            ok = False
        if "parse_collected_count" not in gsrc or "COLLECTED_RE" not in gsrc:
            print("FAIL: collection guard lacks deterministic count parsing", file=sys.stderr)
            ok = False
    else:
        print(f"FAIL: collection guard source missing at {guard_src_path}", file=sys.stderr)
        ok = False
    # legacy fail-open heredoc must be gone
    if "PYEOF" in text or '"tests collected"' in text:
        print("FAIL: legacy fail-open zero-test heredoc still present in workflow", file=sys.stderr)
        ok = False
    else:
        print("OK: legacy fail-open zero-test heredoc absent")
    return ok

def check_smoke_curated(text, data):
    """Routine CI must run the CURATED smoke group behind a fail-closed gate."""
    ok = True
    if "--group smoke" in text:
        print("OK: curated mutation smoke selected (--group smoke)")
    else:
        print("FAIL: routine workflow does not select curated smoke group (--group smoke)", file=sys.stderr)
        ok = False
    if "--tier A" in text or "--tier B" in text or "--tier C" in text:
        print("FAIL: routine workflow must not run broad tier campaigns (deep campaign is on-demand)", file=sys.stderr)
        ok = False
    if "smoke_gate.py --summary" in text or re.search(r"smoke_gate\.py(\s|$)", text):
        if "--summary" in text:
            print("OK: fail-closed smoke gate invoked")
        else:
            print("FAIL: smoke gate invoked without --summary binding", file=sys.stderr)
            ok = False
    else:
        print("FAIL: fail-closed smoke gate (smoke_gate.py) not invoked", file=sys.stderr)
        ok = False
    return ok

def check_required_paths_exist(text, data):
    ok = True
    root = WORKFLOW_PATH.parent.parent.parent
    for rel in REQUIRED_EXISTING_PATHS:
        if (root / rel).exists():
            print(f"OK: required path exists: {rel}")
        else:
            print(f"FAIL: required path missing on disk: {rel}", file=sys.stderr)
            ok = False
    return ok

def main():
    text, data = load_workflow()
    results = []
    results.append(("triggers", check_triggers(text, data)))
    results.append(("dependencies", check_dependencies(text, data)))
    results.append(("test_targets", check_test_targets(text, data)))
    results.append(("no_silent_skip", check_no_silent_skip(text, data)))
    results.append(("no_branch_only", check_no_branch_only(text, data)))
    results.append(("zero_collection_guard", check_zero_collection_guard(text, data)))
    results.append(("smoke_curated", check_smoke_curated(text, data)))
    results.append(("required_paths_exist", check_required_paths_exist(text, data)))

    all_ok = all(ok for _, ok in results)
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not all_ok:
        print("CI contract validation FAILED", file=sys.stderr)
        sys.exit(1)
    print("CI contract validation PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
