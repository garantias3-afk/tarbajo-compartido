#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# Fabricación de fixtures confinados para el harness de ensayo nativo C5.
#   - Árbol "C5Fixture.app" <1 MiB, contenido ficticio determinista.
#   - Binarios INOCUOS DETERMINISTAS PROPIOS compilados desde c5_marker.c
#     (c5_marker → "C5_FIXTURE_VERIFICADO", c5_sustituto → "C5_SUBSTITUTO").
#     Prohibido createinstallmedia como fixture y /dev/disk real: nada de
#     eso aparece aquí ni con otro nombre funcional equivalente.
#   - Verificación de determinismo: cada binario se compila DOS veces y se
#     comparan SHA-256; divergencia ⇒ NON_DETERMINISTIC (registrado, se
#     recurre a script determinista con pin de bytes).
#   - Mutadores de árbol: única mutación por copia privada (escape, roto,
#     ciclo, fifo, hardlink, plist mutado, ACE allow, ACE heredada).
# Ejecutar SIEMPRE: /usr/bin/python3 -B (PYTHONDONTWRITEBYTECODE=1).
# =====================================================================
"""Fixtures C5 — pequeños, deterministas, confinados a carpeta propia."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

APP_NAME = 'C5Fixture.app'
MAX_FIXTURE_BYTES = 1024 * 1024  # fixture inicial < 1 MiB

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_MARKER = os.path.join(HERE, 'c5_marker.c')
TEXT_VERIFICADO = 'C5_FIXTURE_VERIFICADO'
TEXT_SUSTITUTO = 'C5_SUBSTITUTO'

FILES = {
    'Contents/Info.plist':
        (b'<?xml version="1.0"?>\n<plist version="1.0"><dict>'
         b'<key>Fixture</key><string>C5</string></dict></plist>\n', 0o644),
    'Contents/Resources/manifesto.json':
        (json.dumps({'fixture': 'C5', 'version': 'r1',
                     'notas': 'contenido ficticio; sin artefactos reales'},
                    indent=2, sort_keys=True).encode() + b'\n', 0o644),
    'Contents/Resources/version.plist':
        (b'<?xml version="1.0"?>\n<plist><string>fixture-1.0</string></plist>\n',
         0o664),
    'Contents/Resources/leyeme.txt':
        (b'Fixture C5: contenido ficticio para ensayos confinados.\n', 0o644),
    'Contents/SharedSupport/SharedSupport.dmg':
        (b'FIXTURE-C5-BYTES-FICTICIOS-0123456789\n' * 8, 0o644),
}
LINKS = {
    # enlaces relativos legítimos dentro del mismo árbol (sin '..')
    'Contents/Resources/plist_alias': 'version.plist',
    'Contents/SharedSupport/latest': 'SharedSupport.dmg',
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _compile(tag: str, text: str, out_dir: str, cc_bin: str = 'cc',
             sdk_sysroot: str | None = None) -> dict:
    """Compila c5_marker.c con -DC5_MARKER_TEXT="...". Determinismo exigido:
    COMPORTAMIENTO (3 ejecuciones idénticas) + BYTES fijados (SHA-256 pin del
    artefacto usado). La reproducibilidad bit a bit de la recompilación NO se
    exige (firma ad-hoc arm64 la impide en este toolchain): la doble
    compilación se registra como evidencia de esa condición."""
    out1 = os.path.join(out_dir, tag + '.build1')
    out2 = os.path.join(out_dir, tag + '.build2')
    flag = '-DC5_MARKER_TEXT="%s"' % text
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    cmds = []
    for out in (out1, out2):
        cmd = [cc_bin, '-O0']
        if sdk_sysroot:
            cmd += ['-isysroot', sdk_sysroot]
        cmd += [flag, '-o', out, SRC_MARKER]
        p = subprocess.run(cmd, capture_output=True, env=env)
        cmds.append({'cmd': ' '.join(cmd), 'rc': p.returncode,
                     'stderr': p.stderr.decode('utf-8', 'replace')[:400]})
        if p.returncode != 0:
            raise RuntimeError('compilación falló (%s): %s'
                               % (tag, cmds[-1]['stderr']))
    h1, h2 = sha256_file(out1), sha256_file(out2)
    os.unlink(out2)
    # determinismo de comportamiento: 3 ejecuciones, salida idéntica
    runs = []
    for _ in range(3):
        p = subprocess.run([out1], capture_output=True, env=env)
        runs.append({'rc': p.returncode,
                     'stdout': p.stdout.decode('utf-8', 'replace')})
    comportamiento_determinista = (len({r['stdout'] for r in runs}) == 1
                                   and len({r['rc'] for r in runs}) == 1)
    if not comportamiento_determinista:
        raise RuntimeError('binario %s no determinista en comportamiento' % tag)
    final = os.path.join(out_dir, tag)
    os.rename(out1, final)
    os.chmod(final, 0o755)
    return {'tag': tag, 'path': final, 'sha256': h1,
            'bytes': os.path.getsize(final),
            'comportamiento_determinista': True,
            'salida_comportamiento': runs[0]['stdout'].strip(),
            'rebuild_bit_reproducible': h1 == h2,
            'sha_build2': h2, 'compilaciones': cmds}


SDK_CANDIDATOS = (None,  # sysroot por omisión
                  '/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
                  '/Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk',
                  '/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')


def _pick_sdk(env: dict) -> dict:
    """Prueba candidatos de sysroot compilando de verdad la fuente del
    marcador; devuelve el primero que enlaza (el SDK por omisión de este
    host, 27.0, tiene tbd malformados para el ld actual — se registra)."""
    prueba_dir = os.path.join(env['work'], '_sdk_probe')
    os.makedirs(prueba_dir, exist_ok=True)
    intentos = []
    for sdk in SDK_CANDIDATOS:
        out = os.path.join(prueba_dir, 'probe.out')
        cmd = ['cc', '-O0']
        if sdk:
            cmd += ['-isysroot', sdk]
        cmd += ['-DC5_MARKER_TEXT="probe"', '-o', out, SRC_MARKER]
        p = subprocess.run(cmd, capture_output=True)
        intentos.append({'sdk': sdk or 'default', 'rc': p.returncode,
                         'stderr': p.stderr.decode('utf-8', 'replace')[:300]})
        if p.returncode == 0:
            os.unlink(out)
            return {'sysroot': sdk, 'intentos': intentos}
    raise RuntimeError('ningún sysroot permite enlazar: %s' % intentos)


def build_binaries(out_dir: str, cc_bin: str = 'cc') -> dict:
    """Compila los dos marcadores y verifica determinismo."""
    os.makedirs(out_dir, exist_ok=True)
    ver = subprocess.run([cc_bin, '--version'], capture_output=True)
    sdk = _pick_sdk({'work': os.path.dirname(out_dir)})
    marker = _compile('c5_marker', TEXT_VERIFICADO, out_dir, cc_bin,
                      sdk['sysroot'])
    sust = _compile('c5_sustituto', TEXT_SUSTITUTO, out_dir, cc_bin,
                    sdk['sysroot'])
    return {'cc_version': ver.stdout.decode('utf-8', 'replace').splitlines()[0],
            'sdk': sdk, 'marker': marker, 'sustituto': sust}


def build_app(root: str, binaries_dir: str, name: str = APP_NAME) -> str:
    """Árbol base: dirs 0755, regulares, symlinks internos válidos y el
    binario propio en Contents/MacOS/c5_marker. Devuelve la ruta del .app."""
    app = os.path.join(root, name)
    os.makedirs(os.path.join(app, 'Contents/MacOS'), 0o755, exist_ok=True)
    os.makedirs(os.path.join(app, 'Contents/Resources'), 0o755, exist_ok=True)
    os.makedirs(os.path.join(app, 'Contents/SharedSupport'), 0o755, exist_ok=True)
    for rel in sorted(FILES):
        data, mode = FILES[rel]
        p = os.path.join(app, rel)
        with open(p, 'wb') as f:
            f.write(data)
        os.chmod(p, mode)
    for rel, target in sorted(LINKS.items()):
        os.symlink(target, os.path.join(app, rel))
    shutil.copyfile(os.path.join(binaries_dir, 'c5_marker'),
                    os.path.join(app, 'Contents/MacOS/c5_marker'))
    os.chmod(os.path.join(app, 'Contents/MacOS/c5_marker'), 0o755)
    os.chmod(app, 0o755)
    os.chmod(os.path.join(app, 'Contents'), 0o755)
    return app


def tree_bytes(app: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(app):
        for name in filenames:
            total += os.lstat(os.path.join(dirpath, name)).st_size
    return total


# ---- mutadores: UNA mutación por copia privada -----------------------------
def add_escaping_symlink(app: str) -> None:
    os.symlink('../../fuera_de_raiz', os.path.join(app, 'Contents/escape'))


def add_broken_symlink(app: str) -> None:
    os.symlink('no_existe_en_ningun_lugar', os.path.join(app, 'Contents/roto'))


def add_cycle(app: str) -> None:
    os.symlink('autorreferido', os.path.join(app, 'Contents/autorreferido'))


def add_fifo(app: str) -> None:
    os.mkfifo(os.path.join(app, 'Contents/fifo'))


def add_hardlink(app: str) -> None:
    os.link(os.path.join(app, 'Contents/Info.plist'),
            os.path.join(app, 'Contents/hardlink'))


def mutate_plist(app: str) -> None:
    with open(os.path.join(app, 'Contents/Info.plist'), 'wb') as f:
        f.write(b'CONTENIDO_MUTADO\n')


def set_dir_go_w(app: str) -> None:
    os.chmod(app, 0o775)


def set_file_go_w(app: str) -> None:
    os.chmod(os.path.join(app, 'Contents/Info.plist'), 0o664)


# ---- ACL nativas (solo sobre fixtures propios del operador) ----------------
def acl_allow_write(path: str, user: str = 'OPERADOR') -> dict:
    """Añade ACE allow write: chmod +a# 0 '<user> allow write'."""
    cmd = ['/bin/chmod', '+a#', '0', '%s allow write' % user, path]
    p = subprocess.run(cmd, capture_output=True)
    return {'cmd': ' '.join(cmd), 'rc': p.returncode,
            'stderr': p.stderr.decode('utf-8', 'replace')[:200]}


