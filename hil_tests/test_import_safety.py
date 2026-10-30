"""Prove the isolated worker blocks effects, using simulated device operations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'Tools/check_import_child.py'


class ImportDenialTests(unittest.TestCase):
    def check_fixture(self, source):
        with tempfile.TemporaryDirectory(prefix='n6-import-denial-') as temporary:
            folder = Path(temporary)
            target = folder / 'fixture_probe.py'
            target.write_text(source, encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', '-B', str(WORKER),
                                     '--target', str(target), '--root', str(ROOT)],
                                    capture_output=True, text=True, timeout=20)
            rows = [x.split('=', 1)[1] for x in result.stdout.splitlines()
                    if x.startswith('N6_IMPORT_AUDIT_RESULT=')]
            self.assertTrue(rows, result.stderr)
            return json.loads(rows[-1])

    def test_subprocess_is_never_started(self):
        value = self.check_fixture('import subprocess\nsubprocess.Popen(["ST-LINK_must_never_start.exe"])\n')
        self.assertFalse(value['passed'])
        self.assertEqual(value['effects'], ['subprocess.Popen'])

    def test_serial_constructor_is_denied(self):
        value = self.check_fixture('import serial\nserial.Serial("COM8")\n')
        self.assertEqual(value['effects'], ['serial.Serial'])

    def test_serial_enumeration_is_denied(self):
        value = self.check_fixture('from serial.tools.list_ports import comports\ncomports()\n')
        self.assertEqual(value['effects'], ['serial.enumerate'])

    def test_ble_scan_is_denied(self):
        value = self.check_fixture('from bleak import BleakScanner\nBleakScanner.discover()\n')
        self.assertEqual(value['effects'], ['BLE.discover'])

    def test_network_connect_is_denied(self):
        value = self.check_fixture('import socket\nsocket.create_connection(("must-not-connect.invalid",443))\n')
        self.assertEqual(value['effects'], ['socket.create_connection'])

    def test_filesystem_write_is_denied(self):
        value = self.check_fixture('from pathlib import Path\nPath("must-not-create.audit").write_text("no")\n')
        self.assertEqual(value['effects'], ['filesystem write'])
        self.assertFalse((ROOT / 'must-not-create.audit').exists())

    def test_main_guard_prevents_all_external_effects(self):
        value = self.check_fixture('def main():\n import subprocess,serial\n subprocess.Popen(["never.exe"])\n serial.Serial("COM8")\nif __name__=="__main__":\n main()\n')
        self.assertTrue(value['passed'])
        self.assertEqual(value['effects'], [])


if __name__ == '__main__':
    unittest.main()
