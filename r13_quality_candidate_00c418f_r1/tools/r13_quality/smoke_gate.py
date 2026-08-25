#!/usr/bin/env python3
"""smoke_gate.py — fail-closed gate over a curated mutation smoke campaign.

The mutation runner itself is evidence-oriented and always exits 0. This gate
converts curated smoke receipts into a hard CI decision.

Reads SUMMARY.json produced by mutation_runner and enforces ALL of:
  - summary file exists, parses, and reports attempted > 0
  - min_attempted <= attempted <= max_attempted  (curated size window)
  - every attempted mutant is KILLED_SEMANTIC
  - zero SURVIVED_MATERIAL   (valid critical mutant survived -> FAIL)
  - zero HARNESS_ERROR       (framework error must never count as kill)
  - zero HARNESS_TIMEOUT     (mandatory mutant timed out -> FAIL)
  - zero INVALID_MUTANT      (spec/precondition drift -> FAIL)
  - zero BASELINE_INVALID    (oracle broken on clean tree -> FAIL)
  - zero EQUIVALENT_CONFIRMED (no equivalents allowed in critical smoke)

Any violation prints an explicit stderr diagnostic and exits nonzero.

Usage:
  python tools/r13_quality/smoke_gate.py --summary DIR/SUMMARY.json \
      [--min-attempted 12] [--max-attempted 18]
"""
from __future__ import annotations
import argparse
import json
import sys

EXIT_VIOLATION = 1
EXIT_IO_ERROR = 2


def evaluate(summary: dict, min_attempted: int, max_attempted: int) -> list:
    """Return list of violation strings (empty == PASS)."""
    v = []
    counts = summary.get("counts", {})
    attempted = summary.get("attempted", 0)

    if not isinstance(attempted, int) or isinstance(attempted, bool):
        v.append(f"attempted is not an integer: {attempted!r}")
        return v
    if attempted <= 0:
        v.append(f"zero smoke mutants executed (attempted={attempted})")
        return v
    if attempted < min_attempted:
        v.append(f"attempted={attempted} below curated minimum {min_attempted}")
    if attempted > max_attempted:
        v.append(f"attempted={attempted} above curated maximum {max_attempted}")

    killed = counts.get("KILLED_SEMANTIC", 0)
    if killed != attempted:
        v.append(f"KILLED_SEMANTIC={killed} but attempted={attempted}")

    for cls in (
        "SURVIVED_MATERIAL",
        "HARNESS_ERROR",
        "HARNESS_TIMEOUT",
        "INVALID_MUTANT",
        "BASELINE_INVALID",
        "EQUIVALENT_CONFIRMED",
    ):
        c = counts.get(cls, 0)
        if c:
            v.append(f"{cls}={c} (must be 0)")
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="fail-closed curated smoke gate")
    ap.add_argument("--summary", required=True, help="path to SUMMARY.json from mutation_runner")
    ap.add_argument("--min-attempted", type=int, default=12)
    ap.add_argument("--max-attempted", type=int, default=18)
    args = ap.parse_args()

    try:
        raw = open(args.summary, "rb").read()
        summary = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"FAIL[smoke-gate]: cannot read/parse summary {args.summary}: {e}", file=sys.stderr)
        return EXIT_IO_ERROR

    violations = evaluate(summary, args.min_attempted, args.max_attempted)
    if violations:
        print("FAIL[smoke-gate]: curated mutation smoke gate violated:", file=sys.stderr)
        for x in violations:
            print(f"  - {x}", file=sys.stderr)
        return EXIT_VIOLATION

    print(
        "OK[smoke-gate]: "
        f"attempted={summary.get('attempted')} all KILLED_SEMANTIC; "
        "survivors=0 framework-errors=0 timeouts=0 invalid=0 baseline-invalid=0"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