def acl_allow_delete_child(parent: str, user: str = 'OPERADOR') -> dict:
    """ACE allow delete_child en un directorio."""
    cmd = ['/bin/chmod', '+a', '%s allow delete_child' % user, parent]
    p = subprocess.run(cmd, capture_output=True)
    return {'cmd': ' '.join(cmd), 'rc': p.returncode,
            'stderr': p.stderr.decode('utf-8', 'replace')[:200]}


def acl_inherit_write(parent: str, user: str = 'OPERADOR') -> dict:
    """ACE heredada (file_inherit/directory_inherit) allow write."""
    cmd = ['/bin/chmod', '+a', '%s allow write,file_inherit,directory_inherit'
           % user, parent]
    p = subprocess.run(cmd, capture_output=True)
    return {'cmd': ' '.join(cmd), 'rc': p.returncode,
            'stderr': p.stderr.decode('utf-8', 'replace')[:200]}


def acl_clear(path: str) -> dict:
    cmd = ['/bin/chmod', '-a#', 'all', path] if False else ['/bin/chmod', '-N', path]
    p = subprocess.run(cmd, capture_output=True)
    return {'cmd': ' '.join(cmd), 'rc': p.returncode,
            'stderr': p.stderr.decode('utf-8', 'replace')[:200]}


