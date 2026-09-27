#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN …C5IMAC1)
# Sondas NATIVAS de primitivas sobre fixtures propios (uid operador):
#   1) renamex_np RENAME_EXCL / RENAME_NOFOLLOW_ANY (errno reales)
#   2) constantes AT_* presentes en headers + sonda comportamental de
#      AT_UNIQUE (si existe): regular vs hardlink vs symlink.
#      REGLA OT: la existencia de la constante en el header NO aprueba
#      nada; se mide el comportamiento real y se registra errno.
#   3) ACL: allow-write vía chmod +a, lectura con /bin/ls -leO,
#      enforcement real (open O_WRONLY), chmod -N; precedencia medida.
#   4) gobernanza por padre: unlink de hijo con padre 0555 (EACCES).
#   5) fd preabierto: sobrevive a chmod 0444 (escritura via fd) y a
#      rename (mismo ino) — mecanismo del oráculo N2.
# Todo sobre copias privadas en carpeta propia; sin root; sin dispositivos.
# =====================================================================
"""Sondas de primitivas macOS para PRUEBAS_NATIVAS_C5 (medición, no suposición)."""
from __future__ import annotations

import ctypes
import ctypes.util
import datetime
import errno
import json
import os
import re
import subprocess
import sys

RENAME_EXCL = 0x00000004
RENAME_NOFOLLOW_ANY = 0x00000010

HEADER_CANDIDATOS = (
    '/usr/include/sys/fcntl.h',
    '/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk/usr/include/sys/fcntl.h',
    '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk/usr/include/sys/fcntl.h',
    '/Library/Developer/CommandLineTools/SDKs/MacOSX27.0.sdk/usr/include/sys/fcntl.h',
    '/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk/usr/include/sys/fcntl.h',
)


def ename(n: int) -> str:
    if n == 0:
        return None
    for k, v in vars(errno).items():
        if k.startswith('E') and v == n:
            return k
    # errno sin nombre en el módulo (p. ej. 107 "Capabilities insufficient"):
    # usar strerror del propio sistema como nombre observado
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c') or
                           '/usr/lib/libSystem.dylib', use_errno=True)
        libc.strerror.argtypes = [ctypes.c_int]
        libc.strerror.restype = ctypes.c_char_p
        return 'ERRNO_%d(%s)' % (n, libc.strerror(n).decode('utf-8', 'replace'))
    except Exception:
        return 'ERRNO_%d' % n


def probe_renamex_np(work: str) -> dict:
    """RENAME_EXCL: publicar sobre destino EXISTENTE → EEXIST;
    RENAME_NOFOLLOW_ANY con destino symlink → ELOOP. Cada sub-sonda con
    fuente y destino propios."""
    libc = ctypes.CDLL(ctypes.util.find_library('c') or '/usr/lib/libSystem.dylib',
                       use_errno=True)
    fn = libc.renamex_np
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    fn.restype = ctypes.c_int

    def ren(src, dst, flags):
        ctypes.set_errno(0)
        rc = fn(src.encode(), dst.encode(), flags)
        e = ctypes.get_errno()
        return {'rc': rc, 'errno': e, 'errno_name': ename(e) if rc != 0 else None}

    base = os.path.join(work, 'ren_probe')
    os.makedirs(base, 0o755)
    out = {}

    def fuente(tag):
        f = os.path.join(base, 'src_' + tag)
        with open(f, 'wb') as fh:
            fh.write(b'probe\n')
        return f

    # 1) publicación normal a destino libre
    out['publicacion_libre'] = ren(fuente('a'), os.path.join(base, 'd1'),
                                   RENAME_EXCL)
    # 2) RENAME_EXCL sobre destino YA EXISTENTE → EEXIST esperado
    out['excl_sobre_existente'] = ren(fuente('b'), os.path.join(base, 'd1'),
                                      RENAME_EXCL)
    # 3) NOFOLLOW_ANY con destino symlink → ELOOP esperado
    linkd = os.path.join(base, 'd2_link')
    os.symlink(os.path.join(base, 'd1'), linkd)
    out['destino_symlink_nofollow'] = ren(fuente('c'), linkd,
                                          RENAME_EXCL | RENAME_NOFOLLOW_ANY)
    for name in os.listdir(base):
        p = os.path.join(base, name)
        os.unlink(p) if not os.path.isdir(p) else None
    os.rmdir(base)
    return out


