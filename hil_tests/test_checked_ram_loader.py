"""Host-only safety regressions for the demo RAM loader; no board access."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import load_checked_ram as loader

SYMS = {
    'fsbl': dict(boot_metadata_commit=0x34181000, JumpToApplication=0x34182000,
                 Error_Handler=0x34183000, Firmware_Boot_Prepare=0x34184000),
    'secure': dict(main=0x34010000),
    'nonsecure': dict(main=0x24101000, NPU_SharedMemory_Clear=0x24102000,
                      Debug_UART_Init=0x24103000, MX_ThreadX_Init=0x24104000),
}


class FakeMI:
    def __init__(self, folder, fault=None):
        self.folder, self.fault = folder, fault
        self.calls = []
        self.running = False
        self.pc = 0x24101000 if fault == 'live' else 0x18003514
        self.breakpoint = None
        self.resumes = 0

    def command(self, command, **kwargs):
        self.calls.append(command)
        if command == '-exec-continue':
            self.resumes += 1
            self.pc = self.breakpoint
            if self.resumes == 1 and self.fault == 'writer':
                self.pc = SYMS['fsbl']['boot_metadata_commit']
            if self.resumes == 3 and self.fault == 'ns':
                self.pc += 2
        return '1^done,bkpt={number="1"}'

    def console(self, command, **kwargs):
        self.calls.append(command)
        if command.startswith('thbreak '):
            self.breakpoint = int(command.split('*')[1], 16)
        if command.startswith('set $pc = 0x'):
            self.pc = int(command.split('=')[1], 16)
        if command == 'load' and self.fault == 'load':
            raise RuntimeError('Partial load')
        if command.startswith('dump binary memory '):
            name = command.split()[3]
            role = name.split('.')[0]
            (self.folder / name).write_bytes(b'wrong' if self.fault == 'readback'
                                           else (self.folder / (role + '.bin')).read_bytes())

    def value(self, expression):
        self.calls.append(expression)
        if expression == '$pc':
            return self.pc
        if '56008100' in expression:
            return 0 if self.fault == 'boot' else 2
        if expression == 'boot_work_record.state':
            return 2 if self.fault == 'state' else 1
        if 'unsigned short' in expression:
            return 0 if self.fault == 'park' else 0xe7fe
        return 0

    def until(self, *args, **kwargs):
        if self.fault == 'park':
            raise TimeoutError('debug link lost')
        return '*stopped'


class ControllerTests(unittest.TestCase):
    def run_case(self, fault=None):
        with tempfile.TemporaryDirectory(prefix='ram test ') as tmp:
            folder = Path(tmp)
            for role in ('secure', 'nonsecure'):
                (folder / (role + '.bin')).write_bytes(b'RAM payload')
            mi, result = FakeMI(folder, fault), {}
            error = None
            try:
                loader.start_in_dev(mi, folder, folder, SYMS, result, 61444)
            except Exception as exc:
                error = str(exc)
            return mi, result, error

    def test_success_guard_precedes_first_continue_and_full_readback(self):
        mi, result, error = self.run_case()
        self.assertIsNone(error)
        self.assertEqual(result['status'], 'RAM_STARTED')
        self.assertEqual(result['secure_readback'], 'PASS')
        self.assertEqual(result['nonsecure_readback'], 'PASS')
        guard = '-break-insert -h *0x34181000'
        self.assertLess(mi.calls.index(guard), mi.calls.index('-exec-continue'))
        self.assertLess(mi.calls.index('boot_work_record.state'), mi.calls.index('-break-delete 1'))
        self.assertEqual(mi.calls[-1], '-target-detach')
        self.assertFalse(any('reset' in call.lower() or 'erase' in call.lower() for call in mi.calls))

    def test_live_application_refused_before_secure_read(self):
        mi, result, error = self.run_case('live')
        self.assertIn('DEV ROM', error)
        self.assertNotIn('load', mi.calls)
        self.assertFalse(any('56008100' in call for call in mi.calls))
        self.assertEqual(mi.calls[-1], '-target-disconnect')

    def test_wrong_boot_mode_never_downloads(self):
        mi, _, error = self.run_case('boot')
        self.assertIn('DEV boot', error)
        self.assertNotIn('load', mi.calls)
        self.assertEqual(mi.resumes, 0)

    def test_pending_trial_or_fallback_write_parks_before_write(self):
        mi, result, error = self.run_case('writer')
        self.assertIn('metadata write forbidden', error)
        self.assertEqual(mi.resumes, 1)
        self.assertEqual(result['failure_park_verified'], '0x341ff000')
        self.assertFalse(any(call.startswith('restore ') for call in mi.calls))

    def test_unconfirmed_metadata_refused_at_handoff(self):
        mi, _, error = self.run_case('state')
        self.assertIn('not confirmed', error)
        self.assertEqual(mi.resumes, 1)

    def test_readback_failure_never_enters_secure_main(self):
        mi, _, error = self.run_case('readback')
        self.assertIn('readback mismatch', error)
        self.assertEqual(mi.resumes, 1)

    def test_nonsecure_failure_uses_nonsecure_parking(self):
        mi, result, error = self.run_case('ns')
        self.assertIn('Unexpected stop', error)
        self.assertEqual(result['failure_park_verified'], '0x241ff000')
        self.assertEqual(mi.calls[-1], '-target-detach')

    def test_partial_download_uses_verified_loop(self):
        mi, result, error = self.run_case('load')
        self.assertIn('Partial load', error)
        self.assertEqual(mi.resumes, 0)
        self.assertEqual(result['failure_park_verified'], '0x341ff000')

    def test_failed_parking_never_detaches(self):
        mi, result, _ = self.run_case('park')
        self.assertEqual(result['status'], 'UNCERTAIN')
        self.assertNotIn('-target-detach', mi.calls)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'ram-load.json'
        self.manifest = dict(schema_version=1, settings_writes=False,
                             settings_transition=False, ncp_preserve=True,
                             heap=379504, artifacts={})
        for role, (low, high) in loader.WINDOWS.items():
            payload = struct.pack('<II', high, low + 9) + b'12345678'
            (self.folder / (role + '.bin')).write_bytes(payload)
            elf = bytearray(84)
            elf[:6] = b'\x7fELF\x01\x01'
            struct.pack_into('<H', elf, 18, 40)
            struct.pack_into('<I', elf, 28, 52)
            struct.pack_into('<HH', elf, 42, 32, 1)
            struct.pack_into('<8I', elf, 52, 1, 0, low, low, len(payload), len(payload), 5, 4)
            (self.folder / (role + '.elf')).write_bytes(elf)
        self.refresh()

    def refresh(self):
        for artifact in self.folder.glob('*.*'):
            if artifact.suffix in ('.elf', '.bin'):
                self.manifest['artifacts'][artifact.name] = {'sha256': loader.digest(artifact)}
        self.path.write_text(json.dumps(self.manifest))

    def check(self, mismatch=False, missing=False):
        def objcopy(command, **kwargs):
            binary = Path(command[-2]).with_suffix('.bin')
            Path(command[-1]).write_bytes(b'bad' if mismatch else binary.read_bytes())
        def nm(command, **kwargs):
            return '' if missing else '\n'.join('%x T %s' % (address, name)
                                                for name, address in SYMS[Path(command[-1]).stem].items())
        with patch.object(loader.subprocess, 'run', side_effect=objcopy), \
             patch.object(loader.subprocess, 'check_output', side_effect=nm):
            return loader.preflight(self.path, dict(objcopy='objcopy', nm='nm'))

    def test_valid_bound_inputs(self):
        self.assertEqual(self.check()[1], SYMS)

    def test_tampered_artifact(self):
        (self.folder / 'secure.bin').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            self.check()

    def test_wrong_elf_bin_pair(self):
        with self.assertRaisesRegex(RuntimeError, 'ELF/BIN mismatch'):
            self.check(mismatch=True)

    def test_flash_load_segment(self):
        path = self.folder / 'fsbl.elf'
        data = bytearray(path.read_bytes())
        struct.pack_into('<I', data, 64, 0x70000000)
        path.write_bytes(data)
        self.refresh()
        with self.assertRaisesRegex(RuntimeError, 'outside SRAM'):
            self.check()

    def test_missing_writer_symbol(self):
        with self.assertRaisesRegex(RuntimeError, 'safety symbol'):
            self.check(missing=True)

    def test_persistence_and_heap_guards(self):
        for key, value in (('settings_writes', True), ('settings_transition', True),
                           ('ncp_preserve', False), ('heap', 369071)):
            with self.subTest(key=key):
                previous = self.manifest[key]
                self.manifest[key] = value
                self.refresh()
                with self.assertRaisesRegex(RuntimeError, 'safety contract'):
                    self.check()
                self.manifest[key] = previous

    def test_cli_defaults_to_offline_only(self):
        with patch.object(sys, 'argv', ['loader', '--manifest', str(self.path)]), \
             patch.object(loader, 'find_tools'), patch.object(loader, 'preflight') as pre, \
             patch.object(loader, 'execute') as execute, patch('sys.stdout', io.StringIO()):
            self.assertEqual(loader.main(), 0)
            pre.assert_called_once()
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
