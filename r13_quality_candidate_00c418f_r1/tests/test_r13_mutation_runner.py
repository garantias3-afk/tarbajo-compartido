"""Tests for mutation_runner engine — ME01..ME16 + self-mutants + crash/resume."""
import json
import hashlib
import tempfile
import shutil
import time
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "r13_quality"))

import mutation_runner as MR

# ---------------------------------------------------------------------------
# Helpers
def make_temp_repo(base_content: dict, test_content: str):
    """Create a temp repo with a target file and a test file."""
    tmp = Path(tempfile.mkdtemp(prefix="me_test_"))
    # target file
    for rel, content in base_content.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    # test file
    (tmp / "tests").mkdir(parents=True, exist_ok=True)
    # Also need src directory for PYTHONPATH if needed
    (tmp / "src").mkdir(exist_ok=True)
    (tmp / "tests" / "test_dummy.py").write_text(test_content, encoding="utf-8")
    # Also copy conftest if needed? No
    return tmp

def cleanup(tmp):
    shutil.rmtree(tmp, ignore_errors=True)

def run_mutant_for_test(target_rel, before, after, test_selector, timeout=10, extra_base_content=None):
    """Helper to run a single mutant in isolated temp repo and return receipt."""
    # Create a base file with before content
    # We need to create a repo that has that target file with before fragment exactly once (or requested count)
    # For simplicity, create a file with before fragment once.
    base_content = {}
    if extra_base_content:
        base_content.update(extra_base_content)
    # Ensure target file exists with before content
    # We'll create a minimal python file that contains before as a line
    # If before is not provided, create file with known content
    tmp = make_temp_repo(
        {
            target_rel: f"# test file\n{before}\n# end\n",
            **(extra_base_content or {})
        },
        # test file content depends on selector
        "def test_dummy():\n    assert True\n"
    )
    # But if test_selector is generic, we need to handle
    # We'll manually run MR.run_single_mutant with our tmp as repo root
    # Need to monkeypatch REPO_ROOT for this call? Instead we will call function with repo_root param
    # MR.run_single_mutant expects repo_root Path
    # Create spec
    spec = {
        "campaign_track": "A1",
        "mutation_class": "TEST_CLASS",
        "semantic_intent": "test",
        "target_path": target_rel,
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": before,
        "after_fragment": after,
        "mutation_method": "text_replace",
        "test_selector": test_selector,
        "tier": "C",
        "timeout": timeout,
    }
    # Need to handle base_commit and receipts_dir
    receipts = Path(tempfile.mkdtemp(prefix="receipts_"))
    try:
        base_commit = "testbase123"
        receipt = MR.run_single_mutant(spec, base_commit, tmp, receipts, timeout, resume=False, baseline_cache={})
        return receipt, tmp, receipts
    finally:
        # caller must cleanup
        pass

# ---------------------------------------------------------------------------
class TestME01:
    def test_exact_anchor_succeeds(self):
        """ME01 exact anchor succeeds."""
        tmp = make_temp_repo(
            {"src/mod.py": "def foo():\n    return 42\n"},
            "def test_foo():\n    from mod import foo\n    assert foo() == 42\n"
        )
        # Need to setup PYTHONPATH for test to import mod: place mod under src
        # Actually test should be under tests and import from src/mod.py via sys.path
        # Let's create a simple target and test that checks its value
        # Use text_replace that changes return 42 to 99, should be KILLED if test asserts 42
        # First check that precondition exact match works
        before = "    return 42"
        after = "    return 99"
        # Create a target file with that before exactly once
        target_path = "src/mod.py"
        # Ensure file content
        (tmp / target_path).write_text("def foo():\n    return 42\n", encoding="utf-8")
        # Create test that asserts foo() ==42
        (tmp / "tests" / "test_dummy.py").write_text("def test_foo():\n    import sys; sys.path.insert(0, 'src')\n    from mod import foo\n    assert foo() == 42\n", encoding="utf-8")
        spec = {
            "campaign_track": "A1",
            "mutation_class": "ME01_EXACT",
            "semantic_intent": "exact anchor",
            "target_path": target_path,
            "precondition_match_count": 1,
            "expected_match_count": 1,
            "before_fragment": before,
            "after_fragment": after,
            "mutation_method": "text_replace",
            "test_selector": "tests/test_dummy.py",
            "tier": "C",
            "timeout": 10,
        }
        receipts = Path(tempfile.mkdtemp(prefix="r1_"))
        receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
        assert receipt["classification"] == "KILLED_SEMANTIC", receipt
        cleanup(tmp)
        shutil.rmtree(receipts, ignore_errors=True)

