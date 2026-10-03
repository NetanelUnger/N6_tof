"""Automate the repeated RAM-boot Milestone 3/4 BLE responsiveness gate.

The runner deliberately reuses the existing RAM loader and BLE inspector.  It
adds the missing orchestration: CN8 preflight, concurrent USB pings, postflight
diagnostics, consecutive-boot accounting, and one atomic JSON summary.  A
failed first BLE prompt remains a failed boot; diagnostic retries are never
silently converted into a pass.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

from serial import Serial
from serial.tools import list_ports


ROOT = Path(__file__).resolve().parents[1]
BLE_INSPECTOR = ROOT / "hil_tests" / "ble_inspector.py"
RAM_LOADER = ROOT / "Tools" / "Debug-NonSecureRam.ps1"
DEFAULT_REPORT = ROOT / "hil_tests" / "results" / "milestone4_gate.json"
USB_VID = 0x0483
USB_PID = 0x5740


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True),
                         encoding="utf-8")
    last_error: PermissionError | None = None
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 39:
                time.sleep(min(0.05 * (attempt + 1), 0.25))
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass
    assert last_error is not None
    raise last_error


def find_cn8(requested: str | None, timeout: float = 35.0) -> str:
    if requested:
        return requested
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [port.device for port in list_ports.comports()
                   if port.vid == USB_VID and port.pid == USB_PID]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(
                "more than one CN8 USB CDC port was found; pass --port COMx")
        time.sleep(0.5)
    raise RuntimeError("CN8 USB CDC port did not enumerate")


class UsbCli:
    def __init__(self, port: str) -> None:
        self.serial = Serial(port, 115200, timeout=0.1, write_timeout=2.0)
        self.serial.dtr = True
        self.lock = threading.Lock()
        time.sleep(0.6)
        self.serial.reset_input_buffer()
        self.serial.write(b"\r")
        self._read(1.2)

    def close(self) -> None:
        self.serial.close()

    def _read(self, timeout: float, prompt: bool = False) -> str:
        deadline = time.monotonic() + timeout
        data = bytearray()
        prompt_seen = False
        settle_until = 0.0
        while time.monotonic() < deadline:
            waiting = self.serial.in_waiting
            if waiting:
                data.extend(self.serial.read(waiting))
                if prompt and b"n6> " in data:
                    prompt_seen = True
                    settle_until = time.monotonic() + 0.12
            elif prompt_seen and time.monotonic() >= settle_until:
                break
            else:
                time.sleep(0.02)
        return data.decode("utf-8", errors="replace")

    def command(self, command: str, timeout: float = 4.0) -> str:
        with self.lock:
            self._read(0.15)
            self.serial.write(command.encode("utf-8") + b"\r")
            return self._read(timeout, prompt=True)


def run_process(command: list[str], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True,
        timeout=timeout, encoding="utf-8", errors="replace")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def load_ram() -> dict[str, Any]:
    return run_process([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(RAM_LOADER), "-NoBuild", "-Run",
    ], timeout=150.0)


def extract_frame(text: str) -> int | None:
    match = re.search(r"Frame:\s*(\d+)", text)
    return int(match.group(1)) if match else None


def collect_preflight(cli: UsbCli) -> tuple[dict[str, str], list[str]]:
    radio = cli.command("radio status", 5.0)
    ble = cli.command("ble status", 5.0)
    tof_first = cli.command("tof status", 5.0)
    time.sleep(1.0)
    tof_second = cli.command("tof status", 5.0)
    wifi = cli.command("wifi status", 5.0)
    failures: list[str] = []
    if "manager: ready" not in radio or "W6X_Init: passed" not in radio:
        failures.append("radio manager/W6X_Init is not ready")
    if not all(item in radio for item in (
            "BLE maintenance GATT: ready", "Wi-Fi services: enabled")):
        failures.append("radio feature preflight failed")
    if "BLE GATT: ready" not in ble or "advertising: on" not in ble:
        failures.append("BLE GATT is not ready/advertising")
    first_frame = extract_frame(tof_first)
    second_frame = extract_frame(tof_second)
    if ("ToF state: ready" not in tof_first
            or "ToF state: ready" not in tof_second
            or first_frame is None or second_frame is None
            or second_frame <= first_frame):
        failures.append("ToF is not ready or its frame counter did not advance")
    return ({
        "radio_status": radio,
        "ble_status": ble,
        "tof_status_first": tof_first,
        "tof_status_second": tof_second,
        "wifi_status": wifi,
    }, failures)


def collect_postflight(cli: UsbCli) -> tuple[dict[str, str], list[str]]:
    values = {
        "radio_status": cli.command("radio status", 5.0),
        "ble_status": cli.command("ble status", 6.0),
        "wifi_status": cli.command("wifi status", 5.0),
        "tof_status": cli.command("tof status", 5.0),
        "debug_uart": cli.command("debug uart", 5.0),
        "debug_route": cli.command("debug route", 5.0),
    }
    failures: list[str] = []
    radio = values["radio_status"]
    ble = values["ble_status"]
    if "manager: ready" not in radio or "W6X_Init: passed" not in radio:
        failures.append("radio stopped being ready")
    # The firmware fields retain legacy *_ticks names, but their source is
    # HAL_GetTick() (milliseconds). Accept either CLI spelling while older
    # images are still used by the gate.
    gaps = [int(value) for value in re.findall(
        r"max_gap_(?:ms|ticks)=(\d+)", radio)]
    if not gaps or max(gaps) > 500:
        failures.append(f"radio/BLE loop gap missing or exceeded 500 ms: {gaps}")
    cli_drop = re.search(
        r"CLI TX:.*?dropped\s+(\d+)/(\d+)", ble, re.DOTALL)
    if cli_drop is None or any(int(value) for value in cli_drop.groups()):
        failures.append("BLE CLI TX reported a drop")
    contention = re.search(
        r"CLI TX contention:.*?streak\s+(\d+)/(\d+)", ble, re.DOTALL)
    if contention is None or int(contention.group(1)) != 0:
        failures.append("BLE CLI contention streak did not recover to zero")
    if "link: disconnected, advertising: on" not in ble:
        failures.append("BLE did not return to disconnected advertising state")
    if "ToF state: ready" not in values["tof_status"]:
        failures.append("ToF is not ready after the probe")
    if "operation in progress" in values["wifi_status"]:
        failures.append("Wi-Fi operation remained active after the probe")
    for field in ("stale", "write_errors", "deferred_overflow"):
        match = re.search(rf"\b{field}[=: ]+(\d+)", values["debug_route"])
        if match is not None and int(match.group(1)) != 0:
            failures.append(f"debug route {field} is nonzero")
    return values, failures


def wait_for_ble_idle(cli: UsbCli, timeout: float = 8.0) -> list[str]:
    """Wait for the asynchronous NCP disconnect event and advertising restart."""

    observations: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = cli.command("radio status", 4.0)
        observations.append(status)
        if ("link: disconnected" in status
                and "advertising: on" in status):
            break
        time.sleep(0.5)
    return observations


def usb_ping_worker(cli: UsbCli, attempt: int, count: int, duration: float,
                    start: threading.Event, output: list[dict[str, Any]]) -> None:
    if not start.wait(timeout=35.0):
        return
    began = time.monotonic()
    interval = max(0.2, duration / max(1, count))
    for index in range(1, count + 1):
        target = began + ((index - 1) * interval)
        if target > time.monotonic():
            time.sleep(target - time.monotonic())
        token = f"auto-a{attempt}-{index:02d}"
        sent = time.monotonic()
        try:
            response = cli.command(f"debug ping {token}", 1.4)
            passed = re.search(rf"PONG\s+{re.escape(token)}\s+\d+", response) is not None
            output.append({
                "token": token,
                "passed": passed,
                "elapsed_ms": round((time.monotonic() - sent) * 1000.0, 3),
                "response": response,
            })
        except Exception as exc:  # Preserve the exact host failure in JSON.
            output.append({"token": token, "passed": False,
                           "error": f"{type(exc).__name__}: {exc}"})


def run_ble_probe(attempt: int, duration: float, report: Path, cli: UsbCli,
                  usb_ping_count: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report_mtime_before = report.stat().st_mtime_ns if report.exists() else None
    command = [
        sys.executable, str(BLE_INSPECTOR), "--pair", "--uncached-services",
        "--probe", "wifi-blocking", "--probe-seconds", str(duration),
        "--report", str(report),
    ]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
        env=environment)
    lines: list[str] = []
    measurement_started = threading.Event()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            print(line, end="", flush=True)
            if "Starting wifi-blocking latency probe" in line:
                measurement_started.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    usb_results: list[dict[str, Any]] = []
    pinger = threading.Thread(
        target=usb_ping_worker,
        args=(cli, attempt, usb_ping_count, duration,
              measurement_started, usb_results), daemon=True)
    pinger.start()
    timed_out = False
    try:
        exit_code = process.wait(timeout=duration + 65.0)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        exit_code = process.wait(timeout=10.0)
    reader.join(timeout=5.0)
    pinger.join(timeout=duration + 5.0)
    parsed: dict[str, Any] | None = None
    if (report.exists() and
            (report_mtime_before is None or
             report.stat().st_mtime_ns != report_mtime_before)):
        try:
            parsed = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = None
    return ({
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "measurement_started": measurement_started.is_set(),
        "output": "".join(lines),
        "report_path": str(report),
        "report": parsed,
    }, usb_results)


def report_probe_passed(probe: dict[str, Any]) -> bool:
    report = probe.get("report")
    if not isinstance(report, dict) or not report.get("ok"):
        return False
    latency = report.get("latency_probe")
    return bool(isinstance(latency, dict) and latency.get("passed"))


def run_attempt(arguments: argparse.Namespace, attempt: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempt": attempt, "started_utc": utc_now(), "passed": False,
    }
    if not arguments.skip_ram_load:
        print(f"\n=== attempt {attempt}: loading fresh RAM image ===", flush=True)
        result["ram_load"] = load_ram()
        if result["ram_load"]["exit_code"] != 0:
            result["failure"] = "RAM load failed"
            result["finished_utc"] = utc_now()
            return result
    try:
        port = find_cn8(arguments.port)
        result["port"] = port
        cli = UsbCli(port)
    except Exception as exc:
        result["failure"] = f"CN8 open failed: {type(exc).__name__}: {exc}"
        result["finished_utc"] = utc_now()
        return result
    try:
        print(f"=== attempt {attempt}: CN8 preflight on {port} ===", flush=True)
        preflight, preflight_failures = collect_preflight(cli)
        result["preflight"] = preflight
        result["preflight_failures"] = preflight_failures
        if preflight_failures:
            result["failure"] = "; ".join(preflight_failures)
            return result

        probe_report = (arguments.report.parent /
                        f"{arguments.report.stem}_attempt_{attempt:02d}_ble.json")
        print(f"=== attempt {attempt}: BLE/Wi-Fi probe + USB pings ===",
              flush=True)
        probe, usb_pings = run_ble_probe(
            attempt, arguments.probe_seconds, probe_report, cli,
            arguments.usb_pings)
        result["ble_probe"] = probe
        result["usb_pings"] = usb_pings
        result["ble_release_wait"] = wait_for_ble_idle(cli)
        postflight, postflight_failures = collect_postflight(cli)
        result["postflight"] = postflight
        result["postflight_failures"] = postflight_failures
        usb_started = bool(probe["measurement_started"])
        usb_passed = (usb_started and len(usb_pings) == arguments.usb_pings
                      and all(item.get("passed") for item in usb_pings))
        result["usb_summary"] = {
            "requested": arguments.usb_pings,
            "received": sum(bool(item.get("passed")) for item in usb_pings),
            "passed": usb_passed,
            "skipped": not usb_started,
        }
        failures = list(postflight_failures)
        if not report_probe_passed(probe):
            failures.append("BLE latency probe failed")
        if usb_started and not usb_passed:
            failures.append("concurrent USB ping series failed")
        result["failures"] = failures
        result["passed"] = not failures
        if failures:
            result["failure"] = "; ".join(failures)
        return result
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        cli.close()
        result["finished_utc"] = utc_now()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automated consecutive RAM-boot M3.7/M4 BLE gate")
    parser.add_argument("--required-passes", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=7)
    parser.add_argument("--probe-seconds", type=float, default=45.0)
    parser.add_argument("--usb-pings", type=int, default=24)
    parser.add_argument("--port", help="CN8 port, for example COM8")
    parser.add_argument("--skip-ram-load", action="store_true",
                        help="test the currently running image once")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    arguments.report = arguments.report.resolve()
    if (arguments.required_passes < 1 or arguments.max_attempts < 1
            or arguments.max_attempts < arguments.required_passes
            or arguments.probe_seconds <= 5.0 or arguments.usb_pings < 1):
        raise SystemExit("invalid pass/attempt/probe arguments")
    if arguments.skip_ram_load:
        arguments.required_passes = 1
        arguments.max_attempts = 1
    summary: dict[str, Any] = {
        "schema": 1,
        "started_utc": utc_now(),
        "required_consecutive_passes": arguments.required_passes,
        "max_attempts": arguments.max_attempts,
        "probe_seconds": arguments.probe_seconds,
        "usb_pings_per_attempt": arguments.usb_pings,
        "attempts": [],
        "consecutive_passes": 0,
        "passed": False,
    }
    for attempt in range(1, arguments.max_attempts + 1):
        attempt_result = run_attempt(arguments, attempt)
        summary["attempts"].append(attempt_result)
        if attempt_result.get("passed"):
            summary["consecutive_passes"] += 1
            print(f"=== attempt {attempt}: PASS; consecutive "
                  f"{summary['consecutive_passes']}/{arguments.required_passes} ===")
        else:
            summary["consecutive_passes"] = 0
            print(f"=== attempt {attempt}: FAIL: "
                  f"{attempt_result.get('failure', 'unknown failure')} ===")
        summary["passed"] = (
            summary["consecutive_passes"] >= arguments.required_passes)
        summary["updated_utc"] = utc_now()
        atomic_json(arguments.report, summary)
        if summary["passed"]:
            break
        remaining_attempts = arguments.max_attempts - attempt
        if summary["consecutive_passes"] + remaining_attempts < arguments.required_passes:
            summary["stopped_reason"] = (
                "required consecutive passes are no longer reachable")
            break
    summary["finished_utc"] = utc_now()
    atomic_json(arguments.report, summary)
    print(f"\nMilestone gate {'PASS' if summary['passed'] else 'FAIL'}: "
          f"{summary['consecutive_passes']}/{arguments.required_passes} "
          f"consecutive passes. Report: {arguments.report}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
