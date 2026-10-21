"""Shared capture-source contract. Hardware access never belongs to Tk widgets."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
import time
from typing import Protocol
import uuid

from protocol import DepthFrame, FrameReader


class SourceError(RuntimeError):
    pass


@dataclass
class SourceStats:
    state: str = "closed"
    received: int = 0
    crc_errors: int = 0
    framing_errors: int = 0
    discarded_bytes: int = 0
    buffered_bytes: int = 0
    timeouts: int = 0
    counter_resets: int = 0
    last_error: str | None = None


@dataclass(frozen=True)
class Sample:
    frame: DepthFrame
    device_id: str
    boot_id: str
    connection_id: str
    source: str
    received_utc: str
    received_monotonic_ns: int
    channel: int = 1
    device_info: dict | None = None


class SampleSource(Protocol):
    stats: SourceStats
    def open(self) -> None: ...
    def read(self, timeout: float = 3) -> Sample: ...
    def stop(self) -> None: ...
    def status(self) -> dict: ...


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def find_usb(requested=None):
    from serial.tools import list_ports
    candidates = [p for p in list_ports.comports() if p.vid == 0x0483 and p.pid == 0x5740]
    if requested:
        candidates = [p for p in candidates if p.device.upper() == requested.upper()]
    if len(candidates) != 1:
        raise SourceError("BLOCKED: select exactly one present N6 CN8 device (0483:5740).")
    return candidates[0]


class UsbSampleSource:
    kind = "usb"
    def __init__(self, port=None, *, expected_device=None):
        self.requested_port = port
        self.expected_device = expected_device
        self.stats = SourceStats()
        self._serial = None
        self._reader = None
        self.owns_stream = False
        self.before = {}
        self.after = {}
        self.restore_error = None
        self.previous = None
        self.device_id = self.boot_id = None
        self.connection_id = uuid.uuid4().hex

    def command(self, command, expected=None, timeout=3):
        self._serial.write((command + "\r").encode("ascii"))
        self._serial.flush()
        response = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response.extend(self._serial.read(8192))
            if b"\r\nn6> " in response and (expected is None or expected in response):
                return response.decode("utf-8", "replace")
            if len(response) > 131072:
                raise SourceError("Command response exceeded its bounded window.")
        raise SourceError(f"BLOCKED: device command timed out: {command.split()[0]}")

    def open(self):
        from serial import Serial
        port = find_usb(self.requested_port)
        self.port = port.device
        try:
            self._serial = Serial(port.device, 115200, timeout=.1, write_timeout=2)
            # Accept only a closed host port. Never disconnect another client.
            time.sleep(.15)
            self._serial.reset_input_buffer()
            ble = self.command("ble status", b"BLE GATT:")
            if re.search(r"link:\s*connected\b", ble):
                raise SourceError("BLOCKED: another BLE client is connected; capture did not take its route.")
            tof = self.command("tof status", b"ToF state:")
            dataset = self.command("dataset stream status", b"Dataset stream:")
            self.before = {"tof": tof, "dataset": dataset}
            if "Dataset stream: on" in dataset or re.search(r"Map:\s*on\b", tof):
                raise SourceError("BLOCKED: existing image/dataset stream is active; no takeover was performed.")
            if "ToF state: ready" not in tof or "acquisition: running" not in tof:
                raise SourceError("BLOCKED: sensor is not running and ready.")
            route = re.search(r"Image destination: requested (\w+)", tof)
            if not route:
                raise SourceError("BLOCKED: firmware does not report its image route.")
            self.previous_route = route[1].lower()
            info = self.command("radio info", b"NCP MAC:")
            mac = re.search(r"NCP MAC:\s*([0-9A-Fa-f:]{17})", info)
            if mac is None:
                raise SourceError("BLOCKED: cannot establish the device identity.")
            self.device_id = "n6:" + mac[1].lower()
            if self.expected_device and self.device_id.lower() != self.expected_device.lower():
                raise SourceError("BLOCKED: connected device differs from the selected target.")
            version = self.command("version", b"Firmware version:")
            self.device_info = {"firmware_version": re.search(r"Firmware version:\s*(\d+)", version)[1],
                                "usb_serial": port.serial_number, "identity_source": "NCP MAC"}
            sdk = re.search(r"SDK:\s*([\d.]+)", info)
            self.device_info["ncp_sdk"] = sdk[1] if sdk else None
            identity = self.command("dataset session", b"Dataset session:")
            match = re.search(r"Dataset session:\s*([a-f0-9]{32})", identity)
            if match is None:
                identity = self.command("dataset session " + uuid.uuid4().hex, b"Dataset session:")
                match = re.search(r"Dataset session:\s*([a-f0-9]{32})", identity)
            if match is None:
                raise SourceError("BLOCKED: firmware lacks RAM capture identity support.")
            self.boot_id = match[1]
            # New start sequence changes only this source's stream/route.
            self._serial.reset_input_buffer()
            self._serial.write(b"dataset stream on\r")
            self._serial.flush()
            self.owns_stream = True
            self._reader = FrameReader(self._serial)
            self.stats.state = "streaming"
        except Exception:
            self.stop()
            raise

    def read(self, timeout=3):
        if self.stats.state != "streaming":
            raise SourceError("Source is not open.")
        try:
            frame = self._reader.read_frame(timeout)
            self.stats.received += 1
            if self.previous and frame.timestamp_ms != self.previous.timestamp_ms:
                delta = (frame.frame_id - self.previous.frame_id) & 0xffffffff
                if delta == 0 or delta > 0x80000000:
                    self.stats.counter_resets += 1
            self.previous = frame
            return Sample(frame, self.device_id, self.boot_id, self.connection_id,
                          self.kind, utc_now(), time.monotonic_ns(), device_info=self.device_info)
        except TimeoutError as exc:
            self.stats.timeouts += 1
            self.stats.last_error = str(exc)
            raise
        finally:
            self.stats.crc_errors = self._reader.crc_errors
            self.stats.framing_errors = self._reader.framing_errors
            self.stats.discarded_bytes = self._reader.discarded_bytes
            self.stats.buffered_bytes = len(self._reader.buffer)
            self.stats.last_error = self._reader.last_error or self.stats.last_error

    def stop(self):
        if self._serial is None:
            self.stats.state = "closed"
            return
        try:
            if self.owns_stream:
                self.command("dataset stream off", b"Dataset stream disabled", timeout=4)
                self.owns_stream = False
                self._serial.reset_input_buffer()
                self.command("dataset route " + self.previous_route, b"Capture route restored.")
                self.after["tof"] = self.command("tof status", b"ToF state:")
                self.after["dataset"] = self.command("dataset stream status", b"Dataset stream:")
                if ("Dataset stream: off" not in self.after["dataset"] or
                        f"requested {self.previous_route.upper()}" not in self.after["tof"]):
                    raise SourceError("Runtime stream/route restoration was not confirmed.")
        except Exception as exc:
            self.restore_error = str(exc)
            self.stats.last_error = str(exc)
        finally:
            self._serial.close()
            self._serial = None
            self._reader = None
            self.stats.state = "closed"

    def status(self):
        return {**asdict(self.stats), "source": self.kind, "device_id": self.device_id,
                "boot_id": self.boot_id, "connection_id": self.connection_id,
                "before": self.before, "after": self.after, "restore_error": self.restore_error}


def create_source(kind="usb", **options):
    if kind == "usb":
        return UsbSampleSource(**{k:v for k,v in options.items() if k in {"port","expected_device"}})
    if kind == "ble":
        from ble_sample_source import BleSampleSource
        return BleSampleSource(**options)
    raise SourceError(f"BLOCKED: {kind} capture adapter is not installed yet.")
