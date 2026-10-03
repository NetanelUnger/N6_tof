"""Hardware-free checks for N6 dual-COM capture and command routing."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dual_com_debug as debug  # noqa: E402


class PortSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.usb = SimpleNamespace(device="COM8", vid=0x0483, pid=0x5740,
                                   description="USB Serial Device", hwid="USB VID:PID=0483:5740")
        self.inner = SimpleNamespace(device="COM6", vid=0x0483, pid=0x3754,
                                     description="STMicroelectronics STLink Virtual COM Port",
                                     hwid="USB VID:PID=0483:3754")

    def test_detects_both_roles_and_override(self) -> None:
        ports = [self.inner, self.usb]
        self.assertEqual(debug.choose_port("USB", ports), "COM8")
        self.assertEqual(debug.choose_port("INNER", ports), "COM6")
        self.assertEqual(debug.choose_port("INNER", ports, "com6"), "COM6")

    def test_ambiguous_role_never_chooses_arbitrarily(self) -> None:
        self.assertIsNone(debug.choose_port("USB", [self.usb, self.usb]))

    def test_usb_id_survives_com_renumbering(self) -> None:
        self.usb.device = "COM12"
        self.assertEqual(debug.choose_port("USB", [self.inner, self.usb]), "COM12")


class LogTests(unittest.TestCase):
    def test_split_utf8_and_unique_runs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertNotEqual(debug.make_run_directory(root), debug.make_run_directory(root))
            path = root / "capture.txt"
            log = debug.CaptureLog(path, "USB")
            first = "שלום".encode("utf-8")
            self.assertEqual(log.receive(first[:1]), "")
            self.assertEqual(log.receive(first[1:]), "שלום")
            self.assertIn("שלום", path.read_text(encoding="utf-8"))
            log.event("reconnected COM8")
            log.close()
            contents = path.read_text(encoding="utf-8")
            self.assertIn("שלום", contents)
            self.assertIn("reconnected COM8", contents)


class CommandTests(unittest.TestCase):
    def test_shortcuts_and_hidden_password(self) -> None:
        class FakePort:
            def __init__(self) -> None:
                self.sent: list[bytes] = []

            def send(self, data: bytes, description: str) -> bool:
                self.sent.append(data)
                return True

        usb, inner = FakePort(), FakePort()
        console = debug.ConsoleOutput(True)
        commands = iter(["ble status", "wifi scan", "inner a", "ping test",
                         'usb wifi connect "SSID"', "quit"])
        with patch("builtins.input", side_effect=lambda _: next(commands)), \
                patch("getpass.getpass", return_value="secret123"), \
                patch("sys.stdout", new_callable=io.StringIO):
            debug.command_loop(usb, inner, console, ())
        self.assertEqual(usb.sent, [b"ble status\r", b"wifi scan\r",
                                    b"debug ping test\r", b'wifi connect "SSID"\r',
                                    b"secret123\r"])
        self.assertEqual(inner.sent, [b"a"])


if __name__ == "__main__":
    unittest.main()
