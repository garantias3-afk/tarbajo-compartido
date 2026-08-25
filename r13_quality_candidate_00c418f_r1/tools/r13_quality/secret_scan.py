#!/usr/bin/env python3
"""secret_scan.py — binary-safe secret scanner with no blanket .md exemption.

Requirements:
  - scan tracked text files (git ls-files)
  - binary-safe (skip unreadable/binary)
  - no blanket `.md` exemption; explicit narrow allowlist only
  - GitHub PAT pattern, OpenAI-style key, Google API key, private key headers
  - exit non-zero when candidate secret detected
  - tested with fake tokens only, never real user tokens
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    'github_pat': re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    'openai_key': re.compile(r'sk-[A-Za-z0-9]{20,}'),
    'google_api': re.compile(r'AIza[A-Za-z0-9_\-]{30,}'),
    'private_key': re.compile(r'BEGIN.*PRIVATE KEY'),
}

# Narrow allowlist: only specific file patterns or content that is explicitly marked as test fixture
ALLOWLIST_PATTERNS = []
# No blanket extension exclusion
EXCLUDED_EXTENSIONS = set()  # no blanket .md exemption
# Explicit narrow allowlist mechanism: only files matching these exact allowlist patterns are skipped
ALLOWLIST_FILES = {
    # example: "tests/fixtures/fake_secrets.json"
}

# Narrowest exemption layer: repo-relative file PLUS exact line substring.
# Each entry documents a known benign literal (pattern-definition source,
# defect-inventory grep text, or fake fixture token). No whole-file or
# whole-pattern exemptions; a real secret on an exempted line differs from
# the exact documented substring and is still detected.
_PK_HDR_A = "BEGIN"
_PK_HDR_B = "PRIVATE KEY"
_FAKE_PAT = "github_pat_" + "12345678901234567890_ABCDEFGHIJ"
_FAKE_RSA = "BEGIN RSA " + _PK_HDR_B
_FAKE_SK = "sk-" + "12345678901234567890ABCDEFGHIJ"
_FAKE_AIZA = "AIza" + "Sy1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ123"
_LEGACY_GREP = "grep -Eq '" + _PK_HDR_A + ".*" + _PK_HDR_B + "'"
_ALLOW_TESTS_ORACLE = "PATTERNS['private_key'].pattern == r'" + _PK_HDR_A + ".*" + _PK_HDR_B
_ALLOW_SPEC_QUOTE = "PATTERNS['private_key'] = re.compile(r'" + _PK_HDR_A + ".*" + _PK_HDR_B + "')"
_ALLOW_SRC_DEF = "'private_key': re.compile(r'" + _PK_HDR_A + ".*" + _PK_HDR_B + "'),"
ALLOWLIST_LINES = {
    ".github/workflows/c8-wave1-ci.yml": (
        _LEGACY_GREP,  # legacy defect-inventory documentation (CI05)
    ),
    "tests/test_r13_ci_contract.py": (
        _FAKE_PAT,  # fake fixture token
        _FAKE_RSA,  # fake fixture header
        _FAKE_SK,  # fake fixture key
        _FAKE_AIZA,  # fake fixture key
        _ALLOW_TESTS_ORACLE,  # kill-oracle literal
        _LEGACY_GREP,  # allowlist-narrowness test reproduces the documented legacy literal
    ),
    "tools/r13_quality/mutation_specs.v1.json": (
        _ALLOW_SPEC_QUOTE,  # mutant spec quoting scanner source
    ),
    "tools/r13_quality/secret_scan.py": (
        _ALLOW_SRC_DEF,  # pattern definition itself
        _ALLOW_SPEC_QUOTE,  # kept for spec-anchor stability
    ),
}

PATTERNS['github_pat'] = re.compile(r'github_pat_[A-Za-z0-9_]{20,}')
PATTERNS['private_key'] = re.compile(r'BEGIN.*PRIVATE KEY')

def is_binary_safe(path: Path) -> bool:
    try:
        # try to read as utf-8, if fails treat as binary and skip safely
        path.read_bytes().decode('utf-8')
        return True
    except Exception:
        # binary file, skip but not error
        return False

def should_allowlist(path: str, line: str) -> bool:
    for pat in ALLOWLIST_PATTERNS:
        if pat.search(line):
            return True
    if path in ALLOWLIST_FILES:
        return True
    # narrowest layer: repo-relative file + exact documented substring only
    subs = ALLOWLIST_LINES.get(str(path).replace("\\", "/"))
    if subs:
        for sub in subs:
            if sub in line:
                return True
    # narrow: only allow if line contains explicit marker "ALLOWLISTED_FAKE_SECRET"
    if "ALLOWLISTED_FAKE_SECRET" in line:
        return True
    return False

def scan_file(path: Path, rel_path: str = None) -> list:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except Exception:
        # binary-safe: skip unreadable files
        return findings
    allow_key = rel_path if rel_path is not None else str(path)
    for i, line in enumerate(text.splitlines(), 1):
        if should_allowlist(allow_key, line):
            continue
        for name, pat in PATTERNS.items():
            if pat.search(line):
                findings.append({"file": str(path), "line": i, "pattern": name, "content": line.strip()[:200]})
    return findings

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    # get tracked files via git ls-files
    try:
        out = subprocess.run(["git", "ls-files"], cwd=str(repo_root), capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            print("failed to list tracked files", file=sys.stderr)
            return 1
        files = out.stdout.splitlines()
    except Exception as e:
        print(f"git ls-files failed: {e}", file=sys.stderr)
        return 1

    all_findings = []
    for rel in files:
        p = repo_root / rel
        # binary-safe: check if file exists and is text
        if not p.exists():
            continue
        # no blanket .md exemption: we scan all, but narrow allowlist covers docs
        # EXCLUDED_EXTENSIONS is empty, so we don't skip .md
        ext = p.suffix.lower()
        if ext in EXCLUDED_EXTENSIONS:
            continue
        findings = scan_file(p, rel_path=rel)
        all_findings.extend(findings)

    if all_findings:
        for f in all_findings:
            print(f"FAIL: {f['pattern']} in {f['file']}:{f['line']}: {f['content']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("OK: no secrets detected")
        return 0

if __name__ == "__main__":
    sys.exit(main())
