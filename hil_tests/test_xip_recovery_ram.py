"""Host-only fault handling for the explicit RAM recovery controller."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('ram_restore',Path(__file__).resolve().parents[1]/'Tools/restore_xip_recovery_ram.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
SYMS=dict(park=0x341828ec,jump=0x341903ac,secure_main=0x34000480,main=0x24100480,threadx=0x24100500,reset=0x24100600)
PAYLOAD=b'\x00\x00\x20\x24\x01\x05\x10\x24'+b'\xA5'*24

class Fake:
    def __init__(self,folder,fail=None,pc=SYMS['park']):
        self.folder=folder;self.fail=fail;self.pc=pc;self.running=False;self.calls=[];self.brk=0
    def command(self,c,**kwargs):
        self.calls.append(c)
        if c=='-exec-continue':self.pc=self.brk if self.fail!='NS' or self.brk!=SYMS['main'] else SYMS['main']+2
    def until(self,*args,**kwargs):return '*stopped'
    def console(self,c,**kwargs):
        self.calls.append(c)
        if c.startswith('thbreak'):self.brk=int(c.split('*')[1],16)
        if c.startswith('set $pc'):self.pc=int(c.split('=')[1],16)
        if c.startswith('dump binary memory'):
            path=Path(c.split()[3]);path.write_bytes(b'BAD' if self.fail=='readback' else PAYLOAD)
    def value(self,c):
        self.calls.append(c)
        if c=='$pc':return self.pc
        if '56008100' in c:return 0 if self.fail=='boot' else 2
        if c=='*(unsigned int*)0x34100400':return int.from_bytes(PAYLOAD[:4],'little')
        if c=='*(unsigned int*)0x34100404':return int.from_bytes(PAYLOAD[4:8],'little')
        return 0x47702001

class Tests(unittest.TestCase):
    def run_case(self,fail=None,pc=SYMS['park']):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for n in ['ram.bin','AppliSecure.bin']:(folder/n).write_bytes(PAYLOAD)
            mi=Fake(folder,fail,pc)
            error=None;result=None
            try:result=controller.restore_parked(mi,folder,folder/'FSBL.elf',folder,SYMS)
            except RuntimeError as e:error=str(e)
            return mi,result,error
    def test_success_exact_RAM_entry_and_reset_refusal(self):
        mi,result,error=self.run_case();self.assertIsNone(error)
        self.assertFalse(result['nor_written']);self.assertFalse(result['A23_entered'])
        self.assertEqual(mi.calls[-1],'-target-detach')
        self.assertIn('set {unsigned int}0x34100600 = 0x47702001',mi.calls)
        self.assertFalse(any('reset' in x.lower() for x in mi.calls))
        self.assertFalse(any('Firmware_Boot_Prepare' in x for x in mi.calls))
    def test_NS_PC_refused_before_secure_alias(self):
        mi,_,error=self.run_case(pc=0x701a0000);self.assertIn('verified Secure',error)
        self.assertEqual(mi.calls[-1],'-target-disconnect')
        self.assertFalse(any('56008100' in x or x.startswith('restore ') or x.startswith('set $pc') for x in mi.calls))
    def test_boot_refusal_does_not_load_or_resume(self):
        mi,_,error=self.run_case('boot');self.assertIn('Not DEV',error)
        self.assertEqual(mi.calls[-1],'-target-disconnect')
        self.assertNotIn('-exec-continue',mi.calls)
    def test_readback_failure_parks_secure_without_app_entry(self):
        mi,_,error=self.run_case('readback');self.assertIn('readback mismatch',error)
        self.assertEqual(mi.pc,SYMS['park']);self.assertNotIn('-exec-continue',mi.calls)
        self.assertEqual(mi.calls[-1],'-target-detach')
    def test_NS_failure_parks_without_late_secure_alias_access(self):
        mi,_,error=self.run_case('NS');self.assertIn('NS main',error)
        self.assertEqual(mi.pc,0x241ff000)
        after=mi.calls[mi.calls.index('thbreak *0x24100480'):]
        self.assertFalse(any('34100400' in x or '56008100' in x for x in after))
        self.assertEqual(mi.calls[-1],'-target-detach')

if __name__=='__main__':unittest.main()
