#!/usr/bin/env python3
"""v10r2r1 tests: C-5 gate before effects, rename_excl never nests, exact inventory."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import place_helper as ph  # noqa: E402

DESTINO_SCRIPT = BASE / 'colocacion_v2' / 'colocar_candidato.sh'


class C5GateTests(unittest.TestCase):
    def test_unknown_policy_fails(self):
        with self.assertRaises(ValueError):
            ph.check_c5_policy('')

    def test_default_blocks_before_effects(self):
        with self.assertRaises(ValueError) as c:
            ph.check_c5_policy('REQUIERE_DECISION_C5')
        self.assertIn('C5_NO_DECIDIDA', str(c.exception))

    def test_root_known_but_not_implemented_blocks(self):
        with self.assertRaises(ValueError):
            ph.check_c5_policy('root')
        self.assertEqual(ph.check_c5_policy('aceptar_usuario')['gate'], 'passed_before_effects')

    def test_script_requires_gate_before_ditto_or_move(self):
        src = DESTINO_SCRIPT.read_text()
        i_gate = src.find('c5-gate')
        i_ditto = src.find('/usr/bin/ditto')
        i_move = src.find('rename-excl')
        self.assertGreater(i_gate, 0)
        self.assertLess(i_gate, i_ditto)
        self.assertLess(i_gate, i_move)

    def test_default_mode_variable_blocks(self):
        # script defaults to REQUIERE_DECISION_C5
        self.assertIn('OT07_MODO_PROTECCION:-REQUIERE_DECISION_C5', DESTINO_SCRIPT.read_text())


class RenameExclTests(unittest.TestCase):
    def test_moves_when_absent(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / 'src'; src.mkdir(); (src / 'f').write_text('x')
            dst = t / 'dst'
            self.assertEqual(ph.rename_excl(str(src), str(dst)), 0)
            self.assertTrue((dst / 'f').exists())
            self.assertFalse(src.exists())

    def test_eexist_on_directory_destination(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / 'src'; src.mkdir(); (src / 'f').write_text('x')
            dst = t / 'dst'; dst.mkdir(); (dst / 'OTHER').write_text('keep')
            self.assertEqual(ph.rename_excl(str(src), str(dst)), 17)
            # NEVER nested
            self.assertFalse((dst / 'src').exists())
            self.assertFalse((dst / 'Install macOS Sonoma.app').exists())
            self.assertEqual((dst / 'OTHER').read_text(), 'keep')
            self.assertTrue((src / 'f').exists())

    def test_eexist_on_file_destination(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / 'src'; src.mkdir(); (src / 'f').write_text('x')
            dst = t / 'dst'; dst.write_text('file')
            self.assertEqual(ph.rename_excl(str(src), str(dst)), 17)
            self.assertEqual(dst.read_text(), 'file')

    def test_eexist_on_symlink_destination_no_follow(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / 'src'; src.mkdir(); (src / 'f').write_text('x')
            other = t / 'other'; other.mkdir(); (other / 'keep').write_text('k')
            dst = t / 'dst'; dst.symlink_to(other)
            rc = ph.rename_excl(str(src), str(dst))
            self.assertIn(rc, (17, 1))  # EEXIST or ELOOP — never write inside other
            self.assertEqual((other / 'keep').read_text(), 'k')
            self.assertFalse((other / 'f').exists())
            self.assertTrue((src / 'f').exists())

    def test_two_contendientes_un_ganador(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            s1 = t / 's1'; s1.mkdir(); (s1 / 'a').write_text('1')
            s2 = t / 's2'; s2.mkdir(); (s2 / 'a').write_text('2')
            dst = t / 'dst'
            r1 = ph.rename_excl(str(s1), str(dst))
            r2 = ph.rename_excl(str(s2), str(dst))
            self.assertEqual(sorted([r1, r2]), [0, 17])
            winner = (dst / 'a').read_text()
            self.assertIn(winner, ('1', '2'))


class InventoryTests(unittest.TestCase):
    def test_inventory_includes_dirs_and_symlinks(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / 'r'
            (root / 'd').mkdir(parents=True)
            (root / 'd' / 'f').write_text('a')
            os.symlink('d/f', root / 'l')
            inv = ph.inventory_tree(root)
            self.assertEqual(inv['counts']['regular'], 1)
            self.assertEqual(inv['counts']['directory'], 1)
            self.assertEqual(inv['counts']['symlink'], 1)
            self.assertIn('d', inv['entries'])

    def test_inventory_detects_same_size_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            a, b = t / 'a', t / 'b'
            for r in (a, b):
                r.mkdir(); (r / 'f').write_text('AAAA')
            (b / 'f').write_text('BBBB')
            self.assertFalse(ph.inventories_equal(ph.inventory_tree(a), ph.inventory_tree(b)))

    def test_inventory_detects_extra_dir(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            a, b = t / 'a', t / 'b'
            for r in (a, b):
                r.mkdir(); (r / 'f').write_text('A')
            (b / 'extra').mkdir()
            self.assertFalse(ph.inventories_equal(ph.inventory_tree(a), ph.inventory_tree(b)))


class ScriptStatics(unittest.TestCase):
    def test_uses_rename_excl_not_mv_n(self):
        src = DESTINO_SCRIPT.read_text()
        self.assertIn('rename-excl', src)
        self.assertNotIn('mv -n', src)

    def test_inventory_not_shasum_c_of_app_manifest(self):
        src = DESTINO_SCRIPT.read_text()
        body = '\n'.join(l for l in src.splitlines() if not l.strip().startswith('#'))
        self.assertIn('compare-inv', body)
        self.assertIn('inv_extracted_app.json', body)
        self.assertNotIn('APP_MANIFIESTO', body)
        self.assertNotIn('shasum --check', body)

    def test_space_is_live_via_helper_not_constant(self):
        src = DESTINO_SCRIPT.read_text()
        self.assertIn('space-check', src)
        helper = (BASE / 'place_helper.py').read_text()
        self.assertIn('du', helper)
        self.assertIn('df', helper)
        self.assertIn('parse_positive_int', helper)


if __name__ == '__main__':
    unittest.main()
