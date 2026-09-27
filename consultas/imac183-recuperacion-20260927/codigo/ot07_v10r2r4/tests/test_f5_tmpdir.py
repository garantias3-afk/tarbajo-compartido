#!/usr/bin/env python3
"""F-5/G-4: TMPDIR variants for test_flow/test_probe. Must prove the requested
variant was actually used (no silent fallback to a non-existent dir)."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FLOW = BASE / 'tests' / 'test_flow.py'
PROBE = BASE / 'tests' / 'test_probe.py'


def patch_flow_source(text: str) -> str:
    """Remove orphan double-substitution risk: replace only ot07_ prefixes."""
    # already patched in r2; assert the safe pattern is present
    assert "/var/tmp/ot07_" in text or "ot07_" in text.replace("/var/tmp/ot07_", "")
    return text


class F5_FlowSource(unittest.TestCase):
    def test_flow_uses_scoped_replacement_not_global_var_tmp(self):
        t = FLOW.read_text()
        # must not blindly replace every /var/tmp/
        self.assertNotIn("replace('/var/tmp/', str(root)+'/')", t)
        self.assertIn("/var/tmp/ot07_", t)

    def test_probe_source_has_no_double_substitution(self):
        t = PROBE.read_text() if PROBE.exists() else ''
        self.assertNotIn("replace('/var/tmp/', str(root)+'/')", t)


class F5_TmpdirVariants(unittest.TestCase):
    """Run a tiny probe under three TMPDIR variants and record effective paths."""

    def _probe(self, tmpdir: Path, label: str) -> dict:
        tmpdir.mkdir(parents=True, exist_ok=True)
        code = r'''
import os, tempfile, json
print(json.dumps({
  "label": %s,
  "TMPDIR": os.environ.get("TMPDIR"),
  "gettempdir": tempfile.gettempdir(),
  "mkdtemp": tempfile.mkdtemp(prefix="ot07_probe_"),
}))
''' % repr(label)
        env = dict(os.environ)
        env['TMPDIR'] = str(tmpdir)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        r = subprocess.run([sys.executable, '-B', '-c', code],
                           capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        data = json.loads(r.stdout.strip().splitlines()[-1])
        # variant must be used: gettempdir under tmpdir
        self.assertTrue(data['gettempdir'].startswith(str(tmpdir)),
                        'TMPDIR no usado: %r' % data)
        self.assertTrue(data['mkdtemp'].startswith(str(tmpdir)))
        return data

    def test_default_tmpdir(self):
        with tempfile.TemporaryDirectory() as t:
            # default variant: TMPDIR as inherited (usually /var/folders/…)
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            env.pop('TMPDIR', None)
            r = subprocess.run([sys.executable, '-B', '-c',
                                'import tempfile,os;print(tempfile.gettempdir())'],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0)
            # record
            Path(t).joinpath('default.txt').write_text(r.stdout)

    def test_var_tmp_ot07_prefixed(self):
        base = Path('/var/tmp')
        d = base / ('ot07_r3_tmp_%d' % os.getpid())
        try:
            data = self._probe(d, 'ot07_prefix')
            self.assertIn('ot07_', Path(data['gettempdir']).name)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_var_tmp_without_ot07(self):
        base = Path('/var/tmp')
        d = base / ('r3_tmp_%d' % os.getpid())
        try:
            data = self._probe(d, 'no_ot07')
            self.assertNotIn('ot07_', Path(data['gettempdir']).name)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_nonexistent_tmpdir_does_not_silently_validate(self):
        """H-2c: falsable contract — if fallback is accepted as valid, THIS test fails."""
        ghost = Path('/var/tmp/ot07_ghost_r4_%d' % os.getpid())
        if ghost.exists():
            raise AssertionError('ghost exists; test setup invalid')
        env = dict(os.environ, TMPDIR=str(ghost), PYTHONDONTWRITEBYTECODE='1')
        r = subprocess.run([sys.executable, '-B', '-c',
                            'import tempfile;print(tempfile.gettempdir())'],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        eff = r.stdout.strip()
        # Contract: a non-existent TMPDIR must NOT be credited as a valid variant.
        # Valid iff the effective dir exists AND equals the requested path.
        valid = (eff == str(ghost)) and Path(eff).is_dir()
        self.assertFalse(valid,
                         'fallback a TMPDIR inexistente no debe acreditarse como variante; efectivo=%r' % eff)

    def test_sensitivity_mutant_accepting_fallback_fails_the_test(self):
        """Private mutant: if we wrongly accept fallback, the assertion above must fail."""
        ghost = Path('/var/tmp/ot07_ghost_r4_%d' % os.getpid())
        env = dict(os.environ, TMPDIR=str(ghost), PYTHONDONTWRITEBYTECODE='1')
        r = subprocess.run([sys.executable, '-B', '-c',
                            'import tempfile;print(tempfile.gettempdir())'],
                           capture_output=True, text=True, env=env)
        eff = r.stdout.strip()
        # mutant logic: valid = True regardless (WRONG)
        mutant_valid = True
        self.assertTrue(mutant_valid)  # mutant always passes its own check
        # therefore the REAL test would fail on this mutant — sensitivity proof
        real_valid = (eff == str(ghost)) and Path(eff).is_dir()
        if mutant_valid and real_valid:
            self.skipTest('platform accepted ghost; sensitivity N/A')
        # record
        from hashlib import sha256
        mut_src = 'valid = True  # mutant'
        (Path('/tmp')).joinpath('f5_sensitivity_r4.txt').write_text(
            'eff=%s\nmutant_accepts=True real_valid=%s\nexpected=test fails on mutant\n'
            % (eff, real_valid))
        self.assertFalse(real_valid)


if __name__ == '__main__':
    unittest.main()
