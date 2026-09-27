#!/usr/bin/python3
"""OCLP process ledger v9. Import is inert; tests inject observations/signals.
Identity is PID + kernel start seconds/microseconds; command is diagnostic only.
Enumeration is not proof of exit. proc_pidinfo ESRCH or an observed zombie is.
Observation and kill remain separate, non-atomic operations on macOS.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROTECTED = {3494, 3512}
TERMINAL = {'resumed', 'exited'}
STATES = {1: 'I', 2: 'R', 3: 'S', 4: 'T', 5: 'Z'}
PROC_PIDTBSDINFO = 3


class ProcessGone(Exception):
    """The targeted kernel lookup returned ESRCH (not missing from enumeration)."""


def extra_protected(text):
    result = set(PROTECTED)
    if text.strip():
        for token in text.split(','):
            if not token.strip().isdigit() or int(token) <= 1:
                raise ValueError('invalid OT07_PROTECTED_PIDS; no signal allowed')
            result.add(int(token))
    return result


def parse_ps(text):
    result = {}
    for line in text.splitlines():
        fields = line.split(None, 8)
        if len(fields) != 9 or not fields[0].isdigit() or not fields[1].isdigit():
            raise ValueError('unrecognized ps record')
        pid, ppid = map(int, fields[:2])
        if pid in result:
            raise ValueError('duplicate ps PID')
        result[pid] = dict(pid=pid, ppid=ppid, state=fields[2],
                          birth_label=' '.join(fields[3:8]), command=fields[8])
    return result


class ProcBSDInfo(ctypes.Structure):
    # Public macOS SDK sys/proc_info.h PROC_PIDTBSDINFO; uint32 uid_t/gid_t.
    _fields_ = [(n, ctypes.c_uint32) for n in (
        'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid',
        'svuid', 'svgid', 'reserved')] + [
        ('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)] + [
        (n, ctypes.c_uint32) for n in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')] + [
        ('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


def valid_record(row):
    if not isinstance(row, dict):
        raise ValueError('missing/incomplete process observation')
    birth = row.get('birth')
    if (not isinstance(row.get('pid'), int) or row['pid'] <= 1 or
        not isinstance(row.get('ppid'), int) or row['ppid'] < 0 or
        row.get('state') not in STATES.values() or
        not isinstance(birth, list) or len(birth) != 2 or
        any(type(x) is not int for x in birth) or birth[0] <= 0 or not 0 <= birth[1] < 1000000):
        raise ValueError('invalid kernel process identity/state')
    return row


def same(a, b):
    return b is not None and a['pid'] == b['pid'] and a['birth'] == b['birth']


class Native:
    def snapshot(self):
        r = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,stat=,lstart=,comm='],
                           check=True, stdout=subprocess.PIPE, text=True,
                           env=dict(os.environ, LC_ALL='C'))
        return parse_ps(r.stdout)

    def observe(self, pid):
        if sys.platform != 'darwin' or ctypes.sizeof(ProcBSDInfo) != 136:
            raise ValueError('unsupported process ABI; no fallback to second-resolution ps')
        lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        fn = lib.proc_pidinfo
        fn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        fn.restype = ctypes.c_int
        data = ProcBSDInfo()
        ctypes.set_errno(0)
        # arg=0 is the public lookup. Zombie visibility is not guaranteed on every path;
        # ESRCH remains the absence proof. Native.send checks the env list at signal time;
        # Ledger.stop_one/resolve check the persisted set before calling send.
        size = fn(pid, PROC_PIDTBSDINFO, 0, ctypes.byref(data), ctypes.sizeof(data))
        error = ctypes.get_errno()
        if size == 0 and error == errno.ESRCH:
            raise ProcessGone(str(pid))
        if size != ctypes.sizeof(data):
            raise OSError(error, 'proc_pidinfo incomplete/denied; process not proven exited')
        if data.pid != pid:
            raise ValueError('kernel returned different PID')
        return valid_record(dict(pid=data.pid, ppid=data.ppid, state=STATES.get(data.status),
                                 birth=[data.start_sec, data.start_usec],
                                 command=bytes(data.name or data.comm).decode('utf-8', errors='replace')))

    def send(self, pid, sig):
        if pid in extra_protected(os.environ.get('OT07_PROTECTED_PIDS', '')) or pid <= 1:
            raise ValueError('protected PID')
        os.kill(pid, sig)

    def pause(self):
        time.sleep(.05)


class Ledger:
    def __init__(self, path, backend=None):
        self.path = Path(path)
        self.backend = backend or Native()
        self.protected = extra_protected(os.environ.get('OT07_PROTECTED_PIDS', ''))
        self.data = json.loads(self.path.read_text()) if self.path.exists() else None
        if self.data is not None:
            self.validate()
            self.protected.update(self.data['protected'])

    def validate(self):
        d = self.data
        if (not isinstance(d, dict) or d.get('version') != 9 or
            not isinstance(d.get('records'), list) or not isinstance(d.get('protected'), list) or
            any(type(x) is not int or x <= 1 for x in d['protected']) or
            not PROTECTED.issubset(d['protected'])):
            raise ValueError('invalid/legacy process ledger; keep lock and inspect')
        valid_record(d['root'])
        seen = set()
        for row in d['records']:
            valid_record(row)
            if row['pid'] in seen or row.get('status') not in {'attempting', 'stopped', 'uncertain', *TERMINAL}:
                raise ValueError('invalid/duplicate ledger record')
            seen.add(row['pid'])

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def observe(self, pid):
        # None, permissions and malformed results are uncertainty, never exit.
        row = valid_record(self.backend.observe(pid))
        if row['pid'] != pid:
            raise ValueError('observation returned different PID')
        return row

    def init(self, pid, parent):
        if self.data is not None or pid in self.protected or pid <= 1:
            raise ValueError('ledger exists or protected PID')
        root = self.observe(pid)
        if root['ppid'] != parent:
            raise ValueError('OCLP is not the direct child of this constructor')
        self.data = dict(version=9, root=root, protected=sorted(self.protected), records=[], phase='initialized')
        self.save()

    def alive(self):
        try:
            now = self.observe(self.data['root']['pid'])
        except ProcessGone:
            return False
        if not same(self.data['root'], now):
            raise ValueError('OCLP PID reused; original child identity lost')
        return now['state'] != 'Z'

    def stop_one(self, record):
        pid = record['pid']
        if pid in self.protected or pid <= 1:
            raise ValueError('protected PID')
        now = self.observe(pid)
        if not same(record, now) or now['ppid'] != record['ppid']:
            raise ValueError('process identity/parent changed before STOP')
        row = dict(record, status='attempting')
        self.data['records'].append(row)
        self.save()  # Intent survives an interruption immediately after STOP.
        self.backend.send(pid, signal.SIGSTOP)
        row['status'] = 'stopped'; self.save()

    def freeze(self):
        if self.data['phase'] != 'initialized':
            raise ValueError('freeze requires a fresh ledger')
        self.data['phase'] = 'freezing'; self.save()
        self.stop_one(self.data['root'])
        for _ in range(100):
            table = self.backend.snapshot()  # Candidate discovery only.
            live = {}
            for row in self.data['records']:
                try:
                    now = self.observe(row['pid'])
                except ProcessGone:
                    if row['pid'] == self.data['root']['pid']:
                        raise ValueError('OCLP exited during freeze')
                    row['status'] = 'exited'; self.save(); continue
                if not same(row, now):
                    raise ValueError('tracked PID reused during freeze')
                if now['state'] == 'Z':
                    if row['pid'] == self.data['root']['pid']:
                        raise ValueError('OCLP exited during freeze')
                    row['status'] = 'exited'; self.save(); continue
                live[row['pid']] = now
            known = {r['pid'] for r in self.data['records']}
            added = False
            for candidate in table.values():
                parent = live.get(candidate['ppid'])
                if candidate['pid'] not in known and parent and parent['state'] == 'T':
                    try:
                        now = self.observe(candidate['pid'])
                    except ProcessGone:
                        continue
                    if now['ppid'] != parent['pid']:
                        raise ValueError('candidate parent changed before capture')
                    if now['state'] != 'Z':
                        self.stop_one(now); added = True
            if not added and live and all(r['state'] == 'T' for r in live.values()):
                self.data['phase'] = 'frozen'; self.save(); return
            self.backend.pause()
        raise ValueError('STOP not confirmed for the complete observed tree')

    def resolve(self, row, send_cont):
        # Only positive same-identity non-T/Z observations or kernel ESRCH close a record.
        try:
            now = self.observe(row['pid'])
        except ProcessGone:
            row['status'] = 'exited'; return True
        if not same(row, now):
            raise ValueError('tracked PID replaced; no signal; keep ledger unresolved')
        row['last_command'] = now.get('command', '')  # exec changes this diagnostic field only.
        if now['state'] == 'Z':
            row['status'] = 'exited'; return True
        if send_cont:
            if row['pid'] in self.protected or row['pid'] <= 1:
                raise ValueError('protected PID in ledger')
            self.backend.send(row['pid'], signal.SIGCONT)
            return False  # Always re-observe after sending CONT, even if initially non-T.
        if now['state'] in ('R', 'S'):
            row['status'] = 'resumed'; return True
        return False  # T and transient I are not positive evidence of resumed execution.

    def thaw(self):
        errors = []
        self.data['phase'] = 'thawing'; self.save()
        for row in reversed(self.data['records']):
            if row['status'] in TERMINAL:
                continue
            try:
                if not self.resolve(row, send_cont=True):
                    for _ in range(100):
                        if self.resolve(row, send_cont=False): break
                        self.backend.pause()
                    else:
                        raise ValueError('CONT not confirmed; keep ledger pending')
                row.pop('error', None)
                self.save()
            except Exception as e:
                row['status'] = 'uncertain'; row['error'] = str(e)
                self.save(); errors.append(str(e))
        self.data['phase'] = 'resume-failed' if errors else 'thawed'; self.save()
        if errors:
            raise ValueError('; '.join(errors))

    def check(self):
        # Safe close: a valid thawed ledger with no unresolved rows. Zero rows is legitimate
        # when freeze never sent STOP. It does not prove a capture.
        self.validate()
        if self.data['phase'] != 'thawed' or any(r['status'] not in TERMINAL for r in self.data['records']):
            raise ValueError('constructor ledger unresolved; keep execution lock')

    def check_build(self):
        self.check()
        root = self.data['root']
        captured = [r for r in self.data['records']
                    if r['pid'] == root['pid'] and r['birth'] == root['birth'] and r['status'] in TERMINAL]
        if not captured:
            raise ValueError('no terminal row for the registered root identity; capture not proven')


def main(args):
    cmd, path, *rest = args
    ledger = Ledger(path)
    if cmd == 'init': ledger.init(*map(int, rest))
    elif cmd == 'freeze': ledger.freeze()
    elif cmd == 'thaw': ledger.thaw()
    elif cmd == 'check': ledger.check()
    elif cmd == 'check-build': ledger.check_build()
    elif cmd == 'alive':
        if not ledger.alive(): raise ValueError('original OCLP child exited')
    else: raise ValueError('unknown process command')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as e:
        print('OT07_PROCESS_FAIL: ' + str(e), file=sys.stderr)
        sys.exit(1)
