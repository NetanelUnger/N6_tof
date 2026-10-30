"""Host-only recovery fixtures; no serial/debugger imports or board access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('lease',Path(__file__).with_name('n6_hardware_lease.py'))
lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)


class Tests(unittest.TestCase):
    def setup_owner(self,root):
        folder=root/'coord';folder.mkdir()
        owner={'thread':'n6-xip-passive-fixture','pid':99999999,'started_utc':'2026-10-22T18:55:07+00:00',
               'scope':'XIP passive COM6 UART capture only; test fixture'}
        (folder/'n6-hardware-owner.lock').write_bytes(b'1')
        raw=json.dumps(owner).encode();(folder/'n6-hardware-owner.json').write_bytes(raw)
        ready=root/'ready.json';ready.write_bytes(raw)
        return folder,owner,ready,raw
    def run_case(self,state='absent',mutate=None):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root)
            if mutate:mutate(folder,ready)
            if state=='absent' and mutate is None:
                result=lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=lambda pid:{'state':state})
                self.assertTrue(result['archived']);self.assertFalse(result['port_free_verified'])
                self.assertEqual((root/'evidence/n6-hardware-owner.json').read_bytes(),raw)
                self.assertEqual((root/'evidence/n6-hardware-owner.lock').read_bytes(),b'1')
                self.assertFalse((folder/'n6-hardware-owner.lock').exists())
            else:
                with self.assertRaises((RuntimeError,FileExistsError,OSError)):
                    lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=lambda pid:{'state':state})
                self.assertTrue((folder/'n6-hardware-owner.json').exists())
                self.assertTrue((folder/'n6-hardware-owner.lock').exists())
    def test_exact_dead_owner_archived(self):self.run_case()
    def test_owned_xip_requires_explicit_scope_and_creation_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root)
            owner.update(thread='n6-xip-fixture',process_created_utc='2026-10-23T18:12:33+00:00',
              scope='authorized recoverable XIP/USB/OTA NOR validation; no OTP, settings, credential or pairing writes')
            raw=json.dumps(owner).encode();ready.write_bytes(raw);(folder/'n6-hardware-owner.json').write_bytes(raw)
            with self.assertRaises(RuntimeError):
                lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=lambda pid:{'state':'absent'})
            result=lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],
                probe=lambda pid:{'state':'absent'},authorized_xip=True)
            self.assertTrue(result['archived']);self.assertFalse(result['port_free_verified'])
    def test_owned_xip_unknown_process_still_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root)
            owner.update(thread='n6-xip-fixture',process_created_utc='2026-10-23T18:12:33+00:00',
              scope='authorized recoverable XIP/USB/OTA NOR validation; no OTP, settings, credential or pairing writes')
            raw=json.dumps(owner).encode();ready.write_bytes(raw);(folder/'n6-hardware-owner.json').write_bytes(raw)
            with self.assertRaises(RuntimeError):
                lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],
                  probe=lambda pid:{'state':'unknown'},authorized_xip=True)
    def test_live_or_reused_pid_rejected(self):self.run_case('alive')
    def test_access_denied_or_unknown_not_death(self):self.run_case('unknown')
    def test_started_identity_mismatch(self):
        def mutate(folder,ready):
            d=json.loads(ready.read_text());d['started_utc']='different';ready.write_text(json.dumps(d))
        self.run_case(mutate=mutate)
    def test_foreign_scope_rejected(self):
        def mutate(folder,ready):
            d=json.loads(ready.read_text());d['scope']='other owner';s=json.dumps(d)
            ready.write_text(s);(folder/'n6-hardware-owner.json').write_text(s)
        self.run_case(mutate=mutate)
    def test_recovery_guard_rejected(self):
        self.run_case(mutate=lambda f,r:(f/'n6-hardware-recovery.lock').write_bytes(b'other'))
    def test_os_marker_lock_rejected(self):
        import msvcrt
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root)
            with (folder/'n6-hardware-owner.lock').open('r+b') as held:
                msvcrt.locking(held.fileno(),msvcrt.LK_NBLCK,1)
                with self.assertRaises(OSError):
                    lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=lambda pid:{'state':'absent'})
            self.assertEqual((folder/'n6-hardware-owner.json').read_bytes(),raw)
    def test_real_self_identity_is_live(self):
        import os
        identity=lease.windows_process_identity(os.getpid())
        self.assertEqual(identity['state'],'alive');self.assertIn('created_utc',identity)
    def test_pid_appearing_during_recovery_blocks_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root);calls=[]
            def probe(pid):
                calls.append(pid);return {'state':'absent' if len(calls)==1 else 'alive'}
            with self.assertRaises(RuntimeError):
                lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=probe)
            self.assertEqual((folder/'n6-hardware-owner.json').read_bytes(),raw)
            self.assertTrue((folder/'n6-hardware-owner.lock').exists())
    def test_changed_owner_during_recovery_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder,owner,ready,raw=self.setup_owner(root);calls=[]
            changed={**owner,'thread':'new-owner'}
            def probe(pid):
                calls.append(pid)
                if len(calls)==2:(folder/'n6-hardware-owner.json').write_text(json.dumps(changed))
                return {'state':'absent'}
            with self.assertRaises(RuntimeError):
                lease.recover_owned_stale(folder,ready,root/'evidence',owner['thread'],probe=probe)
            self.assertEqual(json.loads((folder/'n6-hardware-owner.json').read_text()),changed)
            self.assertTrue((folder/'n6-hardware-owner.lock').exists())


if __name__=='__main__':unittest.main()
