#!/usr/bin/env python3
"""OT07 v10r2 — inventory and exact-tree comparator (offline, no follow symlinks).

Produces a stable JSON inventory of a directory tree and compares two inventories.
Does not execute anything inside the trees. Fail-closed on special types, escaping
symlinks, or any content/metadata mismatch requested by the caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def symlink_confined(link: Path, target: str, root: Path) -> tuple[bool, str]:
    """Reject absolute targets, '..' components, cycles, and escapes via realpath."""
    if target.startswith("/") or target.startswith("~"):
        return False, f"absolute/tilde symlink: {link} -> {target}"
    parts = Path(target).parts
    if any(p == ".." for p in parts):
        return False, f"dotdot symlink: {link} -> {target}"
    # resolve relative to link parent without following the link itself
    resolved = (link.parent / target)
    try:
        real = resolved.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        return False, f"unresolvable symlink: {link} -> {target} ({e})"
    try:
        real.relative_to(root.resolve())
    except ValueError:
        return False, f"symlink escapes root: {link} -> {target} => {real}"
    return True, str(real)


def build_inventory(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"root is not a directory: {root}")
    entries = {}
    counts = {"regular": 0, "directory": 0, "symlink": 0}
    symlinks = []
    specials = []
    seen_links = set()

    def walk(dir_path: Path, rel: str) -> None:
        with os.scandir(dir_path) as scan:
            for entry in scan:
                rel_path = f"{rel}/{entry.name}" if rel else entry.name
                st = entry.stat(follow_symlinks=False)
                mode = st.st_mode
                if entry.is_symlink():
                    target = os.readlink(entry.path)
                    ok, detail = symlink_confined(Path(entry.path), target, root)
                    if not ok:
                        raise ValueError(detail)
                    # cycle guard on target chain
                    cur = Path(entry.path)
                    hops = 0
                    while cur.is_symlink() and hops < 32:
                        if str(cur) in seen_links:
                            raise ValueError(f"symlink cycle involving {cur}")
                        seen_links.add(str(cur))
                        nxt = (cur.parent / os.readlink(cur))
                        cur = nxt
                        hops += 1
                    if hops >= 32:
                        raise ValueError(f"symlink chain too long: {entry.path}")
                    counts["symlink"] += 1
                    symlinks.append({"path": rel_path, "target": target, "resolved": detail})
                    entries[rel_path] = {"type": "symlink", "target": target}
                elif stat.S_ISDIR(mode):
                    counts["directory"] += 1
                    entries[rel_path] = {"type": "directory"}
                    walk(Path(entry.path), rel_path)
                elif stat.S_ISREG(mode):
                    counts["regular"] += 1
                    entries[rel_path] = {
                        "type": "regular",
                        "size": st.st_size,
                        "sha256": digest_file(Path(entry.path)),
                    }
                else:
                    specials.append(rel_path)
                    raise ValueError(f"special file rejected: {rel_path} mode={oct(mode)}")

    walk(root, "")
    return {
        "root": str(root),
        "counts": counts,
        "entries": entries,
        "symlinks": symlinks,
        "specials": specials,
    }


def compare(a: dict, b: dict, ignore_prefix: str | None = None) -> dict:
    """Exact tree compare. ignore_prefix strips a leading path component from b keys."""
    def norm(keys, inv):
        out = {}
        for k in keys:
            nk = k
            if ignore_prefix and k.startswith(ignore_prefix):
                nk = k[len(ignore_prefix):]
            out[nk] = inv["entries"][k]
        return out

    ea, eb = norm(a["entries"].keys(), a), norm(b["entries"].keys(), b)
    only_a = sorted(set(ea) - set(eb))
    only_b = sorted(set(eb) - set(ea))
    differ = []
    for k in sorted(set(ea) & set(eb)):
        va, vb = ea[k], eb[k]
        if va != vb:
            differ.append({"path": k, "a": va, "b": vb})
    return {
        "only_in_a": only_a,
        "only_in_b": only_b,
        "differ": differ,
        "common": len(set(ea) & set(eb)),
        "identical": not only_a and not only_b and not differ,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="OT07 inventory/compare")
    sub = p.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("root")
    inv.add_argument("out")
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("inv_a")
    cmp_.add_argument("inv_b")
    cmp_.add_argument("--ignore-prefix-b", default="")
    cmp_.add_argument("out")
    args = p.parse_args(argv)

    if args.cmd == "inventory":
        data = build_inventory(Path(args.root))
        Path(args.out).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(json.dumps(data["counts"], sort_keys=True))
        return 0
    a = json.loads(Path(args.inv_a).read_text())
    b = json.loads(Path(args.inv_b).read_text())
    res = compare(a, b, args.ignore_prefix_b or None)
    Path(args.out).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("common", "identical")},
                     sort_keys=True))
    return 0 if res["identical"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print(f"INVENTORY_FAIL: {e}", file=sys.stderr)
        sys.exit(2)
