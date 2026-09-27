"""Ledger regression tests. Fake process table and signals only; no os.kill."""
import copy
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch
from test_guards import module
p = module('ot07_process')


def record(pid, parent, state='S', birth=None):
    return dict(pid=pid, ppid=parent, state=state, birth=birth or [1790409600,pid], command='OpenCore-Patcher')


class Fake:
    def __init__(self):
        self.table = {100: record(100, 50), 101: record(101, 100), 102: record(102, 101)}
        self.sent = []
        self.fail = None
        self.never_stop = False
    def snapshot(self): return copy.deepcopy(self.table)
    def observe(self, pid):
        if pid not in self.table: raise p.ProcessGone(str(pid))
        return copy.deepcopy(self.table[pid])
    def send(self, pid, sig):
        self.sent.append((pid, sig))
        if self.fail == (pid, sig): raise OSError('simulated signal failure')
        if pid in self.table:
            self.table[pid]['state'] = 'T' if sig == signal.SIGSTOP and not self.never_stop else 'S'
    def pause(self): pass


class Processes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = Fake()
        self.ledger = p.Ledger(Path(self.tmp.name)/'ledger.json', self.fake)
        self.no_signal = patch.object(p.os, 'kill', side_effect=AssertionError('REAL_SIGNAL_FORBIDDEN'))
        self.no_process = patch.object(p.subprocess, 'run', side_effect=AssertionError('REAL_PROCESS_FORBIDDEN'))
        self.no_signal.start(); self.no_process.start()
        self.ledger.init(100, 50)
    def tearDown(self):
        self.no_process.stop(); self.no_signal.stop(); self.tmp.cleanup()
    def test_reparented_child_is_resumed_from_exact_ledger(self):
        self.ledger.freeze()
        self.fake.table[102]['ppid'] = 1
        self.ledger.thaw(); self.ledger.check()
        self.assertEqual(self.fake.sent[-3:], [(102,signal.SIGCONT),(101,signal.SIGCONT),(100,signal.SIGCONT)])
    def test_reused_pid_never_receives_cont(self):
        self.ledger.freeze(); self.fake.table[101]['birth'][1] += 1
        with self.assertRaises(ValueError): self.ledger.thaw()
        with self.assertRaises(ValueError): self.ledger.check()
        self.assertNotIn((101, signal.SIGCONT), self.fake.sent)
    def test_failed_stop_retains_intent_for_cleanup(self):
        self.fake.fail = (101, signal.SIGSTOP)
        with self.assertRaises(OSError): self.ledger.freeze()
        self.assertEqual(self.ledger.data['records'][-1]['status'],'attempting')
        self.fake.fail = None; self.ledger.thaw(); self.ledger.check()
    def test_failed_cont_keeps_lock_condition_and_retries(self):
        self.ledger.freeze(); self.fake.fail = (101, signal.SIGCONT)
        with self.assertRaises(ValueError): self.ledger.thaw()
        with self.assertRaises(ValueError): self.ledger.check()
        self.fake.fail = None; self.ledger.thaw(); self.ledger.check()
    def test_protected_descendant_never_signalled(self):
        self.fake.table[3494] = record(3494,100)
        with self.assertRaises(ValueError): self.ledger.freeze()
        self.ledger.thaw()
        self.assertFalse(any(pid in (3494,3512) for pid,_ in self.fake.sent))
    def test_parent_change_rejected_before_stop(self):
        self.fake.table[100]['ppid'] = 60
        with self.assertRaises(ValueError): self.ledger.freeze()
        self.assertEqual(self.fake.sent,[])
    def test_grandchildren_are_captured_after_parent_stops(self):
        self.ledger.freeze()
        self.assertEqual([x[0] for x in self.fake.sent], [100,101,102])
        self.assertEqual(self.ledger.data['phase'],'frozen')
    def test_timeout_keeps_ledger_until_thaw(self):
        self.fake.never_stop = True
        with self.assertRaises(ValueError): self.ledger.freeze()
        with self.assertRaises(ValueError): self.ledger.check()
        self.ledger.thaw(); self.ledger.check()
    def test_exited_and_zombie_descendants_need_no_signal(self):
        self.ledger.freeze(); del self.fake.table[101]; self.fake.table[102]['state']='Z'
        self.ledger.thaw(); self.ledger.check()
        self.assertEqual(self.fake.sent[-1],(100,signal.SIGCONT))
    def test_ledger_survives_helper_restart(self):
        self.ledger.freeze()
        restarted=p.Ledger(self.ledger.path,self.fake)
        restarted.thaw(); restarted.check()
    def test_parser_keeps_full_command_and_start_time(self):
        rows=p.parse_ps(' 100 50 T Fri Sep 25 12:00:00 2026 /Applications/OpenCore Patcher\n')
        self.assertEqual(rows[100]['command'],'/Applications/OpenCore Patcher')
        self.assertEqual(rows[100]['birth_label'],'Fri Sep 25 12:00:00 2026')
        with self.assertRaises(ValueError): p.parse_ps('bad record')
    def test_native_backend_uses_explicit_read_only_ps(self):
        with patch.object(p.subprocess,'run',return_value=type('R',(),{'stdout':'100 50 T Fri Sep 25 12:00:00 2026 OCLP\n'})()) as run:
            self.assertEqual(p.Native().snapshot()[100]['ppid'],50)
            self.assertEqual(run.call_args[0][0],['/bin/ps','-axo','pid=,ppid=,stat=,lstart=,comm='])

    def test_exec_between_observation_and_stop_keeps_identity(self):
        original=self.fake.send
        def exec_then_signal(pid,sig):
            if pid==101 and sig==signal.SIGSTOP:
                self.fake.table[101]['command']='hdiutil-after-exec'
            original(pid,sig)
        self.fake.send=exec_then_signal
        self.ledger.freeze(); self.ledger.thaw(); self.ledger.check()
        self.assertNotEqual(self.fake.table[101]['state'],'T')
        self.assertIn((101,signal.SIGCONT),self.fake.sent)

    def test_exec_of_root_after_init_is_not_pid_reuse(self):
        self.fake.table[100]['command']='new executable'
        self.assertTrue(self.ledger.alive())
        self.ledger.freeze(); self.ledger.thaw(); self.ledger.check()

    def test_exec_during_cont_is_positive_only_when_running(self):
        self.ledger.freeze(); original=self.fake.send
        def changed(pid,sig):
            original(pid,sig)
            if pid==101 and sig==signal.SIGCONT: self.fake.table[pid]['command']='another executable'
        self.fake.send=changed
        self.ledger.thaw(); self.ledger.check()
        self.assertEqual(self.fake.table[101]['state'],'S')

    def test_one_missing_observation_after_cont_retains_pending(self):
        self.ledger.freeze(); original=self.fake.send; probe=self.fake.observe; omitted=[False]
        def incomplete(pid):
            if pid==101 and omitted[0]:
                omitted[0]=False; return None
            return probe(pid)
        def cont(pid,sig):
            if pid==101 and sig==signal.SIGCONT: omitted[0]=True
            else: original(pid,sig)
        self.fake.send=cont; self.fake.observe=incomplete
        with self.assertRaises(ValueError): self.ledger.thaw()
        with self.assertRaises(ValueError): self.ledger.check()
        self.assertEqual(self.fake.table[101]['state'],'T')
        self.assertEqual(self.ledger.data['phase'],'resume-failed')

    def test_missing_enumeration_not_mistaken_for_exit(self):
        self.ledger.freeze()
        self.fake.snapshot=lambda:{}
        self.ledger.thaw(); self.ledger.check()
        self.assertEqual(self.fake.table[101]['state'],'S')

    def test_unknown_before_cont_never_means_exited(self):
        self.ledger.freeze(); probe=self.fake.observe
        self.fake.observe=lambda pid:None if pid==101 else probe(pid)
        with self.assertRaises(ValueError): self.ledger.thaw()
        self.assertNotIn((101,signal.SIGCONT),self.fake.sent)
        with self.assertRaises(ValueError): self.ledger.check()

    def test_esrch_after_cont_is_exited_not_resumed(self):
        self.ledger.freeze(); original=self.fake.send
        def exiting(pid,sig):
            original(pid,sig)
            if pid==101 and sig==signal.SIGCONT: del self.fake.table[pid]
        self.fake.send=exiting
        self.ledger.thaw(); self.ledger.check()
        row=next(x for x in self.ledger.data['records'] if x['pid']==101)
        self.assertEqual(row['status'],'exited')

    def test_cont_timeout_keeps_uncertain_and_resumes_other_rows(self):
        self.ledger.freeze(); original=self.fake.send
        self.fake.send=lambda pid,sig:None if pid==101 and sig==signal.SIGCONT else original(pid,sig)
        with self.assertRaises(ValueError): self.ledger.thaw()
        self.assertEqual(self.fake.table[101]['state'],'T')
        self.assertEqual(self.fake.table[100]['state'],'S')
        self.assertEqual(self.fake.table[102]['state'],'S')
        with self.assertRaises(ValueError): self.ledger.check()

    def test_changed_identity_after_cont_is_uncertain(self):
        self.ledger.freeze(); original=self.fake.send
        def replace(pid,sig):
            original(pid,sig)
            if pid==101 and sig==signal.SIGCONT: self.fake.table[pid]['birth'][1]+=1
        self.fake.send=replace
        with self.assertRaises(ValueError): self.ledger.thaw()
        with self.assertRaises(ValueError): self.ledger.check()

    def test_additional_protected_ids_persist_without_environment(self):
        path=Path(self.tmp.name)/'extra.json'
        with patch.dict(p.os.environ,{'OT07_PROTECTED_PIDS':'101'}):
            ledger=p.Ledger(path,self.fake); ledger.init(100,50)
        ledger=p.Ledger(path,self.fake)
        with self.assertRaises(ValueError): ledger.freeze()
        ledger.thaw(); ledger.check()
        self.assertFalse(any(pid==101 for pid,sig in self.fake.sent))

    def test_invalid_extra_protection_does_not_silently_drop(self):
        for value in ('x','1','100,','100,-2'):
            with self.assertRaises(ValueError): p.extra_protected(value)
        self.assertEqual(p.extra_protected('100'),{100,3494,3512})

    def test_legacy_or_unknown_terminal_state_cannot_pass_check(self):
        self.ledger.freeze(); self.ledger.thaw()
        self.ledger.data['records'][0]['status']='identity-changed-no-signal'
        with self.assertRaises(ValueError): self.ledger.check()
        self.ledger.data['version']=8
        with self.assertRaises(ValueError): self.ledger.check()

    def test_alive_rejects_recycled_root_and_accepts_exec(self):
        self.fake.table[100]['birth'][1]+=1
        with self.assertRaises(ValueError): self.ledger.alive()

    def test_root_zombie_or_unknown_freeze_aborts(self):
        original=self.fake.observe; seen=[0]
        def zombie(pid):
            row=original(pid)
            if pid==100:
                seen[0]+=1
                if seen[0]>=2: row['state']='Z'
            return row
        self.fake.observe=zombie
        with self.assertRaises(ValueError): self.ledger.freeze()

    def test_constructor_no_longer_polls_pid_with_kill_zero(self):
        script=(Path(__file__).resolve().parents[1]/'construir_efi.sh').read_text()
        self.assertNotIn('kill -0',script)
        self.assertIn('process alive "$LEDGER"',script)

    def test_signal_return_does_not_bypass_state_validation(self):
        self.ledger.freeze(); probe=self.fake.observe
        self.fake.observe=lambda pid:dict(probe(pid),state='?') if pid==101 else probe(pid)
        with self.assertRaises(ValueError): self.ledger.thaw()
        with self.assertRaises(ValueError): self.ledger.check()

    def test_interruption_after_stop_keeps_intent_for_new_helper(self):
        original=self.fake.send
        def interrupted(pid,sig):
            original(pid,sig)
            if pid==101 and sig==signal.SIGSTOP: raise KeyboardInterrupt('synthetic interruption')
        self.fake.send=interrupted
        with self.assertRaises(KeyboardInterrupt): self.ledger.freeze()
        stored=json.loads(self.ledger.path.read_text())
        self.assertEqual(stored['records'][-1]['status'],'attempting')
        self.fake.send=original
        retry=p.Ledger(self.ledger.path,self.fake);retry.thaw();retry.check()
        self.assertEqual(self.fake.table[101]['state'],'S')

    def test_interruption_during_cont_never_persists_closed_phase(self):
        self.ledger.freeze();original=self.fake.send
        def interrupted(pid,sig):
            original(pid,sig)
            if pid==101 and sig==signal.SIGCONT: raise KeyboardInterrupt('synthetic interruption')
        self.fake.send=interrupted
        with self.assertRaises(KeyboardInterrupt):self.ledger.thaw()
        retry=p.Ledger(self.ledger.path,self.fake)
        with self.assertRaises(ValueError):retry.check()
        self.fake.send=original;retry.thaw();retry.check()
        self.assertTrue(all(x['state']=='S' for x in self.fake.table.values()))

    def test_empty_ledger_is_safe_close_but_not_capture(self):
        self.ledger.thaw(); self.ledger.check()
        with self.assertRaises(ValueError): self.ledger.check_build()
        self.assertEqual(self.fake.sent,[])

    def test_descendant_only_fails_check_build(self):
        self.ledger.freeze(); self.ledger.thaw()
        self.ledger.data['records']=[r for r in self.ledger.data['records'] if r['pid']!=100]
        with self.assertRaises(ValueError): self.ledger.check_build()

    def test_root_birth_mismatch_fails_check_build(self):
        self.ledger.freeze(); self.ledger.thaw()
        for r in self.ledger.data['records']:
            if r['pid']==100: r['birth']=[1,2]
        with self.assertRaises(ValueError): self.ledger.check_build()

    def test_root_terminal_passes_check_build(self):
        self.ledger.freeze(); self.ledger.thaw(); self.ledger.check(); self.ledger.check_build()

    def test_uncertain_descendant_fails_check_build(self):
        self.ledger.freeze(); self.ledger.thaw()
        extra=record(103,100); extra['status']='uncertain'
        self.ledger.data['records'].append(extra)
        with self.assertRaises(ValueError): self.ledger.check_build()

    def test_unclosed_or_legacy_ledger_fails_check_build(self):
        self.ledger.data['phase']='freezing'
        with self.assertRaises(ValueError): self.ledger.check_build()
        self.ledger.data['version']=8
        with self.assertRaises(ValueError): self.ledger.check_build()
