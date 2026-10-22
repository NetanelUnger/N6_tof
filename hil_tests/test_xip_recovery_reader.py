"""Host checks for the recovery reader's no-legacy-entry failure handling."""
import importlib.util
import io
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'Tools/read_xip_recovery.py'
spec = importlib.util.spec_from_file_location('reader', MODULE)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
SYMBOLS = {'Firmware_Boot_Prepare': 0x34180010, 'Error_Handler': 0x34180020}


class FakeMI:
    def __init__(self, folder, fail=None, initial_pc=0x18003514):
        self.calls = []
        self.folder = folder
        self.fail = fail
        self.pc = initial_pc

    def command(self, value, **kwargs):
        self.calls.append(value)
        if value == '-exec-continue':
            self.pc = SYMBOLS['Firmware_Boot_Prepare']

    def until(self, *args, **kwargs):
        return '*stopped'

    def console(self, value, **kwargs):
        self.calls.append(value)
        if value.startswith('set $pc = 0x'):
            self.pc = int(value.split('=')[1], 0)
        if value.startswith('dump binary memory'):
            if self.fail == 'dump':
                raise RuntimeError('memory unavailable')
            name = 'nor-first.bin' if 'nor-first.bin' in value else 'nor-second.bin'
            (self.folder / name).write_bytes(b'\xff' * 4194304)

    def value(self, value):
        self.calls.append(value)
        if value == '$pc':
            if self.fail == 'park' and self.pc == SYMBOLS['Error_Handler']:
                return 0
            return self.pc
        if '0x56008100' in value:
            return 2
        if value == '(int)MapMemory()' and self.fail == 'symbol':
            raise RuntimeError('No symbol MapMemory')
        return 0


class RecoveryReaderTests(unittest.TestCase):
    def test_gdb_symbol_decorated_pc_and_signed_status(self):
        self.assertEqual(reader.scalar_value('0x34181234 <Error_Handler>'), 0x34181234)
        self.assertEqual(reader.scalar_value('-1'), -1)
        with self.assertRaises(ValueError):
            reader.scalar_value('unavailable')

    def run_reader(self, mi, folder):
        return reader.read_at_prepare(mi, Path('FSBL.elf'), folder, SYMBOLS)

    def assert_parked_detach(self, mi):
        park = 'set $pc = 0x34180020'
        self.assertEqual(mi.calls[-3:], [park, '$pc', '-target-detach'])
        self.assertEqual(mi.calls.count('-exec-continue'), 1)

    def test_missing_symbol_stays_interactive_and_parks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            mi = FakeMI(folder, fail='symbol')
            with self.assertRaisesRegex(RuntimeError, 'No symbol'):
                self.run_reader(mi, folder)
            self.assert_parked_detach(mi)
            self.assertLess(mi.calls.index('set $pc = 0x34180020'),
                            mi.calls.index('(int)MapMemory()'))

    def test_failed_dump_parks_without_application_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            mi = FakeMI(Path(tmp), fail='dump')
            with self.assertRaisesRegex(RuntimeError, 'memory unavailable'):
                self.run_reader(mi, Path(tmp))
            self.assert_parked_detach(mi)

    def test_unknown_current_application_refuses_ram_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            mi = FakeMI(Path(tmp), initial_pc=0x70191588)
            with self.assertRaisesRegex(RuntimeError, 'DEV Boot ROM'):
                self.run_reader(mi, Path(tmp))
            self.assertNotIn('load', mi.calls)
            self.assertNotIn('-exec-continue', mi.calls)

    def test_unverified_park_never_sends_detach(self):
        with tempfile.TemporaryDirectory() as tmp:
            mi = FakeMI(Path(tmp), fail='park')
            with self.assertRaisesRegex(RuntimeError, 'no detach sent'):
                self.run_reader(mi, Path(tmp))
            self.assertNotIn('-target-detach', mi.calls)

    def test_two_complete_reads_leave_fsbl_parked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            mi = FakeMI(folder)
            result = self.run_reader(mi, folder)
            self.assertTrue(result['double_read_identical'])
            self.assertTrue(result['park_verified'])
            self.assertFalse(result['nor_written'])
            self.assertFalse(result['application_entered'])
            self.assert_parked_detach(mi)

    def test_installed_gdb_error_does_not_exit_mi(self):
        plugins = Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
        paths = list(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gdb.exe'))
        if not paths:
            self.skipTest('installed Windows GDB not available')
        mi = reader.GdbMI(paths[0], io.StringIO())
        try:
            with self.assertRaisesRegex(RuntimeError, 'error'):
                mi.value('missing_n6_symbol')
            self.assertEqual(mi.value('2+2'), 4)
        finally:
            mi.close()

    def test_wrong_hash_rejected_before_output_or_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fsbl = folder / 'fixture.elf'
            fsbl.write_bytes(b'not a valid FSBL')
            output = folder / 'never-created'
            result = subprocess.run([sys.executable, str(MODULE), '--fsbl', str(fsbl),
                                     '--sha256', '0' * 64, '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('hash mismatch', result.stderr)
            self.assertFalse(output.exists())

    def test_application_symbols_rejected_before_output_or_probe(self):
        application = MODULE.parents[1] / '.local-dependencies/xip/v12-A-no-export/application.elf'
        if not application.exists():
            self.skipTest('local XIP artifact not available')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'never-created'
            digest = hashlib.sha256(application.read_bytes()).hexdigest()
            result = subprocess.run([sys.executable, str(MODULE), '--fsbl', str(application),
                                     '--sha256', digest, '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing FSBL symbol', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
