#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# harness_common — observación y disciplina del harness de ensayo C5.
#   - Journal con ORDEN TEMPORAL (seq + monotonic_ns + utc) por caso.
#   - Pins (dev,ino), instantáneas de bytes (sha/size/mtime), flags de open
#     decodificados, RC/errno con nombre observado.
#   - Hijos SIEMPRE como uid operador: identidad (uid/euid/gid/grupos)
#     registrada por el propio hijo al arrancar (lector_independiente).
#   - Limpieza propia por REGISTRO (ruta+dev/ino+creación), nunca por glob
#     ni diferencia de listados.
#   - Semántica de estados: PASA (oráculo cumplido), FALLA_PRODUCTO
#     (ataque exitoso ⇒ fallo del producto), SKIP (exige nativo/H1 o
#     adaptador sin soporte), INCONCLUSIVO (no se alcanzó el punto
#     ensayado — NUNCA cuenta como verde), ERROR.
# =====================================================================
"""Común del harness C5: observación, hijos, journal, estados."""
from __future__ import annotations

import ctypes
import ctypes.util
import datetime
import errno
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

PYTHON = sys.executable or '/usr/bin/python3'
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- estados del HARNESS (del test, no del SUT) ----------------------------
PASA = 'PASA'                      # el oráculo previsto se cumplió
FALLA_PRODUCTO = 'FALLA_PRODUCTO'  # ataque exitoso ⇒ fallo del producto
SKIP = 'SKIP'                      # exige fase nativa (H1) o sin soporte
INCONCLUSIVO = 'INCONCLUSIVO'      # punto ensayado no alcanzado (no es verde)
ERROR = 'ERROR'                    # defecto del harness (se investiga)

ROTULO = 'NO_PRODUCTIVO_NO_AUTORIZADO; harness de ensayo; sin root'


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ename(n: int):
    if n == 0:
        return None
    for k, v in vars(errno).items():
        if k.startswith('E') and v == n:
            return k
    try:
        libc = ctypes.CDLL(ctypes.util.find_library('c') or
                           '/usr/lib/libSystem.dylib', use_errno=True)
        libc.strerror.argtypes = [ctypes.c_int]
        libc.strerror.restype = ctypes.c_char_p
        return 'ERRNO_%d(%s)' % (n, libc.strerror(n).decode('utf-8', 'replace'))
    except Exception:
        return 'ERRNO_%d' % n


# ---- journal con orden temporal -------------------------------------------
class Journal:
    def __init__(self):
        self.events = []
        self._seq = 0

    def log(self, phase: str, event: str, **detail):
        self._seq += 1
        self.events.append({
            'seq': self._seq,
            't_monotonic_ns': time.monotonic_ns(),
            't_utc': utcnow(),
            'phase': phase,
            'event': event,
            **detail,
        })
        return self.events[-1]

    def merge_child(self, phase: str, child_events: list):
        """Incorpora eventos de un hijo conservando orden relativo propio."""
        self._seq += 1
        self.events.append({
            'seq': self._seq, 't_monotonic_ns': time.monotonic_ns(),
            't_utc': utcnow(), 'phase': phase, 'event': 'HIJO_EVENTOS',
            'hijos': child_events,
        })


# ---- observación de objetos ------------------------------------------------
def pin(path: str) -> dict:
    st = os.lstat(path)
    return {'dev': st.st_dev, 'ino': st.st_ino}


def pin_equal(a, b) -> bool:
    return a is not None and b is not None and a == b


