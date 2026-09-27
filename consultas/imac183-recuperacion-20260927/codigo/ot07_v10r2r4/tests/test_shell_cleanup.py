"""Exercise actual Bash cleanup bodies with wait/helper doubles; no signals.
Handlers are invoked as shell code, not by delivering INT/TERM. This verifies
handler->EXIT->cleanup sequencing, not native signal delivery or native wait.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
BASE=Path(__file__).resolve().parents[1]

class ShellCleanup(unittest.TestCase):
    def supervisor(self,wait_rc=0,pending=False,handler='TERM'):
        source=(BASE/'CREAR_PEN_BOOTEO.sh').read_text()
        cleanup=source[source.index('cleanup(){'):source.index('trap cleanup EXIT')]
        match=next((m for m in re.finditer(r"^trap '(exit [0-9]+)' ([A-Z ]+)$",source,re.M) if handler in m.group(2).split()),None)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lock=root/'lock';lock.mkdir();run=root/'run';(run/'build').mkdir(parents=True)
            (run/'build/process-ledger.json').write_text('{}')
            helper=root/'helper';helper.write_text('#!/bin/bash\necho check >> "$RUN/events"\nexit '+str(int(pending))+'\n');helper.chmod(0o700)
            script='set -uo pipefail\n'+''.join(k+'='+shlex.quote(str(v))+'\n' for k,v in dict(RUN=run,LOCK=lock,DIR=root,PY=helper,CHILD=100,KEEP_LOCK=0).items())
            script+='export RUN\nwait(){ echo wait >> "$RUN/events"; return '+str(wait_rc)+'; }\n'
            script+='rmdir(){ echo release >> "$RUN/events"; /bin/rmdir "$@"; }\n'
            script+=cleanup+'\ntrap cleanup EXIT\n'+match.group(1)+'\n'
            r=subprocess.run(['/bin/bash','-c',script],capture_output=True,text=True,timeout=10)
            events=(run/'events').read_text().splitlines()
            self.assertEqual(r.returncode,130 if handler=='INT' else 143,r.stderr)
            self.assertEqual(int((run/'exit_code').read_text()),r.returncode)
            self.assertEqual(events[:2],['wait','check'])
            keep=wait_rc==127 or pending
            self.assertEqual(lock.exists(),keep)
            self.assertEqual('release' in events,not keep)
            return r
    def test_int_handler_waits_before_release(self): self.supervisor(handler='INT')
    def test_term_handler_waits_before_release(self): self.supervisor(handler='TERM')
    def test_hup_handler_waits_before_release(self): self.supervisor(handler='HUP')
    def test_ambiguous_wait_127_preserves_lock(self):self.supervisor(wait_rc=127)
    def test_nonzero_child_exit_is_reaped_before_release(self):self.supervisor(wait_rc=7)
    def test_pending_ledger_preserves_lock(self):self.supervisor(pending=True)
    def test_constructor_cleanup_thaws_before_wait_without_real_signals(self):
        source=(BASE/'construir_efi.sh').read_text()
        cleanup=source[source.index('cleanup(){'):source.index('trap cleanup EXIT')]
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);events=root/'events'
                prefix='set -uo pipefail\nPID=100\nLEDGER=fixture\n'
                prefix+='EVENTS='+shlex.quote(str(events))+'\n'
                prefix+='thaw(){ echo thaw >> "$EVENTS"; return '+str(int(fail))+'; }\n'
                prefix+='wait(){ echo wait >> "$EVENTS"; return 0; }\n'
                r=subprocess.run(['/bin/bash','-c',prefix+cleanup+'\ntrap cleanup EXIT\nexit 143\n'],capture_output=True,text=True,timeout=10)
                self.assertEqual(events.read_text().splitlines(),['thaw'] if fail else ['thaw','wait'])
                self.assertEqual(r.returncode,1 if fail else 143)
