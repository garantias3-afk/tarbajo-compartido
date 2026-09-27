"""Probe-loop cadence from the real constructor text. No OCLP, signals, or long sleeps."""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCRIPT = (BASE / 'construir_efi.sh').read_text()
START = SCRIPT.index('# PROBE_LOOP_START')
END = SCRIPT.index('# PROBE_LOOP_END')
LOOP = SCRIPT[START:END]
# H-1: product allowlist in construir_efi.sh (do not widen it)
ALLOWLIST = ('/tmp/', '/private/tmp/', '/var/folders/', '/private/var/folders/')


class Probe(unittest.TestCase):
    def run_loop(self, iters, alive_fail=False, ready=False):
        # H-1: positive fixture lives under a product-ALLOWED root (/private/tmp).
        # Documented exception: this test does not inherit trial TMPDIR; the rest
        # of the suite does. Negative case below proves allowlist rejection.
        root = Path('/private/tmp') / ('ot07_r4_probe_%d' % os.getpid())
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            return self._run_loop_inner(root, iters, alive_fail, ready)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _run_loop_inner(self, root, iters, alive_fail, ready):
        log = root / 'oclp_build.log'
        counts = root / 'counts'
        build = root / 'OpenCore-Build'
        if ready:
            product = build / 'System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers'
            product.mkdir(parents=True)
            (build / 'EFI/OC').mkdir(parents=True)
            (build / 'EFI/OC/OpenCore.efi').write_bytes(b'x')
            (build / 'boot.efi').write_bytes(b'x')
            (product / 'Product.efi').write_bytes(b'x')
            log.write_text('has been built at: %s\n' % build)
        else:
            log.write_text('')
        helper = r'''
fail(){ echo "FAIL:$*" >&2; exit 1; }
process(){
  echo "$1" >> "$COUNTS"
  if [ "$1" = alive ] && [ "$FAIL_ALIVE" = 1 ]; then exit 1; fi
  return 0
}
wait(){ echo wait >> "$COUNTS"; return 0; }
'''
        script = helper + LOOP + '\necho REACHED_FREEZE\n'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', COUNTS=str(counts),
                   LOG=str(log), LEDGER='ledger', PID='100',
                   FAIL_ALIVE='1' if alive_fail else '0',
                   OT07_PROBE_ITERS=str(iters), OT07_PROBE_ALIVE_EVERY='20',
                   OT07_PROBE_SLEEP='0')
        r = subprocess.run(['/bin/bash', '-c', script], capture_output=True,
                           text=True, env=env, timeout=15)
        alive = counts.read_text().splitlines().count('alive') if counts.exists() else 0
        return r, alive

    def test_periodic_alive_is_sparser_than_iterations(self):
        r, alive = self.run_loop(40)
        self.assertNotEqual(r.returncode, 0, r.stderr)
        self.assertIn('SONDEO_AGOTADO', r.stderr)
        self.assertNotIn('REACHED_FREEZE', r.stdout)
        self.assertEqual(alive, 3)
        self.assertLess(alive, 40)
        self.assertNotIn('kill -0', SCRIPT)

    def test_ready_build_still_rechecks_identity_before_freeze(self):
        r, alive = self.run_loop(40, ready=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('REACHED_FREEZE', r.stdout)
        self.assertEqual(alive, 1)

    def test_alive_failure_does_not_reach_freeze(self):
        r, alive = self.run_loop(40, alive_fail=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('REACHED_FREEZE', r.stdout)
        self.assertEqual(alive, 1)

    def test_success_gate_is_stricter_than_cleanup(self):
        crear = (BASE / 'CREAR_PEN_BOOTEO.sh').read_text()
        cleanup = crear[crear.index('cleanup(){'):crear.index('trap cleanup EXIT')]
        gate = crear[crear.index('run_child /bin/bash "$DIR/construir_efi.sh"'):crear.index('guard prepare')]
        self.assertIn('ot07_process.py" check "', cleanup)
        self.assertNotIn('check-build', cleanup)
        self.assertIn('check-build', gate)
        self.assertLess(crear.index('check-build'), crear.index('eraseDisk JHFS+'))

    def test_allowlist_rejects_tmpdir_outside(self):
        """Negative: fixture under /var/tmp (not allowlisted) must be rejected by product rule."""
        case = SCRIPT[SCRIPT.index('case "$SRC" in'):SCRIPT.index('*) wait "$PID"')]
        self.assertIn('/tmp/*OpenCore-Build', case)
        self.assertIn('/private/tmp/*OpenCore-Build', case)
        self.assertIn('/var/folders/*OpenCore-Build', case)
        self.assertIn('/private/var/folders/*OpenCore-Build', case)
        # /var/tmp must NOT be allowlisted
        self.assertNotIn('/var/tmp/*OpenCore-Build', case)
        sample = '/var/tmp/ot07_r4_probe_x/OpenCore-Build'
        self.assertFalse(sample.startswith(ALLOWLIST))
