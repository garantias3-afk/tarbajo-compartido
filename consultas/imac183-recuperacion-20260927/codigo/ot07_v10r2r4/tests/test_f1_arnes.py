#!/usr/bin/env python3
"""F-1/I-3 harness: inject du/df failures into the REAL helper (private copy),
count call sites, prove the gate is reached, and prove the test can fail (sensitivity)."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
HELPER = BASE / 'place_helper.py'
SCRIPT = BASE / 'colocacion_v2' / 'colocar_candidato.sh'


def make_helper_copy(td: Path, *, du_rc=0, du_out='4096', df_rc=0, df_out=None) -> Path:
    """Private copy of place_helper.py with du/df replaced by stubs that log calls."""
    src = HELPER.read_text()
    stub = td / 'bin'
    stub.mkdir(exist_ok=True)
    log = td / 'calls.log'
    log.write_text('')
    (stub / 'du').write_text(
        '#!/bin/bash\necho "du $*" >> %s\n'
        'echo %s\nexit %s\n' % (log, du_out, du_rc))
    (stub / 'df').write_text(
        '#!/bin/bash\necho "df $*" >> %s\n'
        'if [ %s -ne 0 ]; then echo "df-fail" >&2; exit %s; fi\n'
        'echo "Filesystem 1024-blocks Used Available Capacity Mounted"\n'
        'echo "x 1 1 %s 1%% /p"\n' % (log, df_rc, df_rc, df_out if df_out is not None else '999999999'))
    for n in ('du', 'df'):
        (stub / n).chmod(0o755)
    # inject: measure_space_need/avail call stubs via PATH
    src = src.replace("subprocess.run(['/usr/bin/du', '-sk', src]",
                      "subprocess.run(['du', '-sk', src]")
    src = src.replace("subprocess.run(['/bin/df', '-k', dirpath]",
                      "subprocess.run(['df', '-k', dirpath]")
    # require exactly one injection point for each
    assert src.count("subprocess.run(['du', '-sk', src]") == 1, 'du injection not unique'
    assert src.count("subprocess.run(['df', '-k', dirpath]") == 1, 'df injection not unique'
    out = td / 'place_helper_inject.py'
    out.write_text(src)
    return out, stub, log


def run_helper(helper: Path, stub: Path, *args):
    env = dict(os.environ, PATH=f'{stub}:/usr/bin:/bin:/usr/sbin:/sbin')
    return subprocess.run([sys.executable, '-B', str(helper), *args],
                          capture_output=True, text=True, env=env, timeout=20)


class F1_DuInjection(unittest.TestCase):
    def test_du_rc1_with_number_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir(); (src / 'f').write_bytes(b'x')
            helper, stub, log = make_helper_copy(td, du_rc=1, du_out='4096')
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('du', r.stderr.lower())
            self.assertEqual(log.read_text().count('du '), 1, 'du llamado exactamente una vez')

    def test_du_rc0_empty_output_fails(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir()
            helper, stub, log = make_helper_copy(td, du_rc=0, du_out='')
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)

    def test_du_rc1_empty_fails(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir()
            helper, stub, log = make_helper_copy(td, du_rc=1, du_out='')
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)

    def test_df_rc1_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir(); (src / 'f').write_bytes(b'x')
            helper, stub, log = make_helper_copy(td, df_rc=1, df_out='999')
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)

    def test_df_non_numeric_fails(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir()
            helper, stub, log = make_helper_copy(td, df_out='abc')
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)

    def test_space_insufficient_vs_sufficient(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            src = td / 'd'; src.mkdir(); (src / 'f').write_bytes(b'x')
            helper, stub, log = make_helper_copy(td, du_out='8', df_out='4')  # need 8+2GiB > 4
            r = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r.returncode, 0)
            helper2, stub2, log2 = make_helper_copy(td, du_out='8', df_out='999999999')
            r2 = run_helper(helper2, stub2, 'space-check', str(src), str(td))
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertIn('OK=True', r2.stdout)

    def test_injection_point_unique(self):
        src = HELPER.read_text()
        self.assertEqual(src.count("subprocess.run(['/usr/bin/du'"), 1)
        self.assertEqual(src.count("subprocess.run(['/bin/df'"), 1)


class F1_Sensitivity(unittest.TestCase):
    """If the space rejection is disabled, the corresponding test MUST fail."""

    def test_mutating_space_rejection_breaks_test(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            # 1) baseline: helper with stubs, du ok, df tiny -> should FAIL space-check
            helper, stub, log = make_helper_copy(td, du_out='8', df_out='4')
            src = td / 'd'; src.mkdir()
            r_fail = run_helper(helper, stub, 'space-check', str(src), str(td))
            self.assertNotEqual(r_fail.returncode, 0)
            # 2) mutate ONLY the helper copy: accept any avail
            mutated = td / 'mut.py'
            text = helper.read_text()
            old = 'ok = avail >= need'
            assert text.count(old) == 1, 'mutation point not unique'
            mutated.write_text(text.replace(old, 'ok = True'))
            r_mut = run_helper(mutated, stub, 'space-check', str(src), str(td))
            self.assertEqual(r_mut.returncode, 0, 'mutacion no detectada: el test no acredita la guarda')
            # 3) therefore the real test would fail on the mutant — that IS the sensitivity proof
            #    recorded as: expected FAIL on mutant, observed FAIL.
            #    hash of mutant for the report
            h = hashlib.sha256(mutated.read_bytes()).hexdigest()
            (td / 'sensitivity.txt').write_text(
                'fixture=place_helper_inject.py\nmutation=ok=True\n'
                'baseline_rc=%d mutant_rc=%d sha256_mut=%s\n'
                'expected=mutant rc0 (test would fail) observed=rc0\n' % (
                    r_fail.returncode, r_mut.returncode, h))
            self.assertIn('mutant_rc=0', (td / 'sensitivity.txt').read_text())


class F1_PositiveControl(unittest.TestCase):
    def test_arnes_puede_llegar_a_publicacion(self):
        """Positive synthetic: with aceptar_usuario + tiny tree + stubs, script can reach COLOCADO."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            import place_helper as ph
            apps = td / 'Applications'; apps.mkdir()
            pkg = td / 'p.pkg'; pkg.write_bytes(b'abc')
            app = td / 'Install macOS Sonoma.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents' / 'f').write_text('x')
            (app / 'Contents' / 'SharedSupport').mkdir()
            (app / 'Contents' / 'SharedSupport' / 'SharedSupport.dmg').write_bytes(b'D' * 20)
            inv = td / 'inv.json'
            inv.write_text(__import__('json').dumps(ph.inventory_tree(app), sort_keys=True))
            stub = td / 'stubs'; stub.mkdir()
            (stub / 'pkgutil').write_text(
                '#!/bin/bash\necho "Status: signed Apple Software"\necho "3. Apple Root CA"\nexit 0\n')
            (stub / 'pkgutil').chmod(0o755)
            script = SCRIPT.read_text()
            script = re.sub(r'HELPER="[^"]+"', f'HELPER="{HELPER}"', script)
            script = re.sub(r'PKG="[^"]+"', f'PKG="{pkg}"', script)
            script = re.sub(r'PKG_BYTES=\d+', 'PKG_BYTES=3', script)
            script = re.sub(r'PKG_SHA256="[^"]+"',
                            f'PKG_SHA256="{hashlib.sha256(b"abc").hexdigest()}"', script)
            script = re.sub(r'ORIGEN="[^"]+"', f'ORIGEN="{app}"', script)
            script = re.sub(r'DESTINO="[^"]+"', f'DESTINO="{apps}/Install macOS Sonoma.app"', script)
            script = re.sub(r'INVENTARIO_REF="[^"]+"', f'INVENTARIO_REF="{inv}"', script)
            script = script.replace('set -uo pipefail', 'set -uo pipefail\nset +e')
            script = script.replace('export PATH=/usr/bin:/bin:/usr/sbin:/sbin',
                                    f'export PATH={stub}:/usr/bin:/bin:/usr/sbin:/sbin')
            script = script.replace('/usr/sbin/pkgutil', f'{stub}/pkgutil')
            # force space-check success by huge df via helper stubs
            helper_i, stub_i, log_i = make_helper_copy(td, du_out='8', df_out='999999999')
            script = re.sub(r'HELPER="[^"]+"', f'HELPER="{helper_i}"', script)
            script = script.replace(f'export PATH={stub}:',
                                    f'export PATH={stub_i}:{stub}:')
            sh = td / 'run.sh'; sh.write_text(script); sh.chmod(0o755)
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True,
                               env=dict(os.environ, OT07_MODO_PROTECCION='aceptar_usuario'),
                               timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('COLOCADO_VERIFICADO', r.stdout)
            self.assertTrue((apps / 'Install macOS Sonoma.app' / 'Contents' / 'f').exists())


if __name__ == '__main__':
    unittest.main()
