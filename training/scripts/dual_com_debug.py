"""Capture N6 USB CLI and ST-LINK debug UART while accepting diagnostic commands."""

from __future__ import annotations

import argparse
import codecs
import getpass
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_ROOT = PROJECT_DIR / "training" / "reports" / "dual_com"
INNER_KEYS = frozenset("?artcuRTCU n0".replace(" ", ""))


def enable_ansi_output(stream=None, kernel32=None) -> bool:
    """Enable Windows VT output without changing input/ESC handling."""
    stream = sys.stdout if stream is None else stream
    if not stream.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes
    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    mode = wintypes.DWORD()
    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and
                kernel32.SetConsoleMode(handle, mode.value | 0x0001 | 0x0004))


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def port_inventory() -> list[Any]:
    return sorted(list_ports.comports(), key=lambda port: port.device.upper())


def choose_port(role: str, ports: list[Any], override: str | None = None) -> str | None:
    if override:
        return next((port.device for port in ports if port.device.upper() == override.upper()), None)
    if role == "USB":
        matches = [port for port in ports if port.vid == 0x0483 and port.pid == 0x5740]
    else:
        matches = [
            port for port in ports
            if port.vid == 0x0483
            and port.pid != 0x5740
            and ("stlink" in port.description.lower().replace("-", "")
                 or "st-link" in port.hwid.lower())
        ]
    # Ambiguous matches must not silently bind to the wrong board.
    return matches[0].device if len(matches) == 1 else None