def snapshot(path: str) -> dict:
    """Instantánea: tipo, pin, modo, dueño, tamaño, mtime, sha256 (regulares)."""
    st = os.lstat(path)
    out = {'path': path, 'pin': {'dev': st.st_dev, 'ino': st.st_ino},
           'modo': oct(st.st_mode & 0o7777),
           'tipo': ('dir' if stat.S_ISDIR(st.st_mode) else
                    'symlink' if stat.S_ISLNK(st.st_mode) else
                    'reg' if stat.S_ISREG(st.st_mode) else 'otro'),
           'uid': st.st_uid, 'gid': st.st_gid, 'nlink': st.st_nlink,
           'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
    if stat.S_ISREG(st.st_mode):
        out['sha256'] = sha256_file(path)
    return out


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


OFLAGS = {os.O_RDONLY: 'O_RDONLY', os.O_WRONLY: 'O_WRONLY', os.O_RDWR: 'O_RDWR',
          getattr(os, 'O_NONBLOCK', 4): 'O_NONBLOCK',
          getattr(os, 'O_APPEND', 8): 'O_APPEND',
          getattr(os, 'O_CREAT', 512): 'O_CREAT',
          getattr(os, 'O_TRUNC', 1024): 'O_TRUNC',
          getattr(os, 'O_EXCL', 2048): 'O_EXCL',
          getattr(os, 'O_NOFOLLOW', 256): 'O_NOFOLLOW',
          getattr(os, 'O_SHLOCK', 16): 'O_SHLOCK',
          getattr(os, 'O_EXLOCK', 32): 'O_EXLOCK',
          getattr(os, 'O_DIRECTORY', 1048576): 'O_DIRECTORY',
          getattr(os, 'O_CLOEXEC', 16777216): 'O_CLOEXEC',
          getattr(os, 'O_SYMLINK', 2097152): 'O_SYMLINK'}


def decode_flags(flags: int) -> str:
    partes = []
    acceso = flags & 0o3
    partes.append({0: 'O_RDONLY', 1: 'O_WRONLY', 2: 'O_RDWR'}.get(
        acceso, 'ACCESO_%d' % acceso))
    for bit, nombre in sorted(OFLAGS.items()):
        if bit and bit > 0o3 and flags & bit:
            partes.append(nombre)
    return '|'.join(partes)


def physical_path(path: str) -> str:
    p = os.path.abspath(path)
    for alias, real in (('/var/', '/private/var/'), ('/tmp/', '/private/tmp/')):
        if p.startswith(alias):
            return real + p[len(alias):]
    return p


def rename_excl(src: str, dst: str, nofollow_any: bool = True) -> int:
    """renamex_np(RENAME_EXCL [| RENAME_NOFOLLOW_ANY]) vía ctypes.
    Devuelve 0 o el errno observado (nunca colapsa errnos)."""
    libc = ctypes.CDLL(ctypes.util.find_library('c') or
                       '/usr/lib/libSystem.dylib', use_errno=True)
    fn = libc.renamex_np
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    fn.restype = ctypes.c_int
    flags = 0x00000004 | (0x00000010 if nofollow_any else 0)
    ctypes.set_errno(0)
    rc = fn(physical_path(src).encode(), physical_path(dst).encode(), flags)
    return 0 if rc == 0 else ctypes.get_errno()


# ---- inventario lstat-only (contenido) -------------------------------------
def inventory_tree(root: str) -> dict:
    """Inventario exacto lstat-only con sha256 de regulares; rechaza raíz
    symlink. Igual formato que P5r para reutilizar el ancla."""
    raw_root = os.path.abspath(root)
    if os.path.islink(raw_root) or not os.path.isdir(raw_root):
        raise RuntimeError('raiz invalida para inventario: %r' % root)
    entries = {}
    counts = {'regular': 0, 'directory': 0, 'symlink': 0}

    def walk(dir_path: str, rel: str) -> None:
        for name in sorted(os.listdir(dir_path)):
            epath = os.path.join(dir_path, name)
            rel_path = '%s/%s' % (rel, name) if rel else name
            st = os.lstat(epath)
            if stat.S_ISLNK(st.st_mode):
                counts['symlink'] += 1
                entries[rel_path] = {'type': 'symlink',
                                     'target': os.readlink(epath)}
            elif stat.S_ISDIR(st.st_mode):
                counts['directory'] += 1
                entries[rel_path] = {'type': 'directory'}
                walk(epath, rel_path)
            elif stat.S_ISREG(st.st_mode):
                counts['regular'] += 1
                entries[rel_path] = {'type': 'regular', 'size': st.st_size,
                                     'sha256': sha256_file(epath)}
            else:
                entries[rel_path] = {'type': 'especial',
                                     'mode': oct(st.st_mode & 0o7777)}

    walk(raw_root, '')
    rst = os.lstat(raw_root)
    return {'root': raw_root, 'root_pin': {'dev': rst.st_dev, 'ino': rst.st_ino},
            'counts': counts, 'entries': entries}


def write_anchor(app_dir: str, out_path: str) -> str:
    """Ancla de referencia: inventario JSON de una copia pristine + SHA-256
    EXTERNO al archivo (HB-4). Devuelve (ruta, sha)."""
    inv = inventory_tree(app_dir)
    data = json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n'
    with open(out_path, 'wb') as f:
        f.write(data)
    return out_path, sha256_bytes(data)


def compare_content(ref: dict, got: dict) -> bool:
    return ref.get('entries') == got.get('entries')


# ---- hijos: identidad registrada -------------------------------------------
def child_identity() -> dict:
    return {'pid': os.getpid(), 'uid': os.getuid(), 'euid': os.geteuid(),
            'gid': os.getgid(), 'egid': os.getegid(),
            'grupos': os.getgroups(),
            'host': os.uname().nodename, 't_utc': utcnow(),
            'rotulo': 'hijo del harness C5; uid operador exigido'}


def run_child(args: list, env_extra: dict | None = None, cwd: str | None = None):
    """Ejecuta un hijo propio con env saneado por defecto (sin DYLD_*/PYTHON*),
    registrando identidad del padre y devolviendo rc/stdout/stderr/errno."""
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
           'HOME': os.environ.get('HOME', '/'),
           'PYTHONDONTWRITEBYTECODE': '1',
           'TMPDIR': os.environ.get('TMPDIR', '/tmp')}
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(args, capture_output=True, env=env, cwd=cwd)
    return {'cmd': args, 'rc': p.returncode,
            'stdout': p.stdout.decode('utf-8', 'replace')[-4000:],
            'stderr': p.stderr.decode('utf-8', 'replace')[-4000:]}


