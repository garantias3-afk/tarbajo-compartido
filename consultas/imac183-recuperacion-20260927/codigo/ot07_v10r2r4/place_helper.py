#!/usr/bin/env python3
"""OT07 v10r2r1 — placement helpers: exclusive rename, exact inventory, C-5 gate.

renamex_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY) via ctypes — no third-party binary.
RC mapping: 0 moved, 17 EEXIST (destination appeared), other error.
Never follows symlinks in the syscall; parents are validated separately.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

RENAME_EXCL = 0x00000004
RENAME_NOFOLLOW_ANY = 0x00000010
C5_KNOWN = ('REQUIERE_DECISION_C5', 'root', 'aceptar_usuario')
C5_IMPLEMENTED = ('aceptar_usuario',)
C5_NOT_IMPLEMENTED = ('root',)


def physical_path(path: str) -> str:
    """Map documented /var and /tmp aliases to their physical /private forms.
    renamex_np(RENAME_NOFOLLOW_ANY) rejects a path whose prefix contains a symlink
    (e.g. /var -> /private/var) with ELOOP; callers must pass physical paths."""
    p = os.path.abspath(path)
    for alias, real in (('/var/', '/private/var/'), ('/tmp/', '/private/tmp/')):
        if p.startswith(alias):
            return real + p[len(alias):]
    return p


def rename_excl(src: str, dst: str) -> int:
    """Atomic exclusive rename. Returns 0, 17 (EEXIST), or 1.
    Uses physical paths so RENAME_NOFOLLOW_ANY does not reject /var aliases."""
    s, d = physical_path(src), physical_path(dst)
    libc = ctypes.CDLL('/usr/lib/libSystem.dylib', use_errno=True)
    fn = libc.renamex_np
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    fn.restype = ctypes.c_int
    ctypes.set_errno(0)
    rc = fn(s.encode(), d.encode(), RENAME_EXCL | RENAME_NOFOLLOW_ANY)
    if rc == 0:
        return 0
    e = ctypes.get_errno()
    # M-1: preserve real errno (EEXIST=17, ELOOP=62, …). Never collapse to 1.
    return e if e else 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory_tree(root: Path) -> dict:
    """Exact inventory: dirs + regular (size/sha256) + symlink targets. No follow.
    I-1: reject a symlink root BEFORE resolve() would follow it."""
    raw = Path(root)
    if raw.is_symlink():
        raise ValueError('raiz es symlink (rechazo previo a resolve): %r' % root)
    if not raw.is_dir():
        raise ValueError('raiz no es directorio: %r' % root)
    root = raw.resolve()
    if root.is_symlink():
        raise ValueError('raiz resuelta sigue siendo symlink: %r' % root)
    entries = {}
    counts = {'regular': 0, 'directory': 0, 'symlink': 0}

    def walk(dir_path: Path, rel: str) -> None:
        with os.scandir(dir_path) as scan:
            for entry in scan:
                rel_path = f'{rel}/{entry.name}' if rel else entry.name
                epath = Path(entry.path)
                st = entry.stat(follow_symlinks=False)
                if entry.is_symlink():
                    target = os.readlink(epath)
                    if target.startswith('/') or target.startswith('~') or '..' in Path(target).parts:
                        raise ValueError(f'enlace no confinado: {rel_path} -> {target}')
                    resolved = (epath.parent / target).resolve(strict=True)
                    try:
                        resolved.relative_to(root)
                    except ValueError:
                        raise ValueError(f'enlace escapa: {rel_path} -> {target}')
                    counts['symlink'] += 1
                    entries[rel_path] = {'type': 'symlink', 'target': target}
                elif stat.S_ISDIR(st.st_mode):
                    counts['directory'] += 1
                    entries[rel_path] = {'type': 'directory'}
                    walk(epath, rel_path)
                elif stat.S_ISREG(st.st_mode):
                    counts['regular'] += 1
                    entries[rel_path] = {
                        'type': 'regular', 'size': st.st_size, 'sha256': sha256_file(epath),
                    }
                else:
                    raise ValueError(f'tipo especial: {rel_path}')
    walk(root, '')
    return {'root': str(root), 'counts': counts, 'entries': entries}


def inventories_equal(a: dict, b: dict) -> bool:
    return a.get('entries') == b.get('entries')


def check_c5_policy(mode: str) -> dict:
    """Gate BEFORE any placement effect.

    Distinguishes: invalid / undecided / known-but-not-implemented / implemented.
    B-1: a known-but-unimplemented policy (root) must fail at the gate, never
    after publishing. No default that implies user authorization.
    """
    if mode not in C5_KNOWN:
        raise ValueError('C5_INVALIDA: politica desconocida o ausente: %r' % (mode,))
    if mode == 'REQUIERE_DECISION_C5':
        raise ValueError('C5_NO_DECIDIDA: no iniciar colocacion sin politica aprobada')
    if mode in C5_NOT_IMPLEMENTED:
        raise ValueError(
            'C5_NO_IMPLEMENTADA: %r es conocida pero la proteccion no esta implementada; '
            'no publicar ni trasladar' % (mode,))
    if mode not in C5_IMPLEMENTED:
        raise ValueError('C5_INVALIDA: %r' % (mode,))
    return {'c5_mode': mode, 'gate': 'passed_before_effects',
            'implemented': True, 'protection_pending': False}


def resolve_alias(path: str) -> str:
    """Normalize only documented macOS /var <-> /private/var alias. Reject others."""
    p = os.path.abspath(path)
    for a, b in (('/var/', '/private/var/'), ('/tmp/', '/private/tmp/')):
        if p.startswith(b):
            return a + p[len(b):]
    return p


def same_filesystem(a: str, b: str) -> bool:
    sa, sb = os.stat(a), os.stat(b)
    return sa.st_dev == sb.st_dev


def parse_positive_int(text: str, label: str) -> int:
    """B-2: reject empty, non-numeric, zero, negative, and oversized values."""
    s = (text or '').strip()
    if not s or not s.isdigit():
        raise ValueError('%s no es entero positivo: %r' % (label, text))
    n = int(s)
    if n <= 0:
        raise ValueError('%s debe ser > 0: %r' % (label, n))
    if n > 1 << 40:
        raise ValueError('%s fuera de rango: %r' % (label, n))
    return n


def measure_space_need(src: str) -> int:
    """Live du of source plus 2 GiB reserve. Fails closed on any tool error."""
    import subprocess
    r = subprocess.run(['/usr/bin/du', '-sk', src], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise ValueError('du RC=%d: %s' % (r.returncode, r.stderr[-200:]))
    parts = (r.stdout or '').split()
    if not parts:
        raise ValueError('du sin salida')
    size_kib = parse_positive_int(parts[0], 'du_kib')
    return size_kib + 2 * 1024 * 1024


def measure_space_avail(dirpath: str) -> int:
    import subprocess
    r = subprocess.run(['/bin/df', '-k', dirpath], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise ValueError('df RC=%d: %s' % (r.returncode, r.stderr[-200:]))
    lines = [ln for ln in (r.stdout or '').splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError('df salida incompleta')
    avail = parse_positive_int(lines[-1].split()[3] if len(lines[-1].split()) > 3 else '', 'df_avail')
    return avail


def main(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('rename-excl')
    r.add_argument('src'); r.add_argument('dst')
    i = sub.add_parser('inventory')
    i.add_argument('root'); i.add_argument('out')
    c = sub.add_parser('compare-inv')
    c.add_argument('a'); c.add_argument('b')
    g = sub.add_parser('c5-gate')
    g.add_argument('mode')
    s = sub.add_parser('same-fs')
    s.add_argument('a'); s.add_argument('b')
    sp = sub.add_parser('space-check')
    sp.add_argument('src'); sp.add_argument('avail_dir')
    args = p.parse_args(argv)
    if args.cmd == 'rename-excl':
        rc = rename_excl(args.src, args.dst)
        print('RC=%d' % rc)
        return rc
    if args.cmd == 'inventory':
        inv = inventory_tree(Path(args.root))
        Path(args.out).write_text(json.dumps(inv, indent=2, sort_keys=True) + '\n')
        print(json.dumps(inv['counts'], sort_keys=True))
        return 0
    if args.cmd == 'compare-inv':
        a = json.loads(Path(args.a).read_text())
        b = json.loads(Path(args.b).read_text())
        ok = inventories_equal(a, b)
        print('EQUAL=%s' % ok)
        return 0 if ok else 1
    if args.cmd == 'c5-gate':
        print(json.dumps(check_c5_policy(args.mode)))
        return 0
    if args.cmd == 'same-fs':
        ok = same_filesystem(args.a, args.b)
        print('SAME_FS=%s' % ok)
        return 0 if ok else 1
    if args.cmd == 'space-check':
        need = measure_space_need(args.src)
        avail = measure_space_avail(args.avail_dir)
        ok = avail >= need
        print('NEED_KIB=%d AVAIL_KIB=%d OK=%s' % (need, avail, ok))
        return 0 if ok else 1
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print('PLACE_HELPER_FAIL: %s' % e, file=sys.stderr)
        sys.exit(2)
