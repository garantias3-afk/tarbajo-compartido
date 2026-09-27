#!/usr/bin/python3
"""OT07 v10r2 — installer preflight anchored to the signed PKG.

C-1 replacement for the bundle codesign check. Provenance is established by:
  1) PKG existence + pinned byte size + pinned SHA-256 (trust anchors, never read
     from the candidate under test)
  2) pkgutil --check-signature = signed Apple Software, chain ends at Apple Root CA
  3) pkgutil --expand-full into an owned private temp (no scripts executed)
  4) exact tree compare payload app <-> installed/extracted app, allowing only the
     postinstall transform (Contents/SharedSupport + SharedSupport.dmg)
  5) SharedSupport.dmg PKG top-level == app DMG (size + SHA-256 full)
  6) CIM codesign --verify --strict -R=anchor apple (kept; RC=0 required)

codesign -d / spctl are diagnostics only and never grant GO.
Offline functions never attach a DMG. read_dmg stays for authorized E later.
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path('/Applications/Install macOS Sonoma.app')
METADATA = 'com_apple_MobileAsset_MacSoftwareUpdate/com_apple_MobileAsset_MacSoftwareUpdate.xml'
SFR_METADATA = 'SFR/com_apple_MobileAsset_SFRSoftwareUpdate/com_apple_MobileAsset_SFRSoftwareUpdate.xml'

# Trust anchors — pinned in this revision. Never derived from the candidate tree.
PKG_RUTA = Path('/var/tmp/ot07_E2R1_candidato.gMdKSX/InstallAssistant.pkg')
PKG_BYTES = 13654790295
PKG_SHA256 = 'ecc36bf172105f8c3325ceeb4e5ab8cc297260be806eac10b21b784ff40d8173'
PKG_STATUS = 'signed Apple Software'
PKG_ROOT_CA = 'Apple Root CA'
POSTINSTALL_ADDITIONS = frozenset({
    'Contents/SharedSupport',
    'Contents/SharedSupport/SharedSupport.dmg',
})


def metadata_versions(data):
    assets = data.get('Assets', []) if isinstance(data, dict) else []
    if not isinstance(assets, list) or not assets or not isinstance(assets[0], dict):
        raise ValueError('sin Assets[0] valido')
    # OCLP 2.4.1 reads Assets[0]; other assets can describe ancillary components.
    version, build = assets[0].get('OSVersion', ''), assets[0].get('Build', '')
    if (not isinstance(version, str) or not isinstance(build, str) or
        not re.fullmatch(r'14\.[0-9]+(?:\.[0-9]+)?', version) or not re.fullmatch(r'23[A-Za-z0-9]+', build)):
        raise ValueError('payload no identificado como Sonoma: ' + repr((version, build)))
    return [{'version': version, 'build': build}]


def read_metadata(mp):
    # MacSoftwareUpdate takes precedence, as the final source in OCLP's two-path loop.
    # A present but invalid primary is an error: do not hide it with a valid secondary.
    for rel in (METADATA, SFR_METADATA):
        p = Path(mp) / rel
        if p.exists():
            return {'path': rel, 'asset_index': 0, 'versions': metadata_versions(plistlib.loads(p.read_bytes()))}
    raise ValueError('sin metadatos MacSoftwareUpdate ni SFRSoftwareUpdate')


def read_dmg(dmg):
    """Attach/mount for metadata. Only authorized E should call this."""
    mp = tempfile.mkdtemp(prefix='ot07_installer_')
    device, result, error = None, None, None
    attached = False
    try:
        r = subprocess.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-plist',
                            '-mountpoint', mp, str(dmg)], check=True, stdout=subprocess.PIPE)
        attached = True
        entities = plistlib.loads(r.stdout).get('system-entities', [])
        whole = [x['dev-entry'] for x in entities if re.fullmatch(r'/dev/disk[0-9]+', x.get('dev-entry', ''))]
        if len(whole) != 1:
            raise ValueError('no se puede identificar el dispositivo propio del DMG')
        device = whole[0]
        mounted = [x for x in entities if x.get('mount-point') and
                   os.path.realpath(x['mount-point']) == os.path.realpath(mp)]
        if len(mounted) != 1:
            raise ValueError('DMG no montado en el temporal propio')
        result = read_metadata(mp)
    except BaseException as exc:
        error = exc
    cleanup_error = None
    try:
        if device:
            subprocess.run(['/usr/bin/hdiutil', 'detach', device], check=True)
        elif attached:
            raise ValueError('attach sin dispositivo identificable: inspeccion manual necesaria')
        if os.path.ismount(mp):
            raise ValueError('temporal sigue montado')
        os.rmdir(mp)  # No recursive deletion and no force detach.
    except Exception as exc:
        cleanup_error = exc
    if cleanup_error:
        raise RuntimeError('DMG_CIERRE_PENDIENTE device=%r mountpoint=%r; causa_original=%r; cierre=%r'
                           % (device, mp, error, cleanup_error)) from error
    if error:
        raise error
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run_checked(cmd, *, env=None):
    """Run without pipes so RC is never masked. LC_ALL=C by default."""
    e = dict(os.environ, LC_ALL='C')
    if env:
        e.update(env)
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=e, text=True)


def verify_pkg_identity(pkg: Path) -> dict:
    if not pkg.is_file() or pkg.is_symlink():
        raise ValueError('PKG ausente o symlink: %r' % pkg)
    size = pkg.stat().st_size
    if size != PKG_BYTES:
        raise ValueError('PKG bytes %d != pineado %d' % (size, PKG_BYTES))
    digest = sha256_file(pkg)
    if digest != PKG_SHA256:
        raise ValueError('PKG sha256 %s != pineado %s' % (digest, PKG_SHA256))
    r = run_checked(['/usr/sbin/pkgutil', '--check-signature', str(pkg)])
    out = r.stdout
    if PKG_STATUS not in out:
        raise ValueError('pkgutil status no es %r: %s' % (PKG_STATUS, out[-200:]))
    if PKG_ROOT_CA not in out:
        raise ValueError('cadena no termina en %r' % PKG_ROOT_CA)
    return {'bytes': size, 'sha256': digest, 'status': PKG_STATUS, 'signature': out}


def inventory_tree(root: Path) -> dict:
    """Exact inventory; never follows symlinks; rejects special types and escapes.
    I-1: reject symlink root BEFORE resolve() would follow it."""
    raw = Path(root)
    if raw.is_symlink():
        raise ValueError('raiz es symlink (rechazo previo a resolve): %r' % root)
    if not raw.is_dir():
        raise ValueError('raiz de inventario invalida: %r' % root)
    root = raw.resolve()
    if root.is_symlink():
        raise ValueError('raiz resuelta sigue siendo symlink: %r' % root)
    entries = {}
    counts = {'regular': 0, 'directory': 0, 'symlink': 0}

    def walk(dir_path: Path, rel: str) -> None:
        with os.scandir(dir_path) as scan:
            for entry in scan:
                rel_path = f'{rel}/{entry.name}' if rel else entry.name
                st = entry.stat(follow_symlinks=False)
                mode = st.st_mode
                epath = Path(entry.path)
                if entry.is_symlink():
                    target = os.readlink(epath)
                    if target.startswith('/') or target.startswith('~') or '..' in Path(target).parts:
                        raise ValueError(f'enlace no confinado: {rel_path} -> {target}')
                    resolved = (epath.parent / target).resolve(strict=True)
                    try:
                        resolved.relative_to(root)
                    except ValueError:
                        raise ValueError(f'enlace escapa la raiz: {rel_path} -> {target}')
                    counts['symlink'] += 1
                    entries[rel_path] = {'type': 'symlink', 'target': target}
                elif stat.S_ISDIR(mode):
                    counts['directory'] += 1
                    entries[rel_path] = {'type': 'directory'}
                    walk(epath, rel_path)
                elif stat.S_ISREG(mode):
                    counts['regular'] += 1
                    entries[rel_path] = {
                        'type': 'regular', 'size': st.st_size, 'sha256': sha256_file(epath),
                    }
                else:
                    raise ValueError(f'tipo especial rechazado: {rel_path}')
    walk(root, '')
    return {'root': str(root), 'counts': counts, 'entries': entries}


def compare_trees(a: dict, b: dict) -> dict:
    ea, eb = a['entries'], b['entries']
    only_a = sorted(set(ea) - set(eb))
    only_b = sorted(set(eb) - set(ea))
    differ = []
    for k in sorted(set(ea) & set(eb)):
        if ea[k] != eb[k]:
            differ.append(k)
    return {'only_in_a': only_a, 'only_in_b': only_b, 'differ': differ,
            'identical': not only_a and not only_b and not differ}


def expand_pkg(pkg: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / 'pkg'
    if out.exists():
        raise ValueError('destino de expansion ya existe')
    run_checked(['/usr/sbin/pkgutil', '--expand-full', str(pkg), str(out)])
    if not out.is_dir():
        raise ValueError('expand-full no produjo directorio')
    return out


def verify_payload_matches_app(payload_app: Path, app: Path) -> dict:
    """Allow only the documented postinstall additions on the app side."""
    inv_p = inventory_tree(payload_app)
    inv_a = inventory_tree(app)
    res = compare_trees(inv_p, inv_a)
    extra = set(res['only_in_b'])
    if res['only_in_a']:
        raise ValueError('payload tiene entradas ausentes en app: %r' % res['only_in_a'][:5])
    if res['differ']:
        raise ValueError('contenido difiere: %r' % res['differ'][:5])
    if not extra <= POSTINSTALL_ADDITIONS:
        raise ValueError('extras no explicados por postinstall: %r' % sorted(extra - POSTINSTALL_ADDITIONS))
    missing = POSTINSTALL_ADDITIONS - extra
    if missing:
        raise ValueError('faltan adiciones del postinstall: %r' % sorted(missing))
    return {'payload_counts': inv_p['counts'], 'app_counts': inv_a['counts'],
            'only_in_payload': res['only_in_a'], 'only_in_app': res['only_in_b'],
            'differ': res['differ'], 'identical_except_postinstall': True}


def verify_dmg_anchor(pkg_expand: Path, app: Path) -> dict:
    dmg_pkg = pkg_expand / 'SharedSupport.dmg'
    dmg_app = app / 'Contents/SharedSupport/SharedSupport.dmg'
    for p in (dmg_pkg, dmg_app):
        if not p.is_file() or p.is_symlink():
            raise ValueError('DMG ausente o symlink: %r' % p)
    s1, s2 = dmg_pkg.stat().st_size, dmg_app.stat().st_size
    if s1 != s2 or s1 <= 10000000000:
        raise ValueError('DMG tamaños invalidos: pkg=%d app=%d' % (s1, s2))
    h1, h2 = sha256_file(dmg_pkg), sha256_file(dmg_app)
    if h1 != h2:
        raise ValueError('DMG sha256 difiere: pkg=%s app=%s' % (h1, h2))
    return {'bytes': s1, 'sha256': h1, 'identical': True}


def verify_cim_signature(cim: Path) -> dict:
    if not cim.is_file() or not os.access(cim, os.X_OK) or cim.is_symlink():
        raise ValueError('createinstallmedia ausente o no ejecutable')
    run_checked(['/usr/bin/codesign', '--verify', '--strict', '-R=anchor apple', str(cim)])
    return {'cim': str(cim), 'strict_anchor_apple': True}


def verify_bundle_basics(app: Path) -> dict:
    dmg = app / 'Contents/SharedSupport/SharedSupport.dmg'
    cim = app / 'Contents/Resources/createinstallmedia'
    info = app / 'Contents/Info.plist'
    if not dmg.is_file() or dmg.stat().st_size <= 10000000000:
        raise ValueError('SharedSupport.dmg ausente o <= 10 GB')
    if not os.access(cim, os.X_OK):
        raise ValueError('createinstallmedia no ejecutable')
    if not info.is_file() or info.stat().st_size <= 0:
        raise ValueError('Info.plist ausente')
    with info.open('rb') as f:
        if not isinstance(plistlib.load(f), dict):
            raise ValueError('Info.plist invalido')
    return {'dmg_bytes': dmg.stat().st_size, 'cim': str(cim)}


def diagnostic_signatures(app: Path, cim: Path) -> dict:
    """Never decisive. Records codesign -d / spctl for the report."""
    diag = {}
    for label, target in (('app', app), ('cim', cim)):
        try:
            r = subprocess.run(['/usr/bin/codesign', '-dvvv', str(target)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, env=dict(os.environ, LC_ALL='C'))
            diag[label] = {'codesign_d_rc': r.returncode, 'out': r.stdout[-1500:]}
        except Exception as e:
            diag[label] = {'error': str(e)}
    try:
        r = subprocess.run(['/usr/sbin/spctl', '--assess', '--type', 'execute', str(app)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, env=dict(os.environ, LC_ALL='C'))
        diag['spctl_app'] = {'rc': r.returncode, 'out': r.stdout[-500:],
                             'note': 'RC=3 expected for this envelope family; not a GO criterion'}
    except Exception as e:
        diag['spctl_app'] = {'error': str(e)}
    return diag


def verify_offline_provenance(pkg: Path, app: Path, workdir: Path | None = None) -> dict:
    """Full C-1 chain without attaching any DMG and without running PKG scripts.
    I-5: PKG/app live under /var/tmp — fail early if inputs are missing.
    I-2: space budget before expand-full. I-4: cleanup errors are reported, not swallowed."""
    if not pkg.is_file():
        raise ValueError('I5_PKG_AUSENTE: %r (dependencia de /var/tmp; no se reconstruye)' % pkg)
    if not app.is_dir() or app.is_symlink():
        raise ValueError('I5_APP_AUSENTE: %r' % app)
    # space: expand needs ~PKG size free next to workdir
    pkg_size = pkg.stat().st_size
    owner = workdir or Path(tempfile.mkdtemp(prefix='ot07_pkg_chain_'))
    created = workdir is None
    cleanup_error = None
    try:
        # I-2: refuse expand if the volume cannot hold the expansion
        st = os.statvfs(str(owner))
        avail = st.f_bavail * st.f_frsize
        if avail < pkg_size + (1 << 30):
            raise ValueError('I2_ESPACIO_INSUFICIENTE expand: avail=%d need=%d' % (avail, pkg_size + (1 << 30)))
        pkg_id = verify_pkg_identity(pkg)
        expand_root = owner / 'expand'
        expand_root.mkdir(mode=0o700, exist_ok=True)
        expanded = expand_pkg(pkg, expand_root)
        payload_app = expanded / 'Payload' / 'Applications' / 'Install macOS Sonoma.app'
        if not payload_app.is_dir():
            raise ValueError('payload sin app en la ruta esperada')
        tree = verify_payload_matches_app(payload_app, app)
        dmg = verify_dmg_anchor(expanded, app)
        cim = app / 'Contents/Resources/createinstallmedia'
        cim_id = verify_cim_signature(cim)
        basics = verify_bundle_basics(app)
        if sha256_file(pkg) != PKG_SHA256:
            raise ValueError('PKG cambio durante la derivacion')
        return {
            'ok': True,
            'pkg': pkg_id,
            'payload_vs_app': tree,
            'dmg': dmg,
            'cim': cim_id,
            'basics': basics,
            'envelope_codesign_app': 'expected RC=1 obsolete omit rules; not required for GO',
        }
    finally:
        if created and owner.exists():
            try:
                shutil.rmtree(owner)
            except OSError as e:
                cleanup_error = e
        if cleanup_error is not None:
            raise RuntimeError('I4_LIMPIEZA_FALLIDA %r; conservar diagnostico en %r'
                               % (cleanup_error, owner)) from cleanup_error


def main():
    dmg = APP / 'Contents/SharedSupport/SharedSupport.dmg'
    cim = APP / 'Contents/Resources/createinstallmedia'
    verify_bundle_basics(APP)
    verify_cim_signature(cim)
    report = verify_offline_provenance(PKG_RUTA, APP)
    subprocess.run(['/usr/bin/hdiutil', 'verify', str(dmg)], check=True)
    report['metadata'] = read_dmg(dmg)
    report['diagnostic'] = diagnostic_signatures(APP, cim)
    print('SONOMA_VERIFICADO: ' + json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('INSTALADOR_NO_VERIFICADO: ' + str(e), file=sys.stderr)
        sys.exit(1)
