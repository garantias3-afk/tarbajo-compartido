#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# lector_independiente — hijo del harness que mide CAPACIDAD REAL por
# separado del SUT y de la metadata que el SUT afirme. Registra SU
# identidad (uid/euid/gid/grupos) al arrancar: los intentos de ataque
# corren SIEMPRE como uid operador; el hijo rechaza correr como root.
# Operaciones soportadas (tarea JSON): open, write, close, unlink, rename,
# chmod, truncate, mkdir, create, ls_leO, lstat, read_sha, exec.
# =====================================================================
"""Lector independiente C5: capacidad real medida por proceso aparte."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import child_identity, decode_flags, ename, sha256_file  # noqa: E402


def _result(op, **kw):
    out = {'op': op}
    out.update(kw)
    return out


def op_open(t, fds):
    flags = eval(t['flags'], {'__builtins__': {}},
                 {n: getattr(os, n, 0) for n in dir(os) if n.startswith('O_')})
    try:
        fd = os.open(t['path'], flags, t.get('mode', 0o600))
        tag = t.get('fd_tag', 'fd%d' % len(fds))
        fds[tag] = fd
        st = os.fstat(fd)
        return _result('open', fd_tag=tag, ok=True, flags_num=flags,
                       flags=decode_flags(flags), pin={'dev': st.st_dev,
                                                       'ino': st.st_ino},
                       modo=oct(st.st_mode & 0o7777))
    except OSError as e:
        return _result('open', ok=False, flags=t['flags'],
                       errno=e.errno, errno_name=ename(e.errno))


def op_write(t, fds):
    fd = fds[t['fd_tag']]
    try:
        n = os.write(fd, t.get('data', 'MUTADO-POR-LECTOR\n').encode())
        st = os.fstat(fd)
        return _result('write', ok=True, bytes=n,
                       pin={'dev': st.st_dev, 'ino': st.st_ino})
    except OSError as e:
        return _result('write', ok=False, errno=e.errno,
                       errno_name=ename(e.errno))


def op_close(t, fds):
    fd = fds.pop(t['fd_tag'], None)
    if fd is None:
        return _result('close', ok=False, error='fd_tag ausente')
    os.close(fd)
    return _result('close', ok=True)


def _try(t, fn):
    try:
        fn()
        return _result(t['op'], ok=True)
    except OSError as e:
        return _result(t['op'], ok=False, errno=e.errno,
                       errno_name=ename(e.errno))


def op_ls_leO(t, _fds):
    p = subprocess.run(['/bin/ls', '-leO', '--', t['path']],
                       capture_output=True)
    return _result('ls_leO', ok=(p.returncode == 0), rc=p.returncode,
                   salida=p.stdout.decode('utf-8', 'replace').strip())


def op_lstat(t, _fds):
    try:
        st = os.lstat(t['path'])
        return _result('lstat', ok=True, pin={'dev': st.st_dev,
                                              'ino': st.st_ino},
                       modo=oct(st.st_mode & 0o7777), uid=st.st_uid,
                       gid=st.st_gid, nlink=st.st_nlink, size=st.st_size)
    except OSError as e:
        return _result('lstat', ok=False, errno=e.errno,
                       errno_name=ename(e.errno))


def op_read_sha(t, _fds):
    try:
        return _result('read_sha', ok=True, sha256=sha256_file(t['path']))
    except OSError as e:
        return _result('read_sha', ok=False, errno=e.errno,
                       errno_name=ename(e.errno))


def op_exec(t, _fds):
    """Ejecuta un binario del fixture con env dado; captura marcador."""
    env = t.get('env') or {}
    try:
        p = subprocess.run(t['argv'], capture_output=True, env=env,
                           timeout=20)
        return _result('exec', ok=True, rc=p.returncode,
                       stdout=p.stdout.decode('utf-8', 'replace')[:500],
                       stderr=p.stderr.decode('utf-8', 'replace')[:500])
    except subprocess.TimeoutExpired:
        return _result('exec', ok=False, error='timeout')
    except OSError as e:
        return _result('exec', ok=False, errno=e.errno,
                       errno_name=ename(e.errno))


HANDLERS = {'open': op_open, 'write': op_write, 'close': op_close,
            'unlink': lambda t, f: _try(t, lambda: os.unlink(t['path'])),
            'rmdir': lambda t, f: _try(t, lambda: os.rmdir(t['path'])),
            'rename': lambda t, f: _try(t, lambda: os.rename(t['src'],
                                                             t['dst'])),
            'chmod': lambda t, f: _try(t, lambda: os.chmod(t['path'],
                                                           t['mode'])),
            'truncate': lambda t, f: _try(t, lambda: os.truncate(t['path'],
                                                                t['size'])),
            'mkdir': lambda t, f: _try(t, lambda: os.mkdir(t['path'],
                                                           t.get('mode',
                                                                 0o700))),
            'create': lambda t, f: _try(t, lambda: os.close(
                os.open(t['path'], os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        t.get('mode', 0o600)))),
            'ls_leO': op_ls_leO, 'lstat': op_lstat, 'read_sha': op_read_sha,
            'exec': op_exec}


def main():
    ident = child_identity()
    if ident['euid'] == 0:
        print(json.dumps({'error': 'el lector NO corre como root'}))
        return 5
    args = sys.argv[1:]
    tarea_path = args[args.index('--tarea') + 1]
    out_path = args[args.index('--out') + 1]
    with open(tarea_path) as f:
        tarea = json.load(f)
    fds = {}
    ops = []
    for t in tarea.get('ops', []):
        h = HANDLERS.get(t['op'])
        if h is None:
            ops.append(_result(t.get('op', '?'), ok=False, error='op desconocida'))
            continue
        ops.append(h(t, fds))
        if t.get('fd_tag') and t['op'] in ('open',) and t.get('keep') is not True:
            pass  # el fd se cierra con op close explícita
    for tag in list(fds):
        try:
            os.close(fds[tag])
        except OSError:
            pass
    with open(out_path, 'w') as f:
        json.dump({'identidad': ident, 'ops': ops}, f, indent=2)
    print(json.dumps({'ops': len(ops), 'euid': ident['euid']}))
    return 0


if __name__ == '__main__':
    os.umask(0o077)
    sys.exit(main())
