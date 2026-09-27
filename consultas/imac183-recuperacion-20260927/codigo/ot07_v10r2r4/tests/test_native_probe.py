"""Mock the macOS libproc ABI. No kernel calls or signals in this suite."""
import ctypes
import errno
import unittest
from unittest.mock import patch
from test_guards import module
p=module('ot07_process')

class NativeProbe(unittest.TestCase):
    def invoke(self, size=136, error=0, mutate=None):
        class Function:
            def __call__(self,pid,flavor,arg,buffer,length):
                assert flavor==3 and arg==0 and length==136
                value=ctypes.cast(buffer,ctypes.POINTER(p.ProcBSDInfo)).contents
                value.pid=pid;value.ppid=50;value.status=4
                value.start_sec=1790409600;value.start_usec=123456;value.name=b'changed exec'
                if mutate: mutate(value)
                ctypes.set_errno(error)
                return size
        library=type('Library',(),{'proc_pidinfo':Function()})()
        with patch.object(p.sys,'platform','darwin'),patch.object(p.ctypes,'CDLL',return_value=library),patch.object(p.os,'kill',side_effect=AssertionError('NO_REAL_SIGNAL')):
            return p.Native().observe(100)
    def test_public_abi_size_and_offsets(self):
        self.assertEqual(ctypes.sizeof(p.ProcBSDInfo),136)
        self.assertEqual(p.ProcBSDInfo.start_sec.offset,120)
        self.assertEqual(p.ProcBSDInfo.start_usec.offset,128)
    def test_birth_microseconds_and_state_from_kernel(self):
        row=self.invoke()
        self.assertEqual(row['birth'],[1790409600,123456]);self.assertEqual(row['state'],'T')
    def test_only_esrch_means_process_gone(self):
        with self.assertRaises(p.ProcessGone): self.invoke(size=0,error=errno.ESRCH)
    def test_permission_or_empty_or_short_read_is_uncertain(self):
        for size,error in ((0,0),(0,errno.EPERM),(100,0)):
            with self.subTest(size=size,error=error),self.assertRaises(OSError):self.invoke(size,error)
    def test_invalid_identity_and_status_rejected(self):
        for field,value in (('pid',99),('status',9),('start_sec',0),('start_usec',1000000)):
            with self.subTest(field=field),self.assertRaises(ValueError):self.invoke(mutate=lambda row:setattr(row,field,value))
    def test_unsupported_host_never_uses_ps_as_fallback(self):
        with patch.object(p.sys,'platform','linux'),patch.object(p.ctypes,'CDLL',side_effect=AssertionError('NO_LOAD')):
            with self.assertRaises(ValueError):p.Native().observe(100)
