"""Failure-injected controller checks; no board or subprocess use."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('writer',Path(__file__).resolve().parents[1]/'Tools/write_xip_bootchain.py')
writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)


class MI:
    running=False
    def __init__(self,folder,fail=None,pc=0x341828ec):
        self.folder=folder;self.fail=fail;self.pc=pc;self.calls=[]
    def value(self,s):
        self.calls.append(s)
        if s=='$pc':return self.pc
        if '0x56008100' in s:return 2
        if self.fail=='erase' and 'EraseSector' in s:return -1
        return 0
    def console(self,s,**kw):
        self.calls.append(s)
        if s.startswith('set $pc'):self.pc=int(s.split('=')[1],0)
        if s.startswith('dump binary memory'):
            p=Path(s.split()[3])
            data=b'text' if p.name=='ram-text.bin' else b'\xff'*4194304
            if self.fail=='changed' and p.name=='before.bin':data=b'changed'
            p.write_bytes(data)
    def command(self,s,**kw):self.calls.append(s)


class Tests(unittest.TestCase):
    def test_bounds_and_preservation(self):
        before=bytes((i%251 for i in range(4194304)))
        result=writer.desired_nor(before,b'f'*2048,b's'*4096)
        self.assertEqual(result[0x180000:],before[0x180000:])
        self.assertEqual(result[2048:0x100000],before[2048:0x100000])
        self.assertEqual(result[0x101000:0x180000],before[0x101000:0x180000])
        for args in ((before[:-1],b'f'*2048,b's'*4096),(before,b'f'*131073,b's'*4096)):
            with self.assertRaises(ValueError):writer.desired_nor(*args)
    def test_ns_runtime_refused_before_secure_read(self):
        mi=MI(None,pc=0x70191588)
        with self.assertRaisesRegex(RuntimeError,'verified Secure'):
            writer.program_parked(mi,Path('.'),None,0x341828ec,b'',b'',0,b'')
        self.assertEqual(mi.calls,['$pc'])
    def run_fake(self,fail=None):
        with tempfile.TemporaryDirectory() as d:
            mi=MI(Path(d),fail=fail,pc=0x34182906)
            data=b'\xff'*4194304
            if fail:
                with self.assertRaises(RuntimeError):writer.program_parked(mi,Path(d),None,0x341828ec,data,data,0,b'text')
            else:writer.program_parked(mi,Path(d),None,0x341828ec,data,data,0,b'text')
            self.assertEqual(mi.calls[-1],'-target-detach')
            self.assertIn('set $primask = 1',mi.calls)
            return mi.calls
    def test_changed_nor_refuses_any_erase(self):
        self.assertFalse(any('EraseSector' in x for x in self.run_fake('changed')))
    def test_failed_erase_stops_without_retry_or_program(self):
        calls=self.run_fake('erase')
        self.assertEqual(sum('EraseSector' in x for x in calls),1)
        self.assertFalse(any('EXTMEM_Write' in x for x in calls))
    def test_secure_first_exactly_four_owned_sectors_and_double_readback(self):
        calls=self.run_fake()
        self.assertEqual([x for x in calls if 'EraseSector' in x],[
            '(int)EXTMEM_EraseSector(0,%d,65536)'%o for o in (0x100000,0x110000,0,0x10000)])
        self.assertEqual(sum('EXTMEM_Write' in x for x in calls),4)
        self.assertEqual(sum('after-' in x for x in calls),2)


if __name__=='__main__':unittest.main()
