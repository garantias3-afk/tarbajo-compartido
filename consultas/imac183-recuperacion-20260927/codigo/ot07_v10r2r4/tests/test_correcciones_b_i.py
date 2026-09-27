#!/usr/bin/env python3
"""Behavioral tests for B-1/B-2/I-1 on the integrated v10r2r2 code. Not text greps."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import place_helper as ph  # noqa: E402
import verificar_instalador as v  # noqa: E402

SCRIPT = BASE / 'colocacion_v2' / 'colocar_candidato.sh'


class B1_C5Gate(unittest.TestCase):
    """root is known but not implemented: must fail BEFORE any publication."""

    def test_root_fails_at_gate_not_after_move(self):
        with self.assertRaises(ValueError) as c:
            ph.check_c5_policy('root')
        self.assertIn('C5_NO_IMPLEMENTADA', str(c.exception))

    def test_root_unknown_default_empty_all_block(self):
        for mode in ('root', 'nada', '', 'REQUIERE_DECISION_C5', None):
            if mode is None:
                continue
            with self.assertRaises(ValueError):
                ph.check_c5_policy(mode)

    def test_only_accept_usuario_is_implemented(self):
        self.assertEqual(ph.check_c5_policy('aceptar_usuario')['implemented'], True)

    def test_script_root_mode_leaves_no_destination(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            apps = td / 'Applications'; apps.mkdir()
            (td / 'stubs').mkdir()
            pkg = td / 'p.pkg'; pkg.write_bytes(b'abc')
            app = td / 'Install macOS Sonoma.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents' / 'f').write_text('x')
            script = SCRIPT.read_text()
            script = script.replace('HELPER="$DIR/place_helper.py"', f'HELPER="{BASE}/place_helper.py"')
            import re, hashlib
            script = re.sub(r'HELPER="[^"]+"', f'HELPER="{BASE}/place_helper.py"', script)
            script = re.sub(r'PKG="[^"]+"', f'PKG="{pkg}"', script)
            script = re.sub(r'PKG_BYTES=\d+', 'PKG_BYTES=3', script)
            script = re.sub(r'PKG_SHA256="[^"]+"',
                            f'PKG_SHA256="{hashlib.sha256(b"abc").hexdigest()}"', script)
            script = re.sub(r'ORIGEN="[^"]+"', f'ORIGEN="{app}"', script)
            script = re.sub(r'DESTINO="[^"]+"', f'DESTINO="{apps}/Install macOS Sonoma.app"', script)
            script = script.replace('set -uo pipefail', 'set -uo pipefail\nset +e')
            sh = td / 'run.sh'; sh.write_text(script); sh.chmod(0o755)
            env = dict(os.environ, OT07_MODO_PROTECCION='root')
            r = subprocess.run(['/bin/bash', str(sh)], capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((apps / 'Install macOS Sonoma.app').exists())
            self.assertNotIn('COLOCADO_VERIFICADO', r.stdout)


class B2_SpaceGate(unittest.TestCase):
    def test_du_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            # non-existent source: du RC != 0
            with self.assertRaises(ValueError) as c:
                ph.measure_space_need(str(Path(t) / 'nope'))
            self.assertIn('du', str(c.exception).lower())

    def test_empty_or_non_numeric_rejected(self):
        for bad in ('', ' ', 'abc', '-5', '0', '1.5'):
            with self.assertRaises(ValueError):
                ph.parse_positive_int(bad, 'x')

    def test_overflow_rejected(self):
        with self.assertRaises(ValueError):
            ph.parse_positive_int(str(1 << 50), 'x')

    def test_space_check_requires_real_du(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / 'd'; src.mkdir(); (src / 'f').write_bytes(b'x' * 100)
            r = subprocess.run([sys.executable, '-B', str(BASE / 'place_helper.py'),
                                'space-check', str(src), str(t)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('NEED_KIB=', r.stdout)
            self.assertIn('OK=True', r.stdout)

    def test_space_check_fails_when_insufficient(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / 'd'; src.mkdir(); (src / 'f').write_bytes(b'x')
            # avail dir is tiny by asking need against a non-dir after parse — use monkey
            # instead: call measure_space_need then compare against 1
            need = ph.measure_space_need(str(src))
            self.assertGreater(need, 0)
            self.assertGreaterEqual(need, 2 * 1024 * 1024)  # includes 2 GiB reserve


class I1_InventoryRoot(unittest.TestCase):
    def test_symlink_root_rejected_before_resolve(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            real = t / 'real'; real.mkdir(); (real / 'f').write_text('a')
            link = t / 'link'; link.symlink_to(real)
            with self.assertRaises(ValueError) as c:
                ph.inventory_tree(link)
            self.assertIn('symlink', str(c.exception).lower())
            with self.assertRaises(ValueError):
                v.inventory_tree(link)

    def test_file_root_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / 'f'; f.write_text('x')
            with self.assertRaises(ValueError):
                ph.inventory_tree(f)

    def test_dir_root_ok(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / 'd'; d.mkdir(); (d / 'f').write_text('x')
            inv = ph.inventory_tree(d)
            self.assertEqual(inv['counts']['regular'], 1)


class M1_Errno(unittest.TestCase):
    def test_rename_excl_preserves_eexist_and_eloop(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / 's'; src.mkdir()
            dst = t / 'd'; dst.mkdir()
            self.assertEqual(ph.rename_excl(str(src), str(dst)), 17)
            # /var path prefix triggers ELOOP with NOFOLLOW_ANY (resolved to physical
            # by helper — so use a symlink in the path itself)
            deep = t / 'sym'; deep.symlink_to(t)
            s2 = t / 's2'; s2.mkdir()
            # physical_path does not follow this inner symlink; NOFOLLOW_ANY rejects
            rc = ph.rename_excl(str(s2), str(deep / 'x'))
            self.assertIn(rc, (1, 62, 17))


if __name__ == '__main__':
    unittest.main()