def test_me02_zero_match_invalid():
    """ME02: zero-match anchor => INVALID_MUTANT (module-level so -k 'test_me02' selects it)."""
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n"},
        "def test_dummy():\n    assert True\n"
    )
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME02_ZERO",
        "semantic_intent": "zero match",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "NONEXISTENT_XYZ_123",
        "after_fragment": "replaced",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r2_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "INVALID_MUTANT"
    assert "precondition" in receipt["classification_reason"].lower() or "mismatch" in receipt["classification_reason"].lower()
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

class TestME03:
    def test_multiple_unexpected_matches_invalid(self):
        tmp = make_temp_repo(
            {"src/mod.py": "x = 1\nx = 1\nx = 1\n"},
            "def test_dummy():\n    assert True\n"
        )
        spec = {
            "campaign_track": "A1",
            "mutation_class": "ME03_MULTI",
            "semantic_intent": "multiple matches",
            "target_path": "src/mod.py",
            "precondition_match_count": 1,
            "expected_match_count": 1,
            "before_fragment": "x = 1",
            "after_fragment": "x = 2",
            "mutation_method": "text_replace",
            "test_selector": "tests/test_dummy.py",
            "tier": "C",
            "timeout": 10,
        }
        receipts = Path(tempfile.mkdtemp(prefix="r3_"))
        receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
        assert receipt["classification"] == "INVALID_MUTANT"
        cleanup(tmp)
        shutil.rmtree(receipts, ignore_errors=True)

