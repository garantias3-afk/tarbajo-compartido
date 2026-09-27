#!/usr/bin/env python3
"""Tests offline for verificar_instalador v10r2 (C-1 chain). No DMG attach, no PKG scripts."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import verificar_instalador as v  # noqa: E402


def make_app(root: Path, *, with_dmg=True, with_cim=True, extra=None, dmg_bytes=10000000001,
             dmg_sha='a' * 64) -> Path:
    app = root / 'Install macOS Sonoma.app'
    (app / 'Contents' / 'SharedSupport').mkdir(parents=True)
    (app / 'Contents' / 'Resources').mkdir(parents=True)
    (app / 'Contents' / 'Info.plist').write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        b'<plist version="1.0"><dict><key>CFBundleIdentifier</key>'
        b'<string>com.apple.InstallAssistant.macOSSonoma</string></dict></plist>')
    if with_dmg:
        p = app / 'Contents' / 'SharedSupport' / 'SharedSupport.dmg'
        p.write_bytes(b'D' * 100)
        os.truncate(p, dmg_bytes)
    if with_cim:
        c = app / 'Contents' / 'Resources' / 'createinstallmedia'
        c.write_bytes(b'#!/bin/sh\nexit 0\n')
        c.chmod(0o755)
    if extra:
        extra(app)
    return app


class InventoryTests(unittest.TestCase):
    def test_regular_and_symlink_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 't'
            (root / 'sub').mkdir(parents=True)
            (root / 'sub' / 'a.txt').write_text('hello')
            os.symlink('sub/a.txt', root / 'link')
            inv = v.inventory_tree(root)
            self.assertEqual(inv['counts']['regular'], 1)
            self.assertEqual(inv['counts']['symlink'], 1)
            self.assertEqual(inv['entries']['link'], {'type': 'symlink', 'target': 'sub/a.txt'})

    def test_absolute_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 't'
            root.mkdir()
            os.symlink('/etc/passwd', root / 'bad')
            with self.assertRaises(ValueError):
                v.inventory_tree(root)

    def test_dotdot_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 't'
            root.mkdir()
            os.symlink('../outside', root / 'bad')
            with self.assertRaises(ValueError):
                v.inventory_tree(root)

    def test_compare_detects_extra_and_differ(self):
        a = {'entries': {'x': {'type': 'regular', 'size': 1, 'sha256': 'aa'}}}
        b = {'entries': {'x': {'type': 'regular', 'size': 1, 'sha256': 'bb'},
                         'y': {'type': 'directory'}}}
        res = v.compare_trees(a, b)
        self.assertEqual(res['only_in_b'], ['y'])
        self.assertEqual(res['differ'], ['x'])
        self.assertFalse(res['identical'])


class ProvenanceUnitTests(unittest.TestCase):
    def test_pkg_identity_requires_pinned_bytes_and_sha(self):
        with tempfile.TemporaryDirectory() as td:
            pkg = Path(td) / 'p.pkg'
            pkg.write_bytes(b'x')
            with self.assertRaises(ValueError):
                v.verify_pkg_identity(pkg)

    def test_verify_payload_rejects_unexpected_extra(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            pay = td / 'pay'
            app = td / 'app'
            for r in (pay, app):
                (r / 'Contents').mkdir(parents=True)
                (r / 'Contents' / 'f').write_text('a')
            (app / 'Contents' / 'SharedSupport').mkdir()
            (app / 'Contents' / 'SharedSupport' / 'SharedSupport.dmg').write_bytes(b'D' * 10)
            (app / 'Contents' / 'evil').write_text('x')
            with self.assertRaises(ValueError):
                v.verify_payload_matches_app(pay, app)

    def test_verify_payload_accepts_only_postinstall_additions(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            pay = td / 'pay'
            app = td / 'app'
            for r in (pay, app):
                (r / 'Contents').mkdir(parents=True)
                (r / 'Contents' / 'f').write_text('a')
            (app / 'Contents' / 'SharedSupport').mkdir()
            (app / 'Contents' / 'SharedSupport' / 'SharedSupport.dmg').write_bytes(b'D' * 10)
            res = v.verify_payload_matches_app(pay, app)
            self.assertTrue(res['identical_except_postinstall'])

    def test_dmg_anchor_requires_full_sha_match(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            exp = td / 'exp'
            app = td / 'app' / 'Contents' / 'SharedSupport'
            exp.mkdir()
            app.mkdir(parents=True)
            (exp / 'SharedSupport.dmg').write_bytes(b'A' * 20)
            (app / 'SharedSupport.dmg').write_bytes(b'B' * 20)
            with self.assertRaises(ValueError):
                v.verify_dmg_anchor(exp, td / 'app')


class ColocacionScriptTests(unittest.TestCase):
    """Synthetic dry checks of colocar_candidato.sh v2 logic (never /Applications)."""

    def script_src(self):
        return (BASE / 'colocacion_v2' / 'colocar_candidato.sh').read_text()

    def test_c2_pkg_hash_is_compared_not_printed_only(self):
        src = self.script_src()
        self.assertIn('PKG_GOT', src)
        self.assertIn('[ "$PKG_GOT" = "$PKG_SHA256" ]', src)
        self.assertIn('Status: $PKG_STATUS', src)
        self.assertIn('Apple Root CA', src)

    def test_no_pending_placeholder(self):
        self.assertNotIn('PENDING_PKG_SHA256', self.script_src())
        self.assertNotIn('successful', self.script_src())

    def test_c6_c7_c8_c9_present(self):
        src = self.script_src()
        self.assertIn('dirname "$DESTINO"', src)
        self.assertIn('/bin/mkdir "$STAGING"', src)
        self.assertIn('same-fs', src)
        self.assertIn('space-check', src)

    def test_c5_protection_is_proposal_not_active(self):
        src = self.script_src()
        helper = (BASE / 'place_helper.py').read_text()
        self.assertIn('C5_NO_IMPLEMENTADA', helper)
        self.assertIn('NO_ACTIVO', src)
        self.assertIn('chown', src)

    def test_no_pkg_script_execution(self):
        src = self.script_src()
        body = '\n'.join(l for l in src.splitlines() if not l.strip().startswith('#'))
        self.assertTrue(body.strip(), 'body vacio: la asercion no puede fallar')
        self.assertNotIn('installer', body)
        self.assertNotIn('startosinstall', src)
        self.assertNotIn('--expand-full', src)


if __name__ == '__main__':
    unittest.main()
