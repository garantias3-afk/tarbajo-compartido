#!/usr/bin/env python3
"""test_collection_guard.py — deterministic fail-closed pytest collection guard.

Replaces the historical fail-open heredoc in r13-quality-ci.yml that could
reach script end with implicit exit 0 when:
  - collected test count is zero,
  - collection output is unrecognized,
  - the pytest collect command itself fails.

Success requires ALL of:
  pytest --collect-only returncode == 0
  AND parsed collected_count > 0

Every other state produces an explicit stderr diagnostic and an explicit
nonzero exit. There is no successful fallthrough.

Exit codes:
  0  collected_count > 0 and collection command succeeded
  2  collection command returned nonzero (or could not be executed)
  3  collection output present but count unparseable
  4  collection succeeded but zero tests collected

Usage:
  python tools/r13_quality/test_collection_guard.py TARGET [TARGET ...]
"""
from __future__ import annotations
import re
import subprocess
import sys

COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")

EXIT_COMMAND_FAILURE = 2
EXIT_UNPARSEABLE = 3
EXIT_ZERO_COLLECTED = 4


def build_collect_cmd(targets: list) -> list:
    return [
        sys.executable, "-m", "pytest",
        *targets,
        "--collect-only", "-q", "-p", "no:cacheprovider",
    ]


def parse_collected_count(output: str):
    """Return int count parsed from pytest --collect-only -q output, or None.

    Scans every line and keeps the LAST successful match (pytest prints the
    total on a dedicated 'N tests collected' summary line).
    """
    count = None
    for line in output.splitlines():
        m = COLLECTED_RE.search(line)
        if m:
            count = int(m.group(1))
    return count


def run_guard(targets: list, run_cmd=None) -> int:
    """Fail-closed guard. run_cmd injectable for authentic behavior tests."""
    if not targets:
        print("FAIL[zero-collection-guard]: no pytest targets supplied", file=sys.stderr)
        return EXIT_UNPARSEABLE
    cmd = build_collect_cmd(targets)
    try:
        if run_cmd is None:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        else:
            proc = run_cmd(cmd)
        returncode = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except Exception as e:
        print(
            f"FAIL[zero-collection-guard]: collection command could not be executed: {e}",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILURE

    if returncode != 0:
        if returncode == 5:
            # pytest's dedicated "no tests collected/ran" exit code
            print(
                f"FAIL[zero-collection-guard]: zero tests collected "
                f"(pytest returncode=5) for targets: {targets}; "
                "refusing to accept an empty suite",
                file=sys.stderr,
            )
            return EXIT_ZERO_COLLECTED
        print(
            f"FAIL[zero-collection-guard]: pytest collection command failed "
            f"(returncode={returncode}) for targets: {targets}",
            file=sys.stderr,
        )
        tail = (stderr.strip() or stdout.strip()).splitlines()[-5:]
        for ln in tail:
            print(f"  | {ln}", file=sys.stderr)
        return EXIT_COMMAND_FAILURE

    count = parse_collected_count(stdout + "\n" + stderr)
    if count is None:
        print(
            "FAIL[zero-collection-guard]: collection output unrecognized; "
            f"could not parse collected test count for targets: {targets}",
            file=sys.stderr,
        )
        tail = stdout.strip().splitlines()[-5:]
        for ln in tail:
            print(f"  | {ln}", file=sys.stderr)
        return EXIT_UNPARSEABLE

    if count <= 0:
        print(
            f"FAIL[zero-collection-guard]: zero tests collected for targets: {targets}; "
            "refusing to accept an empty suite",
            file=sys.stderr,
        )
        return EXIT_ZERO_COLLECTED

    print(f"OK[zero-collection-guard]: {count} tests collected")
    return 0


def main(argv: list) -> int:
    targets = list(argv)
    return run_guard(targets)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