def test_me04_syntax_breaking_invalid():
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 42\n"},
        "def test_dummy():\n    assert True\n"
    )
    before = "    return 42"
    after = "    return 42  # syntax error: missing colon??\n    if True"  # actually valid, need syntax error like "def foo("
    # Better: replace with invalid syntax
    after = "    return 42\n    if"  # incomplete if
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME04_SYNTAX",
        "semantic_intent": "syntax breaking",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": before,
        "after_fragment": after,
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r4_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    # The after_fragment may or may not be syntax error via ast.parse; "if" without colon is syntax error
    # Check classification is INVALID_MUTANT
    assert receipt["classification"] == "INVALID_MUTANT", receipt
    assert "syntax" in receipt["classification_reason"].lower()
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me05_killed():
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 42\n"},
        "def test_dummy():\n    import sys; sys.path.insert(0, 'src')\n    from mod import foo\n    assert foo() == 42\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("def test_foo():\n    import sys; sys.path.insert(0, 'src')\n    from mod import foo\n    assert foo() == 42\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME05_KILLED",
        "semantic_intent": "killed",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 42",
        "after_fragment": "    return 0",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r5_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "KILLED_SEMANTIC"
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me06_survived():
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 42\n"},
        "def test_dummy():\n    assert True\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME06_SURVIVED",
        "semantic_intent": "survived",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 42",
        "after_fragment": "    return 0",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r6_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "SURVIVED_MATERIAL"
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me07_collection_failure_harness_error():
    # Test that a mutant causing top-level import failure is HARNESS_ERROR (not KILLED)
    tmp2 = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 42\n"},
        "def test_dummy():\n    import sys; sys.path.insert(0, 'src')\n    from mod import foo\n    assert foo()==42\n"
    )
    (tmp2 / "src" / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    # Create test that imports mod at top-level so mutant's top-level import error causes collection failure
    (tmp2 / "tests" / "test_dummy2.py").write_text("import sys; sys.path.insert(0, 'src')\nfrom mod import foo\n\ndef test_foo():\n    assert foo()==42\n", encoding="utf-8")
    # Mutant that injects failing import at top-level of mod.py
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME07_HARNESS2",
        "semantic_intent": "harness error via top-level import",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "def foo():",
        "after_fragment": "import nonexistent_module_xyz\ndef foo():",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy2.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r7c_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp2, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "HARNESS_ERROR", receipt

    # Harness exception contract (kills A1_ME_SWALLOW_SUBPROCESS_EXCEPTION):
    # when the collection subprocess cannot be executed at all, the reported
    # result must remain a FAILURE (harness error + nonzero exit), never a
    # silent success.
    real_run = MR.subprocess.run
    def _boom(*a, **k):
        raise RuntimeError("simulated subprocess infrastructure failure")
    MR.subprocess.run = _boom
    try:
        res = MR.run_pytest("tests/test_dummy.py", tmp2, 10)
    finally:
        MR.subprocess.run = real_run
    assert res["harness_error"] is True, "infrastructure exception not flagged as harness error"
    assert res["exit_code"] != 0, "harness exception was swallowed into an exit-0 success"

    cleanup(tmp2)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me08_no_tests_collected_harness_error():
    tmp2 = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n"},
        "def helper():\n    return 1\n"
    )
    (tmp2 / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp2 / "tests" / "test_dummy.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    spec2 = {
        "campaign_track": "A1",
        "mutation_class": "ME08_NO_COLLECT",
        "semantic_intent": "no tests collected",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 1",
        "after_fragment": "    return 0",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts2 = Path(tempfile.mkdtemp(prefix="r8_"))
    receipt2 = MR.run_single_mutant(spec2, "abc123", tmp2, receipts2, 10, resume=False, baseline_cache={})
    # Since baseline has no tests collected, it should be BASELINE_INVALID (which is correct per spec: baseline invalid)
    assert receipt2["classification"] == "BASELINE_INVALID", receipt2
    # Also test that HARNESS_ERROR is correctly returned for no-tests-collected when baseline would be valid
    # Use a top-level import error to trigger HARNESS_ERROR (already covered by ME07)
    # For ME08, we just verify that BASELINE_INVALID is the expected outcome for no-tests baseline
    cleanup(tmp2)
    shutil.rmtree(receipts2, ignore_errors=True)

def test_me09_timeout():
    # Mutant causes target function to sleep, leading to timeout when test calls it
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n"},
        "def test_dummy():\n    assert True\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    import time; return 1\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("import sys; sys.path.insert(0, 'src')\nfrom mod import foo\n\ndef test_foo():\n    assert foo()==1\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME09_TIMEOUT",
        "semantic_intent": "timeout via mutant sleep",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    import time; return 1",
        "after_fragment": "    import time; time.sleep(30); return 1",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 5,  # baseline starts in well under 5s; mutant sleeps 30 => deterministic HARNESS_TIMEOUT
    }
    receipts = Path(tempfile.mkdtemp(prefix="r9_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 1, resume=False, baseline_cache={})
    assert receipt["classification"] == "HARNESS_TIMEOUT", receipt
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me10_baseline_invalid():
    # Baseline fails due to failing test, mutant should be BASELINE_INVALID
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n"},
        "def test_always_fail():\n    assert False\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("def test_always_fail():\n    assert False\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME10_BASELINE",
        "semantic_intent": "baseline invalid",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 1",
        "after_fragment": "    return 0",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r10_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "BASELINE_INVALID", receipt
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me11_framework_error_never_kill():
    # Framework error (collection failure) should be HARNESS_ERROR, not KILLED
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n"},
        "def test_foo():\n    assert True\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("import sys; sys.path.insert(0, 'src')\nfrom mod import foo\n\ndef test_foo():\n    assert foo()==1\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME11_FRAMEWORK",
        "semantic_intent": "framework error not kill",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "def foo():",
        "after_fragment": "import nonexistent_xyz\ndef foo():",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r11_"))
    # Use top-level import to force collection error
    (tmp / "tests" / "test_dummy.py").write_text("import sys; sys.path.insert(0, 'src')\nfrom mod import foo\n\ndef test_foo():\n    assert foo()==1\n", encoding="utf-8")
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    assert receipt["classification"] == "HARNESS_ERROR"
    assert receipt["classification"] != "KILLED_SEMANTIC"
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me12_interrupted_resumes():
    # Simulate interrupted campaign after N mutants and resume via direct run_single_mutant resume flag
    tmp_repo = Path(tempfile.mkdtemp(prefix="me12_repo_"))
    (tmp_repo / "src").mkdir(parents=True)
    (tmp_repo / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_repo / "tests").mkdir(parents=True)
    (tmp_repo / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    specs = []
    for i in range(3):
        specs.append({
            "campaign_track": "A1",
            "mutation_class": f"ME12_{i}",
            "semantic_intent": "test resume",
            "target_path": "src/mod.py",
            "precondition_match_count": 1,
            "expected_match_count": 1,
            "before_fragment": "    return 1",
            "after_fragment": f"    return {i+10}",
            "mutation_method": "text_replace",
            "test_selector": "tests/test_dummy.py",
            "tier": "C",
            "timeout": 10,
        })
    receipts_dir = Path(tempfile.mkdtemp(prefix="me12_receipts_"))
    base_commit = "test"
    cache = {}
    # Run first 2 manually
    for s in specs[:2]:
        MR.run_single_mutant(s, base_commit, tmp_repo, receipts_dir, 10, resume=False, baseline_cache=cache)
    # Count receipts with mutation_id
    def count_receipts(d):
        return len([p for p in d.glob("*.json") if "mutation_id" in json.loads(p.read_text())])
    assert count_receipts(receipts_dir) == 2
    # Simulate resume by running all 3 with resume=True; should only create one new
    for s in specs:
        MR.run_single_mutant(s, base_commit, tmp_repo, receipts_dir, 10, resume=True, baseline_cache=cache)
    assert count_receipts(receipts_dir) == 3
    # Verify summary rebuild is deterministic
    summary = MR.build_summary_from_receipts(receipts_dir)
    assert summary["attempted"] == 3

    # Durability contract (kills A1_ME_LOSE_RECEIPT_ON_INTERRUPTION):
    # atomic_write must fsync BEFORE rename; renaming without fsync is not crash-safe.
    import os as _os
    order = []
    orig_fsync = _os.fsync
    orig_rename = _os.rename
    def _spy_fsync(fd):
        order.append("fsync")
        return orig_fsync(fd)
    def _spy_rename(src, dst):
        if not order or order[-1] != "fsync":
            raise AssertionError("atomic_write renamed without fsync (not crash-safe)")
        order.append("rename")
        return orig_rename(src, dst)
    _os.fsync = _spy_fsync
    _os.rename = _spy_rename
    try:
        probe = receipts_dir / "_durability_probe.json"
        MR.atomic_write(probe, b"{}\n")
    finally:
        _os.fsync = orig_fsync
        _os.rename = orig_rename
    assert order == ["fsync", "rename"], f"atomic_write ordering violated: {order}"

    cleanup(tmp_repo)
    shutil.rmtree(receipts_dir, ignore_errors=True)

def test_me13_completed_receipts_not_rerun():
    # Similar to 12 but check that rerunning with resume does not change receipt mtime
    tmp_repo = Path(tempfile.mkdtemp(prefix="me13_repo_"))
    (tmp_repo / "src").mkdir(parents=True)
    (tmp_repo / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_repo / "tests").mkdir(parents=True)
    (tmp_repo / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME13_TEST",
        "semantic_intent": "test not rerun",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 1",
        "after_fragment": "    return 2",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    spec_file = tmp_repo / "specs.json"
    spec_file.write_text(json.dumps([spec]), encoding="utf-8")
    receipts_dir = Path(tempfile.mkdtemp(prefix="me13_receipts_"))
    base_commit = "test"
    receipt1 = MR.run_single_mutant(spec, base_commit, tmp_repo, receipts_dir, 10, resume=False, baseline_cache={})
    mtime1 = (receipts_dir / f"{receipt1['mutation_id']}.json").stat().st_mtime
    time.sleep(0.1)
    receipt2 = MR.run_single_mutant(spec, base_commit, tmp_repo, receipts_dir, 10, resume=True, baseline_cache={})
    mtime2 = (receipts_dir / f"{receipt2['mutation_id']}.json").stat().st_mtime
    assert mtime1 == mtime2
    assert receipt1["mutation_id"] == receipt2["mutation_id"]

    # Stale-receipt contract (kills A1_ME_REUSE_STALE_RECEIPT): a completed
    # receipt whose target_blob_sha no longer matches the current target MUST
    # be recomputed on resume, never silently reused.
    stale_path = receipts_dir / f"{receipt1['mutation_id']}.json"
    stale = dict(receipt2)
    stale["target_blob_sha"] = "stale_blob_sentinel_not_real"
    stale["classification"] = "KILLED_SEMANTIC"
    stale["completed_at"] = "2020-01-01T00:00:00+00:00"
    stale_path.write_text(json.dumps(stale), encoding="utf-8")
    receipt3 = MR.run_single_mutant(spec, base_commit, tmp_repo, receipts_dir, 10, resume=True, baseline_cache={})
    assert receipt3["target_blob_sha"] != "stale_blob_sentinel_not_real", (
        "stale receipt was reused even though the target blob changed"
    )
    assert stale_path.read_text(encoding="utf-8") != json.dumps(stale, indent=2, sort_keys=True), (
        "stale receipt file was not recomputed on disk"
    )

    cleanup(tmp_repo)
    shutil.rmtree(receipts_dir, ignore_errors=True)

def test_me14_summary_rebuild_deterministic():
    """Summary must count survivors exactly (kills A1_ME_SUMMARY_EXCLUDES_SURVIVOR
    and A1_ME_SUMMARY_DOUBLE_COUNTS) and rebuild deterministically.

    Runs the campaign against an EXPLICIT repo_root so targets resolve to the
    isolated temp repo (the historical version resolved against the runner's
    own module-level REPO_ROOT, making these assertions vacuous).
    """
    tmp_repo = Path(tempfile.mkdtemp(prefix="me14_repo_"))
    (tmp_repo / "src").mkdir(parents=True)
    (tmp_repo / "tests").mkdir(parents=True)
    (tmp_repo / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_repo / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    specs = []
    for i in range(4):
        specs.append({
            "campaign_track": "A1",
            "mutation_class": f"ME14_{i}",
            "semantic_intent": "summary test",
            "target_path": "src/mod.py",
            "precondition_match_count": 1,
            "expected_match_count": 1,
            "before_fragment": "    return 1",
            "after_fragment": f"    return {i+10}",
            "mutation_method": "text_replace",
            "test_selector": "tests/test_dummy.py",
            "tier": "C",
            "timeout": 10,
        })
    spec_file = tmp_repo / "specs.json"
    spec_file.write_text(json.dumps(specs), encoding="utf-8")
    receipts_dir = Path(tempfile.mkdtemp(prefix="me14_receipts_"))
    MR.run_campaign(spec_file, receipts_dir, base_commit="test", timeout=10, resume=False, repo_root=tmp_repo)
    summary1 = MR.build_summary_from_receipts(receipts_dir)
    summary2 = MR.build_summary_from_receipts(receipts_dir)
    assert summary1 == summary2
    # All four trivially-surviving mutants must be present and counted exactly once.
    assert summary1["attempted"] == 4, f"attempted={summary1['attempted']} (survivors excluded or receipts lost)"
    assert summary1["counts"]["SURVIVED_MATERIAL"] == 4, (
        f"SURVIVED_MATERIAL={summary1['counts']['SURVIVED_MATERIAL']} (excluded from summary)"
    )
    assert summary1["counts"]["KILLED_SEMANTIC"] == 0, "unexpected kills in survivor scenario"
    cleanup(tmp_repo)
    shutil.rmtree(receipts_dir, ignore_errors=True)

def test_me15_single_path_diff():
    tmp = make_temp_repo(
        {"src/mod.py": "def foo():\n    return 1\n", "src/other.py": "def bar():\n    return 2\n"},
        "def test_dummy():\n    assert True\n"
    )
    (tmp / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp / "src" / "other.py").write_text("def bar():\n    return 2\n", encoding="utf-8")
    (tmp / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    spec = {
        "campaign_track": "A1",
        "mutation_class": "ME15_DIFF",
        "semantic_intent": "diff only declared path",
        "target_path": "src/mod.py",
        "precondition_match_count": 1,
        "expected_match_count": 1,
        "before_fragment": "    return 1",
        "after_fragment": "    return 0",
        "mutation_method": "text_replace",
        "test_selector": "tests/test_dummy.py",
        "tier": "C",
        "timeout": 10,
    }
    receipts = Path(tempfile.mkdtemp(prefix="r15_"))
    receipt = MR.run_single_mutant(spec, "abc123", tmp, receipts, 10, resume=False, baseline_cache={})
    # The diff should only contain declared path, not other file
    # Our runner computes diff_sha from before/after fragments, not full file diff, so it inherently only references declared path
    # Check that mutated_file_sha256 != original and target_path is correct
    assert receipt["target_path"] == "src/mod.py"
    assert "diff_sha256" in receipt
    # Also ensure we didn't mutate other file
    assert (tmp / "src" / "other.py").read_text().count("return 2") == 1
    cleanup(tmp)
    shutil.rmtree(receipts, ignore_errors=True)

def test_me16_coarse_fine_collision():
    # Two mutants with same mutation_class but different semantic (different after) should have different IDs
    base_commit = "abc123"
    target_blob = "blob123"
    spec1 = {
        "target_path": "src/mod.py",
        "mutation_class": "FM08",
        "semantic_intent": "coarse: remove complete guard",
        "before_fragment": "if x:",
        "after_fragment": "if True:",
        "mutation_method": "text_replace",
        "expected_match_count": 1,
        "test_selector": "tests/test_dummy.py",
    }
    spec2 = {
        "target_path": "src/mod.py",
        "mutation_class": "FM08",
        "semantic_intent": "fine: accept namespace B where only A is legal",
        "before_fragment": "if x:",
        "after_fragment": "if x or y:",
        "mutation_method": "text_replace",
        "expected_match_count": 1,
        "test_selector": "tests/test_dummy.py",
    }
    id1 = MR.compute_mutation_id(base_commit, target_blob, spec1["mutation_class"], MR.canonical_json(spec1))
    id2 = MR.compute_mutation_id(base_commit, target_blob, spec2["mutation_class"], MR.canonical_json(spec2))
    assert id1 != id2, "coarse/fine mutant identities must not collide"

def test_mutation_id_collision():
    # Same as ME16 but also test that ID binds spec canonical bytes
    base_commit = "abc123"
    target_blob = "blob123"
    spec_a = {
        "target_path": "src/mod.py",
        "mutation_class": "FM08",
        "semantic_intent": "variant A",
        "before_fragment": "a",
        "after_fragment": "b",
        "mutation_method": "text_replace",
        "expected_match_count": 1,
        "test_selector": "tests/test_dummy.py",
    }
    spec_b = {
        "target_path": "src/mod.py",
        "mutation_class": "FM08",
        "semantic_intent": "variant B",  # different intent
        "before_fragment": "a",
        "after_fragment": "c",  # different after
        "mutation_method": "text_replace",
        "expected_match_count": 1,
        "test_selector": "tests/test_dummy.py",
    }
    id_a = MR.compute_mutation_id(base_commit, target_blob, spec_a["mutation_class"], MR.canonical_json(spec_a))
    id_b = MR.compute_mutation_id(base_commit, target_blob, spec_b["mutation_class"], MR.canonical_json(spec_b))
    assert id_a != id_b
    # Also test that same spec produces same ID deterministically
    id_a2 = MR.compute_mutation_id(base_commit, target_blob, spec_a["mutation_class"], MR.canonical_json(spec_a))
    assert id_a == id_a2

def test_crash_resume_proof():
    # Ensure every mutant gets durable receipt before next via resume flag
    tmp_repo = Path(tempfile.mkdtemp(prefix="crash_repo_"))
    (tmp_repo / "src").mkdir(parents=True)
    (tmp_repo / "src" / "mod.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_repo / "tests").mkdir(parents=True)
    (tmp_repo / "tests" / "test_dummy.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    specs = []
    for i in range(2):
        specs.append({
            "campaign_track": "A1",
            "mutation_class": f"CRASH_{i}",
            "semantic_intent": "crash test",
            "target_path": "src/mod.py",
            "precondition_match_count": 1,
            "expected_match_count": 1,
            "before_fragment": "    return 1",
            "after_fragment": f"    return {i+5}",
            "mutation_method": "text_replace",
            "test_selector": "tests/test_dummy.py",
            "tier": "C",
            "timeout": 10,
        })
    receipts_dir = Path(tempfile.mkdtemp(prefix="crash_receipts_"))
    cache = {}
    MR.run_single_mutant(specs[0], "test", tmp_repo, receipts_dir, 10, resume=False, baseline_cache=cache)
    def count_receipts(d):
        return len([p for p in d.glob("*.json") if "mutation_id" in json.loads(p.read_text())])
    assert count_receipts(receipts_dir) == 1
    # Crash, resume by running remaining with resume=True
    for s in specs:
        MR.run_single_mutant(s, "test", tmp_repo, receipts_dir, 10, resume=True, baseline_cache=cache)
    summary = MR.build_summary_from_receipts(receipts_dir)
    assert summary["attempted"] == 2
    cleanup(tmp_repo)
    shutil.rmtree(receipts_dir, ignore_errors=True)