def make_run_directory(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    for suffix in range(100):
        path = root / (stem if suffix == 0 else f"{stem}_{suffix:02d}")
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise RuntimeError("Unable to create a unique capture directory")


class CaptureLog:
    def __init__(self, path: Path, label: str) -> None:
        self.path = path
        self.label = label
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.lock = threading.Lock()
        self.file = path.open("w", encoding="utf-8", newline="")
        self.event("capture started")

    def receive(self, data: bytes) -> str:
        with self.lock:
            decoded = self.decoder.decode(data)
            self.file.write(decoded)
            self.file.flush()
            return decoded

    def event(self, message: str) -> None:
        with self.lock:
            self.file.write(f"\r\n[HOST {timestamp()}] {message}\r\n")
            self.file.flush()

    def close(self) -> None:
        with self.lock:
            tail = self.decoder.decode(b"", final=True)
            if tail:
                self.file.write(tail)
            self.file.write(f"\r\n[HOST {timestamp()}] capture stopped\r\n")
            self.file.close()


class ConsoleOutput:
    def __init__(self, quiet: bool, show_inner: bool = False) -> None:
        self.quiet = quiet
        # Preserve the old --live-inner option: show both channels until the
        # first ESC. After that, the selected channel alone is echoed.
        self.show_inner = show_inner
        self.active_channel = "USB"
        self.lock = threading.Lock()
        self.pending = {"USB": "", "INNER": ""}
        self.previous_cr = {"USB": False, "INNER": False}

    def _is_visible(self, label: str) -> bool:
        return self.show_inner or label == self.active_channel

    def info(self, message: str) -> None:
        with self.lock:
            print(f"\n[HOST {timestamp()}] {message}", flush=True)

    def switch_channel(self) -> str:
        """Switch interactive TX and live RX view; both capture logs remain on."""
        with self.lock:
            # Finish the displayed partial line before switching views.
            for label in ("USB", "INNER"):
                if self._is_visible(label):
                    self._flush_partial(label)
            self.active_channel = "INNER" if self.active_channel == "USB" else "USB"
            self.show_inner = False
            mode = "UART / ST-LINK (single keys, no Enter)" if self.active_channel == "INNER" else "USB CDC (CLI + Enter)"
            print(f"\n[HOST {timestamp()}] ESC -> {mode}. Press ESC to switch back.", flush=True)
            return self.active_channel

    def receive(self, label: str, text: str) -> None:
        if not text or self.quiet:
            return
        with self.lock:
            if not self._is_visible(label):
                return
            # Serial reads can split CRLF anywhere. Consume LF once even if
            # its CR was in the preceding read; keep device ANSI bytes intact.
            normalized = []
            for char in text:
                if char == "\n" and self.previous_cr[label]:
                    self.previous_cr[label] = False
                    continue
                self.previous_cr[label] = char == "\r"
                normalized.append("\n" if char == "\r" else char)
            pending = self.pending[label] + "".join(normalized)
            lines = pending.split("\n")
            for line in lines[:-1]:
                print(f"[{label}] {line}", flush=True)
            self.pending[label] = lines[-1]
            if self.pending[label].endswith("n6> ") or len(self.pending[label]) > 512:
                self._flush_partial(label)

    def flush_partial(self, label: str) -> None:
        if self.quiet:
            return
        with self.lock:
            if self._is_visible(label):
                self._flush_partial(label)

    def _flush_partial(self, label: str) -> None:
        if self.pending[label]:
            print(f"[{label}] {self.pending[label]}", flush=True)
            self.pending[label] = ""


class PortCapture(threading.Thread):
    def __init__(self, role: str, override: str | None, baud: int,
                 log: CaptureLog, console: ConsoleOutput, stop: threading.Event) -> None:
        super().__init__(name=f"capture-{role}", daemon=True)
        self.role = role
        self.override = override
        self.baud = baud
        self.log = log
        self.console = console
        self.stop = stop
        self.serial_lock = threading.Lock()
        self.connection: serial.Serial | None = None
        self.device: str | None = None
        self.last_problem: str | None = None

    def _report_problem(self, problem: str) -> None:
        if problem != self.last_problem:
            self.last_problem = problem
            self.log.event(problem)
            self.console.info(f"{self.role}: {problem}")

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                device = choose_port(self.role, port_inventory(), self.override)
                if device is None:
                    self._report_problem("port not found or ambiguous; check 'ports' / overrides")
                    self.stop.wait(1.0)
                    continue
                connection: serial.Serial | None = None
                try:
                    connection = serial.Serial(device, self.baud, timeout=0.2, write_timeout=1.0)
                    if self.role == "USB":
                        connection.dtr = True
                except (OSError, serial.SerialException) as exc:
                    if connection is not None and connection.is_open:
                        connection.close()
                    self._report_problem(f"cannot open {device}: {exc}; close Tera Term if it owns the port")
                    self.stop.wait(2.0)
                    continue

                assert connection is not None
                with self.serial_lock:
                    self.connection = connection
                    self.device = device
                self.last_problem = None
                self.log.event(f"connected {device} at {self.baud} baud")
                self.console.info(f"{self.role}: connected to {device}")
                try:
                    idle_since = time.monotonic()
                    last_port_check = idle_since
                    while not self.stop.is_set():
                        data = connection.read(min(max(connection.in_waiting, 1), 4096))
                        if data:
                            self.console.receive(self.role, self.log.receive(data))
                            idle_since = time.monotonic()
                        elif time.monotonic() - idle_since > 0.3:
                            self.console.flush_partial(self.role)
                        now = time.monotonic()
                        if now - last_port_check >= 2.0:
                            last_port_check = now
                            current = choose_port(self.role, port_inventory(), self.override)
                            if current != device:
                                raise serial.SerialException(
                                    f"port identity changed from {device} to {current or 'missing'}")
                except (OSError, serial.SerialException) as exc:
                    self._report_problem(f"{device} disconnected/read failed: {exc}; reconnecting")
                finally:
                    with self.serial_lock:
                        self.connection = None
                        self.device = None
                        connection.close()
                    self.console.flush_partial(self.role)
                    self.log.event(f"disconnected {device}")
            except Exception as exc:
                # Keep the other capture alive if discovery itself fails transiently.
                self._report_problem(f"capture error: {type(exc).__name__}: {exc}")
            self.stop.wait(1.0)

    def send(self, data: bytes, description: str) -> bool:
        with self.serial_lock:
            if self.connection is None:
                self.console.info(f"{self.role}: not connected; command not queued")
                return False
            try:
                self.connection.write(data)
                self.connection.flush()
            except (OSError, serial.SerialException, serial.SerialTimeoutException) as exc:
                self.console.info(f"{self.role}: send failed: {exc}")
                return False
        # Do not persist commands: Wi-Fi passwords and Cloud tokens can be sensitive.
        self.log.event(f"host sent {description} ({len(data)} bytes; content omitted)")
        return True


def print_ports(console: ConsoleOutput, usb: PortCapture | None = None,
                inner: PortCapture | None = None) -> None:
    ports = port_inventory()
    if not ports:
        console.info("No COM ports detected")
    for port in ports:
        console.info(f"{port.device}: {port.description} (VID:PID={port.vid!s}:{port.pid!s})")
    for worker in (usb, inner):
        if worker is not None:
            console.info(f"{worker.role} capture: {worker.device or 'waiting'}")


HELP = """ESC (press directly, no Enter) switches interactive send + live output:
  USB CDC mode           type CLI commands, then Enter
  UART / ST-LINK mode    press a single key immediately, without Enter:
                         ? a r t c u R T C U n 0
  ESC again              switch back to USB CDC
  Both COM channels are ALWAYS recorded to separate log files.

USB CDC commands:
  ports                  show discovered ports and capture connections
  usb <CLI command>      send any N6 CLI command over USB CDC
  ble [status|...]       shortcut to USB CLI 'ble ...' (not a BLE GATT link)
  wifi [status|...]      shortcut to USB CLI 'wifi ...'
  radio [status|...]     shortcut to USB CLI 'radio ...'
  ping [token]           send 'debug ping <token>' over USB
  status                 radio status, ble status, wifi status, debug uart
  inner <key>            send one UART key without changing view
  bleprobe [seconds]     run the existing BLE GATT wifi-blocking probe
  mark <text>            add a timestamped marker to both files
  quit                   stop capture and close both COM ports
Examples: wifi status | wifi scan | ble status | inner n | usb debug uart
For 'wifi connect "SSID"', password input is hidden and never logged.
"""


def read_console_event(active_channel: str) -> tuple[str, str]:
    """Read ESC immediately on Windows, without waiting for Enter.

    A normal line-based fallback is retained for non-Windows terminals and
    redirected/automated input; typing 'esc' + Enter switches there.
    """
    if sys.platform != "win32" or not sys.stdin.isatty():
        line = input(f"n6-{active_channel.lower()}> ").strip()
        return ("switch", "") if line.lower() == "esc" else ("line", line)

    import msvcrt

    prompt = f"n6-{active_channel.lower()}> "
    print(prompt, end="", flush=True)
    buffer: list[str] = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # Consume an extended key (arrows/function keys).
            continue
        if ch == "\x1b":
            # Drop unfinished USB input rather than silently send it to UART.
            print(flush=True)
            return "switch", ""
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x1a":
            raise EOFError
        if active_channel == "INNER":
            if ch in INNER_KEYS:
                print(ch, flush=True)
                return "uart-key", ch
            # No Enter required in UART mode. Ignore CR/LF and other keys.
            if ch not in ("\r", "\n"):
                print(f"\n[HOST] Unsupported UART key {ch!r}; use ? a r t c u R T C U n 0, or ESC.", flush=True)
                print(prompt, end="", flush=True)
            continue
        if ch in ("\r", "\n"):
            print(flush=True)
            return "line", "".join(buffer).strip()
        if ch == "\x08":
            if buffer:
                buffer.pop()
                print("\b \b", end="", flush=True)
            continue
        if ch.isprintable():
            buffer.append(ch)
            print(ch, end="", flush=True)


def command_loop(usb: PortCapture, inner: PortCapture, console: ConsoleOutput,
                 logs: tuple[CaptureLog, CaptureLog]) -> None:
    console.info("ESC instantly switches USB CDC <-> UART (send + live display).")
    console.info("USB: type CLI + Enter. UART: press ? a r t c u R T C U n 0 (no Enter).")
    console.info("Both ports ALWAYS log to files. Type help in USB mode, quit to stop.")
    console.info("Close Tera Term first if it owns either COM port.")
    while True:
        try:
            event, line = read_console_event(console.active_channel)
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if event == "switch":
            console.switch_channel()
            for log in logs:
                log.event(f"host selected {console.active_channel} live view and input")
            continue
        if console.active_channel == "INNER":
            if event == "uart-key":
                inner.send(line.encode("ascii"), "INNER one-key")
            elif len(line) == 1 and line in INNER_KEYS:
                # Line-based fallback for automated/non-Windows invocations.
                inner.send(line.encode("ascii"), "INNER one-key")
            elif line.lower() in ("quit", "exit", "q"):
                return
            elif line:
                console.info("UART expects one key: ? a r t c u R T C U n 0; press ESC to return to USB.")
            continue
        if not line:
            continue
        command, _, tail = line.partition(" ")
        key = command.lower()
        if key in ("quit", "exit", "q"):
            return
        if key in ("help", "?"):
            print(HELP)
        elif key == "ports":
            print_ports(console, usb, inner)
        elif key == "mark":
            if not tail.strip():
                console.info("Usage: mark <text>")
            else:
                marker = re.sub(r"[\r\n]", " ", tail.strip())
                for log in logs:
                    log.event(f"MARK {marker}")
                console.info(f"MARK {marker}")
        elif key == "inner":
            if len(tail.strip()) != 1 or tail.strip() not in INNER_KEYS:
                console.info("inner needs one key: ? a r t c u R T C U n 0")
            else:
                inner.send(tail.strip().encode("ascii"), "INNER one-key")
        elif key == "bleprobe":
            try:
                seconds = int(tail.strip() or "45")
                if not 1 <= seconds <= 300:
                    raise ValueError
            except ValueError:
                console.info("Usage: bleprobe [seconds 1..300]")
                continue
            probe = PROJECT_DIR / "hil_tests" / "ble_inspector.py"
            console.info(f"Starting BLE GATT probe for {seconds}s; COM capture continues")
            result = subprocess.run(
                [sys.executable, str(probe), "--pair", "--uncached-services",
                 "--probe", "wifi-blocking",
                 "--probe-seconds", str(seconds)], cwd=PROJECT_DIR, check=False,
            )
            console.info(f"BLE probe exit code: {result.returncode}")
        elif key == "status":
            for request in ("radio status", "ble status", "wifi status", "debug uart"):
                if not usb.send((request + "\r").encode("utf-8"), "USB CLI command"):
                    break
                time.sleep(0.15)
        else:
            if key == "usb":
                request = tail.strip()
            elif key == "ping":
                request = "debug ping " + (tail.strip() or "host")
            elif key in ("ble", "wifi", "radio"):
                request = key + " " + (tail.strip() or "status")
            else:
                console.info("Unknown command; use 'help' or 'usb <CLI command>'")
                continue
            if not request:
                console.info("Usage: usb <CLI command>")
                continue
            if usb.send((request + "\r").encode("utf-8"), "USB CLI command") \
                    and request.lower().startswith("wifi connect "):
                password = getpass.getpass("Wi-Fi password (hidden): ")
                usb.send((password + "\r").encode("utf-8"), "hidden Wi-Fi password")
                password = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb-port", help="Explicit N6 USB CDC COM port")
    parser.add_argument("--inner-port", help="Explicit ST-LINK debug UART COM port")
    parser.add_argument("--usb-baud", type=int, default=115200)
    parser.add_argument("--inner-baud", type=int, default=115200)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--quiet", action="store_true", help="Write logs without echoing device lines")
    parser.add_argument("--live-inner", action="store_true",
                        help="Also echo the busy ST-LINK debug UART to the console")
    parser.add_argument("--list-ports", action="store_true", help="Show COM inventory and exit")
    args = parser.parse_args()
    ansi_enabled = enable_ansi_output()
    console = ConsoleOutput(args.quiet, args.live_inner)
    if sys.stdout.isatty() and not ansi_enabled:
        console.info("ANSI colors unavailable in this console; try Windows Terminal.")
    if args.list_ports:
        print_ports(console)
        return 0
    if args.usb_port and args.inner_port and args.usb_port.upper() == args.inner_port.upper():
        parser.error("USB and INNER must be different COM ports")
    if args.usb_baud <= 0 or args.inner_baud <= 0:
        parser.error("baud rates must be positive")
    available = port_inventory()
    usb_device = choose_port("USB", available, args.usb_port)
    inner_device = choose_port("INNER", available, args.inner_port)
    if usb_device is not None and usb_device == inner_device:
        parser.error("USB and INNER resolve to the same COM port")

    run_dir = make_run_directory(args.log_root)
    inner_log = CaptureLog(run_dir / "COM_INNER_LOGS.txt", "INNER")
    usb_log = CaptureLog(run_dir / "COM_LOGS.txt", "USB")
    stop = threading.Event()
    usb = PortCapture("USB", args.usb_port, args.usb_baud, usb_log, console, stop)
    inner = PortCapture("INNER", args.inner_port, args.inner_baud, inner_log, console, stop)
    console.info(f"INNER log: {inner_log.path}")
    console.info(f"USB log:   {usb_log.path}")
    print_ports(console)
    try:
        usb.start()
        inner.start()
        command_loop(usb, inner, console, (inner_log, usb_log))
    finally:
        stop.set()
        usb.join(timeout=3.0) if usb.ident is not None else None
        inner.join(timeout=3.0) if inner.ident is not None else None
        inner_log.close()
        usb_log.close()
        console.info(f"Saved logs in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