def read_ls_le(path: str) -> str:
    """Lector independiente de metadata/ACL: /bin/ls -dleO."""
    p = subprocess.run(['/bin/ls', '-dleO', '--', path], capture_output=True)
    return p.stdout.decode('utf-8', 'replace').strip()


def build_all(work: str) -> dict:
    """Fixture completo de una pieza: binarios + app + control de tamaño
    <1 MiB. Reconstruible: la copia pristine previa (ruta exacta propia) se
    retira antes de regenerar; jamás se toca nada fuera de `work`."""
    os.makedirs(work, exist_ok=True)
    pristine = os.path.join(work, 'pristine')
    if os.path.lexists(pristine):
        if os.path.isdir(pristine) and not os.path.islink(pristine):
            shutil.rmtree(pristine)
        else:
            os.unlink(pristine)
    binaries = build_binaries(os.path.join(work, 'bin'))
    os.makedirs(pristine, 0o755, exist_ok=True)
    app = build_app(pristine, os.path.join(work, 'bin'))
    size = tree_bytes(app)
    if size >= MAX_FIXTURE_BYTES:
        raise RuntimeError('fixture excede 1 MiB: %d bytes' % size)
    return {'binaries': binaries, 'app': app, 'fixture_bytes': size,
            'limite_bytes': MAX_FIXTURE_BYTES}


if __name__ == '__main__':
    os.umask(0o077)
    info = build_all(sys.argv[1] if len(sys.argv) > 1 else
                     os.path.join(HERE, 'build'))
    print(json.dumps({'app': info['app'], 'fixture_bytes': info['fixture_bytes'],
                      'marker_sha256': info['binaries']['marker']['sha256'],
                      'sustituto_sha256': info['binaries']['sustituto']['sha256'],
                      'marker_comportamiento_determinista':
                          info['binaries']['marker']['comportamiento_determinista'],
                      'sustituto_comportamiento_determinista':
                          info['binaries']['sustituto']['comportamiento_determinista']},
                     indent=2))
