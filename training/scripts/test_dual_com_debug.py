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


class DisplayTests(unittest.TestCase):
    def test_crlf_and_ansi_survive_every_serial_split(self):
        raw = "\x1b[31mred\x1b[0m\r\nnext\r\n"
        for split in range(len(raw)+1):
            console = debug.ConsoleOutput(False, True)
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                console.receive("INNER", raw[:split])
                console.receive("INNER", raw[split:])
            self.assertEqual(output.getvalue(), "[INNER] \x1b[31mred\x1b[0m\n[INNER] next\n")

    def test_channels_have_independent_newline_state(self):
        console = debug.ConsoleOutput(False, True)
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            console.receive("INNER", "one\r")
            console.receive("USB", "two\n")
            console.receive("INNER", "\nthree\n")
        self.assertEqual(output.getvalue(), "[INNER] one\n[USB] two\n[INNER] three\n")

    def test_windows_vt_enabled_and_existing_bits_preserved(self):
        class Kernel:
            def GetStdHandle(self, value):
                self.handle_id=value;return 123
            def GetConsoleMode(self, handle, mode):
                mode._obj.value=0x10;return 1
            def SetConsoleMode(self, handle, mode):
                self.mode=mode;return 1
        kernel=Kernel()
        with patch.object(debug.sys, "platform", "win32"):
            self.assertTrue(debug.enable_ansi_output(SimpleNamespace(isatty=lambda:True),kernel))
        self.assertEqual(kernel.handle_id,-11)
        self.assertEqual(kernel.mode,0x15)
        self.assertFalse(debug.enable_ansi_output(SimpleNamespace(isatty=lambda:False),kernel))


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


class EscapeSwitchTests(unittest.TestCase):
    def test_switch_updates_live_output_without_stopping_other_logging(self) -> None:
        console = debug.ConsoleOutput(False)
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            console.receive("USB", "usb-before\n")
            console.receive("INNER", "hidden-inner\n")
            self.assertEqual(console.switch_channel(), "INNER")
            console.receive("USB", "hidden-usb\n")
            console.receive("INNER", "uart-visible\n")
            self.assertEqual(console.switch_channel(), "USB")
            console.receive("USB", "usb-after\n")
        text = output.getvalue()
        self.assertIn("[USB] usb-before", text)
        self.assertIn("[INNER] uart-visible", text)
        self.assertIn("[USB] usb-after", text)
        self.assertNotIn("hidden-inner", text)
        self.assertNotIn("hidden-usb", text)

    def test_switch_routes_inner_single_character_then_usb_cli(self) -> None:
        class FakePort:
            def __init__(self) -> None:
                self.sent = []
            def send(self, data, description):
                self.sent.append(data)
                return True
        class FakeLog:
            def __init__(self) -> None:
                self.events = []
            def event(self, message):
                self.events.append(message)

        events = iter([("switch", ""), ("uart-key", "a"),
                       ("switch", ""), ("line", "wifi status"), ("line", "quit")])
        usb, inner = FakePort(), FakePort()
        logs = (FakeLog(), FakeLog())
        with patch.object(debug, "read_console_event", side_effect=lambda _: next(events)), \
             patch("sys.stdout", new_callable=io.StringIO):
            debug.command_loop(usb, inner, debug.ConsoleOutput(False), logs)
        self.assertEqual(usb.sent, [b"wifi status\r"])
        self.assertEqual(inner.sent, [b"a"])
        self.assertEqual(len(logs[0].events), 2)
        self.assertEqual(len(logs[1].events), 2)

    def test_windows_esc_key_works_without_enter(self) -> None:
        import types
        fake_msvcrt = types.SimpleNamespace(getwch=unittest.mock.Mock(
            side_effect=["w", "i", "f", "i", "\x1b", "a"]))
        with patch.object(debug.sys, "platform", "win32"), \
             patch.object(debug.sys.stdin, "isatty", return_value=True), \
             patch.dict("sys.modules", {"msvcrt": fake_msvcrt}), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(debug.read_console_event("USB"), ("switch", ""))
            self.assertEqual(debug.read_console_event("INNER"), ("uart-key", "a"))


if __name__ == "__main__":
    unittest.main()
