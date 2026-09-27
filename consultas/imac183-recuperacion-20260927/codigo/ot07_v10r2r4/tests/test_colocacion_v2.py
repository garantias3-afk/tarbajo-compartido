#!/usr/bin/env python3
"""Synthetic placement tests for colocar_candidato.sh v3 (v10r2r1). Never /Applications."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / 'colocacion_v2' / 'colocar_candidato.sh'
HELPER = BASE / 'place_helper.py'


def build_fixture(td: Path, c5='aceptar_usuario'):
    pkg = td / 'cand' / 'InstallAssistant.pkg'
    pkg.parent.mkdir(parents=True)
    pkg.write_bytes(b'abc')
    app_src = td / 'cand' / 'extraida' / 'Install macOS Sonoma.app'
    (app_src / 'Contents' / 'SharedSupport').mkdir(parents=True)
    (app_src / 'Contents' / 'SharedSupport' / 'SharedSupport.dmg').write_bytes(b'D' * 100)
    (app_src / 'Contents' / 'file.txt').write_text('payload')
    apps = td / 'Applications'
    apps.mkdir()
    # reference inventory of origen
    sys.path.insert(0, str(BASE))
    import place_helper as ph
    inv_ref = td / 'inv_ref.json'
    import json
    inv_ref.write_text(json.dumps(ph.inventory_tree(app_src), sort_keys=True))
    stub = td / 'stubs'
    stub.mkdir()
    (stub / 'pkgutil').write_text(
        '#!/bin/bash\necho "Status: signed Apple Software"\necho "3. Apple Root CA"\nexit 0\n')
    (stub / 'pkgutil').chmod(0o755)
    import hashlib
    real = hashlib.sha256(b'abc').hexdigest()
    script = SRC.read_text()
    script = script.replace('set -uo pipefail', 'set -uo pipefail\nset +e')
    script = script.replace(f'HELPER="{BASE}/place_helper.py"', f'HELPER="{HELPER}"')
    script = re.sub(r'HELPER="[^"]+"', f'HELPER="{HELPER}"', script)
    script = re.sub(r'PKG="[^"]+"', f'PKG="{pkg}"', script)
    script = re.sub(r'PKG_BYTES=\d+', 'PKG_BYTES=3', script)
    script = re.sub(r'PKG_SHA256="[^"]+"', f'PKG_SHA256="{real}"', script)
    script = re.sub(r'ORIGEN="[^"]+"', f'ORIGEN="{app_src}"', script)
    script = re.sub(r'DESTINO="[^"]+"', f'DESTINO="{apps}/Install macOS Sonoma.app"', script)
    script = re.sub(r'INVENTARIO_REF="[^"]+"', f'INVENTARIO_REF="{inv_ref}"', script)
    script = script.replace('export PATH=/usr/bin:/bin:/usr/sbin:/sbin',
                            f'export PATH={stub}:/usr/bin:/bin:/usr/sbin:/sbin')
    script = script.replace('/usr/sbin/pkgutil', f'{stub}/pkgutil')
    script = script.replace('mktemp -d /private/var/tmp/ot07_staging',
                            f'mktemp -d {td}/staging_parent_must_exist')
    # ensure staging parent dir exists for mktemp
    (td / 'staging_parent_must_exist').mkdir(exist_ok=True)
    sh = td / 'run.sh'
    sh.write_text(script)
    sh.chmod(0o755)
    env = dict(os.environ, OT07_MODO_PROTECCION=c5)
    return sh, apps, pkg, app_src, env


class ColocacionV3Tests(unittest.TestCase):
    def run_script(self, td, c5='aceptar_usuario'):
        sh, apps, pkg, app_src, env = build_fixture(td, c5=c5)
        r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True,
                           timeout=30, env=env)
        return r, apps, pkg, app_src

    def test_success_places_app(self):
        with tempfile.TemporaryDirectory() as t:
            r, apps, pkg, app_src = self.run_script(Path(t))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('COLOCADO_VERIFICADO', r.stdout)
            self.assertTrue((apps / 'Install macOS Sonoma.app' / 'Contents' / 'file.txt').exists())

    def test_c5_default_blocks_before_any_destination(self):
        with tempfile.TemporaryDirectory() as t:
            r, apps, pkg, app_src = self.run_script(Path(t), c5='REQUIERE_DECISION_C5')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('C5_NO_DECIDIDA', r.stderr)
            self.assertFalse((apps / 'Install macOS Sonoma.app').exists())

    def test_c5_unknown_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            r, apps, pkg, app_src = self.run_script(Path(t), c5='nada')
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((apps / 'Install macOS Sonoma.app').exists())

    def test_pkg_missing_fails_before_place(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            sh, apps, pkg, app_src, env = build_fixture(td)
            pkg.unlink()
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((apps / 'Install macOS Sonoma.app').exists())

    def test_destino_preexistente_no_sobrescribe(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            sh, apps, pkg, app_src, env = build_fixture(td)
            dest = apps / 'Install macOS Sonoma.app'
            dest.mkdir()
            (dest / 'OTHER').write_text('keep')
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual((dest / 'OTHER').read_text(), 'keep')

    def test_inventario_alterado_falla(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            sh, apps, pkg, app_src, env = build_fixture(td)
            (app_src / 'Contents' / 'file.txt').write_text('tampered')
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((apps / 'Install macOS Sonoma.app').exists())

    def test_no_pkg_scripts_executed(self):
        body = '\n'.join(l for l in SRC.read_text().splitlines() if not l.strip().startswith('#'))
        for bad in ('startosinstall', 'postinstall.sh', 'hdiutil attach', 'mv -n'):
            self.assertNotIn(bad, body)

    def test_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            sh, apps, pkg, app_src, env = build_fixture(td)
            real = td / 'realapps'
            real.mkdir()
            apps.rmdir()
            apps.symlink_to(real)
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((real / 'Install macOS Sonoma.app').exists())


if __name__ == '__main__':
    unittest.main()