def probe_at_flags(work: str) -> dict:
    """Constantes AT_* leídas de headers locales + sonda comportamental.
    La constante SOLO indica disponibilidad nominal; el veredicto sale del
    errno medido por fstatat sobre regular/hardlink/symlink."""
    header, defines = None, {}
    for h in HEADER_CANDIDATOS:
        if os.path.isfile(h):
            header = h
            with open(h, 'r', errors='replace') as f:
                txt = f.read()
            for m in re.finditer(r'#define\s+(AT_[A-Z_]+)\s+(0x[0-9a-fA-F]+|\d+)',
                                 txt):
                defines[m.group(1)] = int(m.group(2), 0)
            break
    libc = ctypes.CDLL(ctypes.util.find_library('c') or '/usr/lib/libSystem.dylib',
                       use_errno=True)
    fn = libc.fstatat64 if hasattr(libc, 'fstatat64') else libc.fstatat
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p,
                   ctypes.c_void_p, ctypes.c_int]
    fn.restype = ctypes.c_int

    def fstatat_flag(path, flag):
        buf = ctypes.create_string_buffer(144)
        ctypes.set_errno(0)
        rc = fn(-2, path.encode(), buf, flag)
        e = ctypes.get_errno()
        return {'rc': rc, 'errno': e, 'errno_name': ename(e) if rc != 0 else None}

    d = os.path.join(work, 'at_probe')
    os.makedirs(d, 0o755)
    regular = os.path.join(d, 'reg')
    hard = os.path.join(d, 'hard')
    link = os.path.join(d, 'link')
    with open(regular, 'wb') as f:
        f.write(b'x\n')
    os.link(regular, hard)
    os.symlink(regular, link)
    out = {'header': header, 'defines': defines, 'sondas': {}}
    at_unique = defines.get('AT_UNIQUE')
    if at_unique is not None:
        sondeos = {'regular': fstatat_flag(regular, at_unique),
                   'hardlink': fstatat_flag(hard, at_unique),
                   'symlink': fstatat_flag(link, at_unique)}
        todo_rechaza = all(s['rc'] != 0 for s in sondeos.values())
        sondeos['_lectura'] = (
            'AT_UNIQUE %s RECHAZA TODO desde uid operador (errno %s) incluso '
            'para regular nlink=1: la constante existe en el header pero NO '
            'es usable sin privilegios en este host. No se aprueba por '
            'existencia de la constante; el candidato debe demostrar su '
            'primitiva con sonda negativa real o fallback fail-closed.'
            % (hex(at_unique),
               next(iter(sondeos.values()))['errno_name'])
            if todo_rechaza else
            'AT_UNIQUE %s se comporta de forma diferenciada (ver errno por tipo)' % hex(at_unique))
        out['sondas']['AT_UNIQUE_%s' % hex(at_unique)] = sondeos
    else:
        out['sondas']['AT_UNIQUE'] = 'AUSENTE en headers locales: el candidato ' \
            'debe demostrar primitiva alternativa con sonda negativa real ' \
            '(fail-closed), no por nombre'
    if 'AT_SYMLINK_NOFOLLOW' in defines:
        out['sondas']['AT_SYMLINK_NOFOLLOW'] = {
            'regular': fstatat_flag(regular, defines['AT_SYMLINK_NOFOLLOW']),
            'symlink': fstatat_flag(link, defines['AT_SYMLINK_NOFOLLOW']),
        }
    os.unlink(hard)
    os.unlink(link)
    os.unlink(regular)
    os.rmdir(d)
    return out


def probe_acl(work: str) -> dict:
    """ACE allow-write sobre modo 0444: si open O_WRONLY del dueño SUCCEDE,
    la ACL otorga capacidad que el modo no da (precedencia medida, no
    asumida). chmod -N la retira. Lectura independiente con /bin/ls -leO."""
    f = os.path.join(work, 'acl_probe.bin')
    with open(f, 'wb') as fh:
        fh.write(b'probe\n')
    os.chmod(f, 0o444)
    out = {'modo_0444_sin_acl': {}, 'con_ace_allow_write': {}, 'tras_chmod_N': {}}

    def try_open_write():
        try:
            fd = os.open(f, os.O_WRONLY)
            os.close(fd)
            return {'open_OWRONLY': 'SUCCEDE'}
        except OSError as e:
            return {'open_OWRONLY': 'RECHAZA', 'errno': e.errno,
                    'errno_name': ename(e.errno)}

    out['modo_0444_sin_acl'].update(try_open_write())
    cmd1 = ['/bin/chmod', '+a', 'OPERADOR allow write', f]
    p1 = subprocess.run(cmd1, capture_output=True)
    out['con_ace_allow_write']['chmod_rc'] = p1.returncode
    out['con_ace_allow_write']['ls_leO'] = subprocess.run(
        ['/bin/ls', '-leO', '--', f], capture_output=True
    ).stdout.decode('utf-8', 'replace').strip()
    out['con_ace_allow_write'].update(try_open_write())
    subprocess.run(['/bin/chmod', '-N', f], capture_output=True)
    out['tras_chmod_N']['ls_leO'] = subprocess.run(
        ['/bin/ls', '-leO', '--', f], capture_output=True
    ).stdout.decode('utf-8', 'replace').strip()
    out['tras_chmod_N'].update(try_open_write())
    os.unlink(f)
    return out


