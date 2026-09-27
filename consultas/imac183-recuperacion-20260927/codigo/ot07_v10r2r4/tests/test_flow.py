"""Shell lifecycle simulations with explicit tool substitution; not native integration."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
SIM=BASE/'tests/sim_tool.py'


class Flow(unittest.TestCase):
    def run_case(self,case):
        with tempfile.TemporaryDirectory(prefix='ot07_flow_') as tmp:
            root=Path(tmp).resolve()
            def shim(name,kind):
                p=root/name
                p.write_text('#!/bin/bash\nexec /usr/bin/python3 -B '+shlex.quote(str(SIM))+' '+kind+' "$@"\n')
                p.chmod(0o700); return str(p)
            disk=shim('diskutil','diskutil'); version=shim('PlistBuddy','version')
            ditto=shim('ditto','ditto')
            shim('construir_efi.sh','build'); shim('descargar_sonoma.sh','verify-installer')
            app=root/'installer'; (app/'Contents/Resources').mkdir(parents=True)
            shim('installer/Contents/Resources/createinstallmedia','cim')
            (root/'guard.py').write_text('import runpy,sys\nsys.argv.insert(1,"guard")\nrunpy.run_path('+repr(str(SIM))+',run_name="__main__")\n')
            s=(BASE/'CREAR_PEN_BOOTEO.sh').read_text()
            s=s.replace('#!/bin/bash\n','#!/bin/bash\nid(){ echo 0; }\nsync(){ :; }\n',1)
            # H-1: tokenize product /var/tmp/ot07_ BEFORE any real path is inserted
            n_tok = s.count('/var/tmp/ot07_')
            s = s.replace('/var/tmp/ot07_', '__OT07_TMPROOT__/ot07_')
            assert s.count('__OT07_TMPROOT__/ot07_') == n_tok, 'placeholder cardinality'
            s = s.replace('/var/run/ot07-kingston.lock','__OT07_LOCK__')
            # now insert concrete paths (root may itself contain /var/tmp/ot07_)
            s=s.replace('/usr/sbin/diskutil',disk).replace('/usr/libexec/PlistBuddy',version)
            s=s.replace('ditto --norsrc',shlex.quote(ditto)+' --norsrc')
            s=s.replace('/Applications/Install macOS Sonoma.app',str(app)).replace('$DIR/ot07_guard.py','$DIR/guard.py')
            s = s.replace('__OT07_LOCK__', str(root/'lock'))
            s = s.replace('__OT07_TMPROOT__', str(root).rstrip('/'))
            # assert no residual double-substitution
            assert '/private/private/' not in s, 'doble sustitucion residual'
            assert '__OT07_' not in s, 'placeholder sin resolver'
            script=root/'run.sh'; script.write_text(s)
            (root/'ot07_process.py').write_bytes((BASE/'ot07_process.py').read_bytes())
            if case=='existing-lock': (root/'lock').mkdir()
            entries=[]
            for p in root.rglob('*'):
                if p.is_file(): entries.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix())
            (root/'SHA256SUMS.txt').write_text('\n'.join(entries)+'\n')
            env=dict(os.environ,OT07_SIM_ROOT=str(root),OT07_SIM_CASE=case,PYTHONDONTWRITEBYTECODE='1')
            r=subprocess.run(['/bin/bash',str(script),'/dev/disk99','11111111-2222-4333-8444-555555555555'],
                             input=('CANCELAR\n' if case=='wrong-confirmation' else 'CREAR-BOOTEO\n'),text=True,capture_output=True,env=env,timeout=30)
            events=(root/'events').read_text() if (root/'events').exists() else ''
            exits=list(root.glob('ot07_v10.*/exit_code'))
            if case=='existing-lock':
                self.assertEqual(exits,[])
                self.assertTrue((root/'lock').exists())
                return r,events
            self.assertEqual(len(exits),1,r.stdout+r.stderr)
            self.assertEqual(int(exits[0].read_text()),r.returncode)
            run=exits[0].parent
            if case=='bindings-fails':
                self.assertFalse((run/'partitions.after_erase.json').exists())
            if case=='installer-empty':
                self.assertTrue((run/'installed-diagnostico.json').is_file())
            if case=='binding-before-cleanup':
                self.assertNotIn('ditto --norsrc',events)
            self.assertEqual((root/'lock').exists(),case in ('unresolved-ledger','missing-ledger','false-clean-build','empty-capture','root-birth-mismatch','descendant-only'))
            return r,events

    def test_success_with_C1_C2_and_readback(self):
        r,e=self.run_case('success')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('MEDIO_CREADO_INTEGRIDAD_VERIFICADA',r.stdout)
        self.assertIn('ARRANQUE_FISICO: NO_PROBADO',r.stdout)
        self.assertIn('diskutil mount /dev/disk99s2',e)
        self.assertIn('diskutil mount readOnly',e)
        self.assertGreaterEqual(e.count('guard mountpoint'),7)

    def test_pre_erase_failures_leave_disk_untouched(self):
        for case in ('identity-change','oversized','wrong-confirmation','build-fails','payload-tampered','installer-invalid'):
            with self.subTest(case=case):
                r,e=self.run_case(case)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('diskutil eraseDisk',e)
                self.assertNotIn('MEDIO_CREADO_INTEGRIDAD_VERIFICADA',r.stdout)

    def test_post_erase_failures_never_report_success(self):
        for case in ('wrong-efi-mount','small-esp','copy-corrupt','writable-readback','unmount-fails','cim-fails','erase-fails','guid-change-post-cim','readback-corrupt','installer-empty','copy-fails','bindings-fails','binding-before-cleanup'):
            with self.subTest(case=case):
                r,e=self.run_case(case)
                self.assertNotEqual(r.returncode,0)
                self.assertIn('diskutil eraseDisk',e)
                self.assertNotIn('MEDIO_CREADO_INTEGRIDAD_VERIFICADA',r.stdout)
                if case in ('wrong-efi-mount','small-esp'):
                    self.assertNotIn('cim --volume',e)

    def test_existing_lock_blocks_before_identity_and_erase(self):
        r,e=self.run_case('existing-lock')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(e,'')

    def test_unresolved_constructor_ledger_keeps_lock(self):
        r,e=self.run_case('unresolved-ledger')
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('diskutil eraseDisk',e)
        self.assertIn('BLOQUEO_CONSERVADO',r.stderr)

    def test_constructor_success_requires_a_closed_ledger_before_erase(self):
        for case in ('missing-ledger','false-clean-build','empty-capture','root-birth-mismatch','descendant-only'):
            with self.subTest(case=case):
                r,e=self.run_case(case)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('diskutil eraseDisk',e)
                self.assertIn('BLOQUEO_CONSERVADO',r.stderr)