def reader_child(work: str, tarea: dict) -> dict:
    """Lector independiente: hijo propio (python -B) que ejecuta operaciones
    de capacidad/lectura y reporta identidad + resultados JSON."""
    tarea_path = os.path.join(work, 'tarea_lector_%d.json' % os.getpid())
    out_path = os.path.join(work, 'lector_out_%d.json' % os.getpid())
    with open(tarea_path, 'w') as f:
        json.dump(tarea, f)
    r = run_child([PYTHON, '-B', os.path.join(HERE, 'lector_independiente.py'),
                   '--tarea', tarea_path, '--out', out_path])
    r['tarea_path'] = tarea_path
    if os.path.isfile(out_path):
        with open(out_path) as f:
            r['lector'] = json.load(f)
        os.unlink(out_path)
    os.unlink(tarea_path)
    return r


# ---- limpieza propia por registro ------------------------------------------
class OwnRegistry:
    """Registro de objetos propios por (ruta, dev, ino, marca de creación).
    La limpieza SOLO toca entradas registradas verificando pin; jamás glob."""
    def __init__(self, j: Journal):
        self.j = j
        self.items = []

    def add(self, path: str):
        try:
            p = pin(path)
        except OSError as e:
            self.j.log('REGISTRO', 'PIN_FALLA', path=path, errno=ename(e.errno))
            return
        self.items.append({'path': path, 'pin': p,
                           'creado_utc': utcnow()})

    def cleanup(self) -> list:
        informe = []
        for it in sorted(self.items, key=lambda x: -x['path'].count('/')):
            p, pinv = it['path'], it['pin']
            if not os.path.lexists(p):
                informe.append({'path': p, 'accion': 'ya_ausente'})
                continue
            try:
                cur = pin(p)
                if cur != pinv:
                    informe.append({'path': p, 'accion': 'PIN_CAMBIO_NO_TOCAR',
                                    'pin_registrado': pinv, 'pin_actual': cur})
                    continue
                if os.path.islink(p) or os.path.isfile(p):
                    os.unlink(p)
                elif os.path.isdir(p):
                    os.rmdir(p)
                informe.append({'path': p, 'accion': 'eliminado', 'pin': cur})
            except OSError as e:
                informe.append({'path': p, 'accion': 'fallo_reportado',
                                'errno': ename(e.errno)})
        self.items = []
        return informe


def fresh_work(base: str, tag: str) -> str:
    """Directorio de trabajo propio (0700) registrado por el llamador."""
    d = tempfile.mkdtemp(prefix='c5work_%s.' % tag, dir=base)
    os.chmod(d, 0o700)
    return d