def probe_padre_gobierna_borrado(work: str) -> dict:
    """Mecanismo N1/N3: la eliminabilidad la gobierna el PADRE, no el dueño
    del hijo. Medible sin root con archivos propios."""
    out = {}
    parent = os.path.join(work, 'padre_probe')
    os.makedirs(parent, 0o755)
    child = os.path.join(parent, 'hijo')
    with open(child, 'wb') as fh:
        fh.write(b'x\n')
    os.chmod(parent, 0o555)  # padre sin W para dueño
    try:
        os.unlink(child)
        out['unlink_padre_0555'] = 'SUCCEDE (inesperado)'
    except OSError as e:
        out['unlink_padre_0555'] = {'resultado': 'RECHAZA', 'errno': e.errno,
                                    'errno_name': ename(e.errno)}
    os.chmod(parent, 0o755)
    try:
        os.unlink(child)
        out['unlink_padre_0755'] = 'SUCCEDE'
    except OSError as e:
        out['unlink_padre_0755'] = {'resultado': 'RECHAZA', 'errno': e.errno}
    os.rmdir(parent)
    return out


def probe_fd_preabierto(work: str) -> dict:
    """Mecanismo N2: fd O_RDWR preabierto sobrevive a chmod 0444 (la
    escritura por fd SUCCEDE) y a rename (mismo ino). Medible sin root."""
    f = os.path.join(work, 'fd_probe.bin')
    with open(f, 'wb') as fh:
        fh.write(b'AAAA\n')
    fd = os.open(f, os.O_RDWR)
    ino0 = os.fstat(fd).st_ino
    os.chmod(f, 0o444)
    try:
        n = os.write(fd, b'MUTA')
        escritura_tras_chmod = 'SUCCEDE (%d bytes)' % n
    except OSError as e:
        escritura_tras_chmod = {'resultado': 'RECHAZA', 'errno': e.errno,
                                'errno_name': ename(e.errno)}
    f2 = f + '.renombrado'
    os.rename(f, f2)
    try:
        os.write(fd, b'MUTB')
        escritura_tras_rename = 'SUCCEDE'
    except OSError as e:
        escritura_tras_rename = {'resultado': 'RECHAZA', 'errno': e.errno}
    os.close(fd)
    with open(f2, 'rb') as fh:
        contenido_final = fh.read()
    ino1 = os.lstat(f2).st_ino
    os.unlink(f2)
    return {'escritura_tras_chmod_0444': escritura_tras_chmod,
            'escritura_tras_rename': escritura_tras_rename,
            'ino_conservado': ino0 == ino1,
            'contenido_final': contenido_final.decode('utf-8', 'replace').strip()}


def main():
    os.umask(0o077)
    if os.geteuid() == 0:
        print(json.dumps({'error': 'las sondas corren SOLO como uid operador'}))
        return 5
    work = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'resultados', 'work',
        'probe_primitivas')
    os.makedirs(work, exist_ok=True)
    probes = {
        '_meta': {
            'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'euid': os.geteuid(), 'uid': os.getuid(),
            'grupos': os.getgroups(), 'work': work,
            'rotulo': 'NO_PRODUCTIVO_NO_AUTORIZADO; medición sobre fixtures propios',
        },
        'renamex_np': probe_renamex_np(work),
        'at_flags': probe_at_flags(work),
        'acl': probe_acl(work),
        'padre_gobierna_borrado': probe_padre_gobierna_borrado(work),
        'fd_preabierto': probe_fd_preabierto(work),
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                       'resultados', 'probes_nativos.json')
    with open(out, 'w') as f:
        json.dump(probes, f, indent=2, ensure_ascii=False)
    print(json.dumps(probes, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
