"""Interactive BLE scan, GATT-discovery, and bounded-stream HIL utility."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import struct
import sys
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


HIL_ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = HIL_ROOT / "results" / "ble_last.json"
N6_UUID_LABELS = {
    "7a1e0001-b5a3-f393-e0a9-e50e24dcca9e": "N6 CLI service",
    "7a1e0002-b5a3-f393-e0a9-e50e24dcca9e": "N6 CLI RX",
    "7a1e0003-b5a3-f393-e0a9-e50e24dcca9e": "N6 CLI TX",
    "7a1e0004-b5a3-f393-e0a9-e50e24dcca9e": "N6 ToF image TX",
    "7a1e0101-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG service",
    "7a1e0102-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG RX",
    "7a1e0103-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG TX",
}
N6_REQUIRED_PROPERTIES = {
    "7a1e0002-b5a3-f393-e0a9-e50e24dcca9e": {"write", "write-without-response"},
    "7a1e0003-b5a3-f393-e0a9-e50e24dcca9e": {"notify"},
    "7a1e0004-b5a3-f393-e0a9-e50e24dcca9e": {"notify"},
    "7a1e0102-b5a3-f393-e0a9-e50e24dcca9e": {"write", "write-without-response"},
    "7a1e0103-b5a3-f393-e0a9-e50e24dcca9e": {"notify"},
}
N6_STREAM_UUIDS = {
    "cli": {
        "rx": "7a1e0002-b5a3-f393-e0a9-e50e24dcca9e",
        "tx": "7a1e0003-b5a3-f393-e0a9-e50e24dcca9e",
    },
    "debug": {
        "rx": "7a1e0102-b5a3-f393-e0a9-e50e24dcca9e",
        "tx": "7a1e0103-b5a3-f393-e0a9-e50e24dcca9e",
    },
    "tof": {
        "tx": "7a1e0004-b5a3-f393-e0a9-e50e24dcca9e",
    },
}

TOF_IMAGE_MAGIC = 0x364E
TOF_IMAGE_VERSION = 1
TOF_IMAGE_HEADER_SIZE = 20
TOF_IMAGE_FLAG_START = 0x01
TOF_IMAGE_FLAG_END = 0x02
TOF_IMAGE_FLOAT32_LE = 1
TOF_IMAGE_MAX_PAYLOAD = 54 * 42 * 4

LATENCY_PING_INTERVAL_SECONDS = 0.200
LATENCY_STALLED_REPLY_SECONDS = 1.0
LATENCY_LIMIT_MS = 250.0
DEFAULT_LATENCY_PROBE_SECONDS = 10.0
DEFAULT_WIFI_BLOCKING_PROBE_SECONDS = 45.0
DEFAULT_REPLY_GRACE_SECONDS = 3.0
WIFI_TRIGGER_AFTER_SECONDS = 2.0

PONG_PATTERN = re.compile(r"PONG\s+(\S+)\s+(\d+)")
RADIO_LOOP_PATTERN = re.compile(
    r"Radio loop:\s+count=(\d+)\s+last_tick=(\d+)\s+"
    r"max_gap_ticks=(\d+)")
BLE_TX_PUMP_PATTERN = re.compile(
    r"BLE TX pump:\s+last_tick=(\d+)\s+max_gap_ticks=(\d+)")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def bytes_to_hex(value: bytes | bytearray) -> str:
    return bytes(value).hex().upper()


def parse_command(line: str) -> list[str]:
    """Parse one REPL line with normal quoted-argument handling."""

    # The REPL arguments are BLE selectors rather than Windows paths. POSIX
    # parsing gives consistent quote removal on every supported host.
    return shlex.split(line, posix=True)


def serialize_advertisement(device: Any, advertisement: Any) -> dict[str, Any]:
    manufacturer_data = {
        f"0x{int(company):04X}": bytes_to_hex(payload)
        for company, payload in advertisement.manufacturer_data.items()
    }
    service_data = {
        str(uuid).lower(): bytes_to_hex(payload)
        for uuid, payload in advertisement.service_data.items()
    }
    return {
        "address": str(device.address),
        "name": device.name,
        "local_name": advertisement.local_name,
        "rssi_dbm": int(advertisement.rssi),
        "tx_power_dbm": advertisement.tx_power,
        "service_uuids": [str(uuid).lower()
                          for uuid in advertisement.service_uuids],
        "manufacturer_data": manufacturer_data,
        "service_data": service_data,
    }


def serialize_services(services: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for service in services:
        service_uuid = str(service.uuid).lower()
        service_entry: dict[str, Any] = {
            "uuid": service_uuid,
            "label": N6_UUID_LABELS.get(service_uuid),
            "description": service.description,
            "handle": service.handle,
            "characteristics": [],
        }
        for characteristic in service.characteristics:
            characteristic_uuid = str(characteristic.uuid).lower()
            characteristic_entry = {
                "uuid": characteristic_uuid,
                "label": N6_UUID_LABELS.get(characteristic_uuid),
                "description": characteristic.description,
                "handle": characteristic.handle,
                "properties": sorted(str(item)
                                     for item in characteristic.properties),
                "descriptors": [
                    {
                        "uuid": str(descriptor.uuid).lower(),
                        "description": descriptor.description,
                        "handle": descriptor.handle,
                    }
                    for descriptor in characteristic.descriptors
                ],
            }
            service_entry["characteristics"].append(characteristic_entry)
        result.append(service_entry)
    return result


def evaluate_n6_gatt(services: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compare a serialized GATT tree with the discovery-stage N6 contract."""

    observed_services = {service["uuid"] for service in services}
    observed_characteristics = {
        characteristic["uuid"]: set(characteristic["properties"])
        for service in services
        for characteristic in service["characteristics"]
    }
    required_services = {
        "7a1e0001-b5a3-f393-e0a9-e50e24dcca9e",
        "7a1e0101-b5a3-f393-e0a9-e50e24dcca9e",
    }
    missing_uuids = sorted(
        (required_services - observed_services)
        | (set(N6_REQUIRED_PROPERTIES) - set(observed_characteristics))
    )
    property_mismatches = []
    for uuid, required in N6_REQUIRED_PROPERTIES.items():
        observed = observed_characteristics.get(uuid)
        if observed is not None and not required.issubset(observed):
            property_mismatches.append({
                "uuid": uuid,
                "required": sorted(required),
                "observed": sorted(observed),
            })
    detected = bool(required_services & observed_services)
    return {
        "detected": detected,
        "passed": not missing_uuids and not property_mismatches,
        "missing_uuids": missing_uuids,
        "property_mismatches": property_mismatches,
    }


def resolve_device(records: Sequence["ScanRecord"], selector: str) -> "ScanRecord":
    """Resolve a one-based scan index, exact BLE address, or unique N6."""

    if selector.casefold() == "n6":
        matches = [
            record for record in records
            if str(record.advertisement.local_name or record.device.name or "")
            .startswith("N6-MAINT-")
            or "7a1e0001-b5a3-f393-e0a9-e50e24dcca9e" in {
                str(uuid).lower() for uuid in record.advertisement.service_uuids
            }
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one N6 advertiser, found {len(matches)}")
        return matches[0]

    try:
        index = int(selector, 10)
    except ValueError:
        index = 0
    if index != 0:
        if index < 1 or index > len(records):
            raise ValueError(f"device index must be between 1 and {len(records)}")
        return records[index - 1]

    selector_key = selector.casefold()
    for record in records:
        if str(record.device.address).casefold() == selector_key:
            return record
    raise ValueError("device was not found in the latest scan")


@dataclass(frozen=True)
class ScanRecord:
    device: Any
    advertisement: Any


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Return a linearly interpolated percentile for deterministic reports."""

    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    rank = (len(ordered) - 1) * (percent / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


class LatencyProbeCollector:
    """Collect CLI PONG lines and retain the raw notification evidence."""

    def __init__(self, started_at: float) -> None:
        self.started_at = started_at
        self.line_buffer = ""
        self.transcript = ""
        self.samples: list[dict[str, Any]] = []
        self.samples_by_token: dict[str, list[dict[str, Any]]] = {}
        self.raw_notifications: list[dict[str, Any]] = []
        self.duplicate_replies = 0
        self.unknown_replies: list[dict[str, Any]] = []
        self.radio_metrics: dict[str, int] = {}

    def add_ping(self, sequence: int, token: str, scheduled_at: float,
                 sent_at: float) -> dict[str, Any]:
        sample: dict[str, Any] = {
            "sequence": sequence,
            "token": token,
            "scheduled_ms": round(
                (scheduled_at - self.started_at) * 1000.0, 3),
            "sent_ms": round((sent_at - self.started_at) * 1000.0, 3),
            "send_lag_ms": round((sent_at - scheduled_at) * 1000.0, 3),
            "reply_ms": None,
            "latency_ms": None,
            "device_tick": None,
            "write_error": None,
        }
        self.samples.append(sample)
        self.samples_by_token.setdefault(token, []).append(sample)
        return sample

    def on_notification(self, _characteristic: Any, data: bytearray) -> None:
        received_at = time.monotonic()
        payload = bytes(data)
        text = payload.decode("utf-8", errors="replace")
        self.raw_notifications.append({
            "received_ms": round(
                (received_at - self.started_at) * 1000.0, 3),
            "hex": bytes_to_hex(payload),
        })
        self.transcript += text
        self.line_buffer += text
        while "\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\n", 1)
            self._process_line(line.rstrip("\r"), received_at)

    def _process_line(self, line: str, received_at: float) -> None:
        for match in PONG_PATTERN.finditer(line):
            token = match.group(1)
            device_tick = int(match.group(2), 10)
            token_samples = self.samples_by_token.get(token, [])
            sample = next(
                (candidate for candidate in reversed(token_samples)
                 if candidate["reply_ms"] is None),
                None)
            if sample is None and not token_samples:
                self.unknown_replies.append({
                    "token": token,
                    "device_tick": device_tick,
                    "received_ms": round(
                        (received_at - self.started_at) * 1000.0, 3),
                })
            elif sample is None:
                self.duplicate_replies += 1
            else:
                sample["reply_ms"] = round(
                    (received_at - self.started_at) * 1000.0, 3)
                sample["latency_ms"] = round(
                    (received_at - (self.started_at
                                    + (sample["sent_ms"] / 1000.0)))
                    * 1000.0, 3)
                sample["device_tick"] = device_tick

        match = RADIO_LOOP_PATTERN.search(line)
        if match is not None:
            self.radio_metrics.update({
                "loop_count": int(match.group(1), 10),
                "last_loop_tick": int(match.group(2), 10),
                "max_loop_gap_ticks": int(match.group(3), 10),
            })
        match = BLE_TX_PUMP_PATTERN.search(line)
        if match is not None:
            self.radio_metrics.update({
                "last_ble_tx_tick": int(match.group(1), 10),
                "max_ble_tx_gap_ticks": int(match.group(2), 10),
            })

    def build_result(self, scenario: str, duration_seconds: float,
                     disconnects: int, reconnects: int,
                     trigger: dict[str, Any] | None) -> dict[str, Any]:
        latencies = [
            float(sample["latency_ms"])
            for sample in self.samples
            if sample["latency_ms"] is not None
        ]
        missing = [
            sample["token"] for sample in self.samples
            if sample["reply_ms"] is None
        ]
        statistics = {
            "minimum_ms": round(min(latencies), 3) if latencies else None,
            "p50_ms": (round(percentile(latencies, 50.0), 3)
                       if latencies else None),
            "p95_ms": (round(percentile(latencies, 95.0), 3)
                       if latencies else None),
            "maximum_ms": round(max(latencies), 3) if latencies else None,
        }
        passed = (
            not missing
            and statistics["p95_ms"] is not None
            and float(statistics["p95_ms"]) <= LATENCY_LIMIT_MS
        )
        return {
            "scenario": scenario,
            "passed": passed,
            "duration_seconds": duration_seconds,
            "ping_interval_ms": int(LATENCY_PING_INTERVAL_SECONDS * 1000),
            "latency_limit_ms": LATENCY_LIMIT_MS,
            "pings_sent": len(self.samples),
            "replies_received": len(latencies),
            "missing_replies": len(missing),
            "missing_tokens": missing,
            "disconnects": disconnects,
            "reconnects": reconnects,
            "duplicate_replies": self.duplicate_replies,
            "unknown_replies": self.unknown_replies,
            "statistics": statistics,
            "radio_metrics": self.radio_metrics,
            "wifi_trigger": trigger,
            "samples": self.samples,
            "raw_notifications": self.raw_notifications,
            "raw_cli_transcript": self.transcript + self.line_buffer,
        }


class TofFrameAssembler:
    """Reassemble one atomic N6 ToF frame from ordered BLE notifications."""

    def __init__(self) -> None:
        self.pending: dict[str, Any] | None = None
        self.completed = 0
        self.dropped = 0
        self.crc_errors = 0

    def reset(self, count_drop: bool = False) -> None:
        if count_drop and self.pending is not None:
            self.dropped += 1
        self.pending = None

    def push(self, notification: bytes | bytearray) -> dict[str, Any] | None:
        if len(notification) <= TOF_IMAGE_HEADER_SIZE:
            self.reset(count_drop=True)
            return None

        (magic, version, flags, frame_id, offset, total, width, height,
         channel, pixel_format, expected_crc) = struct.unpack_from(
             "<HBBIHHBBBBI", notification)
        fragment = bytes(notification[TOF_IMAGE_HEADER_SIZE:])
        valid_header = (
            magic == TOF_IMAGE_MAGIC
            and version == TOF_IMAGE_VERSION
            and pixel_format == TOF_IMAGE_FLOAT32_LE
            and width > 0 and height > 0
            and total == width * height * 4
            and total <= TOF_IMAGE_MAX_PAYLOAD
            and offset + len(fragment) <= total
        )
        if not valid_header:
            self.reset(count_drop=True)
            return None

        if flags & TOF_IMAGE_FLAG_START:
            self.reset(count_drop=True)
            if offset != 0:
                return None
            self.pending = {
                "frame_id": frame_id,
                "total": total,
                "width": width,
                "height": height,
                "channel": channel,
                "pixel_format": pixel_format,
                "crc32": expected_crc,
                "payload": bytearray(),
            }

        pending = self.pending
        if pending is None or any((
            pending["frame_id"] != frame_id,
            pending["total"] != total,
            pending["width"] != width,
            pending["height"] != height,
            pending["channel"] != channel,
            pending["pixel_format"] != pixel_format,
            pending["crc32"] != expected_crc,
            len(pending["payload"]) != offset,
        )):
            self.reset(count_drop=True)
            return None

        pending["payload"].extend(fragment)
        if not (flags & TOF_IMAGE_FLAG_END):
            return None
        if len(pending["payload"]) != total:
            self.reset(count_drop=True)
            return None
        actual_crc = zlib.crc32(pending["payload"]) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            self.crc_errors += 1
            self.reset()
            return None

        result = {key: value for key, value in pending.items()
                  if key != "payload"}
        self.completed += 1
        self.reset()
        return result


class BleInspector:
    def __init__(self, report_path: Path, scan_timeout: float,
                 connect_timeout: float, pair: bool = False,
                 uncached_services: bool = False) -> None:
        self.report_path = report_path
        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout
        self.pair = pair
        self.uncached_services = uncached_services
        self.records: list[ScanRecord] = []
        self.client: Any | None = None
        self.connected_record: ScanRecord | None = None
        self.subscriptions: set[str] = set()
        self.notifications: dict[str, list[Any]] = {
            "cli": [], "debug": [], "tof": []
        }
        self.tof_assembler = TofFrameAssembler()
        self.disconnect_count = 0
        self.connect_count = 0

    def write_report(self, command: str, ok: bool, **payload: Any) -> None:
        report = {
            "timestamp_utc": utc_timestamp(),
            "command": command,
            "ok": ok,
            **payload,
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix(
            self.report_path.suffix + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True),
                             encoding="utf-8")
        last_error: PermissionError | None = None
        for attempt in range(40):
            try:
                os.replace(temporary, self.report_path)
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

    def on_disconnect(self, _client: Any) -> None:
        self.disconnect_count += 1
        address = (str(self.connected_record.device.address)
                   if self.connected_record is not None else None)
        self.client = None
        self.connected_record = None
        self.subscriptions.clear()
        print(f"\n[BLE] disconnected from {address or 'unknown peer'}")

    async def scan(self, timeout: float) -> None:
        if self.client is not None and self.client.is_connected:
            raise RuntimeError("disconnect before scanning; adapter concurrency varies")

        from bleak import BleakScanner

        print(f"Scanning for {timeout:.1f} seconds...")
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
        records = [ScanRecord(device, advertisement)
                   for device, advertisement in discovered.values()]
        records.sort(key=lambda item: item.advertisement.rssi, reverse=True)
        self.records = records
        devices = [serialize_advertisement(item.device, item.advertisement)
                   for item in records]
        self.print_devices(devices)
        self.write_report("scan", True, duration_seconds=timeout, devices=devices)
        print(f"Saved {len(devices)} scan result(s) to {self.report_path}")

    @staticmethod
    def print_devices(devices: Sequence[dict[str, Any]]) -> None:
        if not devices:
            print("No BLE devices found.")
            return
        print(" #  RSSI  Address/identifier                         Name")
        for index, device in enumerate(devices, start=1):
            name = device["local_name"] or device["name"] or "<unnamed>"
            is_n6 = (str(name).startswith("N6-MAINT-") or
                     "7a1e0001-b5a3-f393-e0a9-e50e24dcca9e"
                     in device["service_uuids"])
            marker = "  [N6]" if is_n6 else ""
            print(f"{index:2d}  {device['rssi_dbm']:4d}  "
                  f"{device['address']:<42} {name}{marker}")

    def show_devices(self) -> None:
        devices = [serialize_advertisement(item.device, item.advertisement)
                   for item in self.records]
        self.print_devices(devices)
        self.write_report("devices", True, devices=devices)

    async def connect(self, selector: str) -> None:
        if self.client is not None and self.client.is_connected:
            raise RuntimeError("already connected; disconnect first")
        if not self.records:
            raise RuntimeError("run 'scan' before 'connect'")

        from bleak import BleakClient

        record = resolve_device(self.records, selector)
        name = (record.advertisement.local_name or record.device.name
                or "<unnamed>")
        print(f"Connecting to {name} ({record.device.address})...")
        # The address-type-neutral WinRT overload can fail with E_FAIL for an
        # otherwise connectable peripheral. Try it first, then the two explicit
        # address types. This remains bounded and is harmless on a failed link:
        # no GATT write is issued until one attempt is fully connected.
        cache_options = ({"use_cached_services": False}
                         if self.uncached_services else {})
        attempts = (
            ("automatic", {"winrt": dict(cache_options)}),
            ("public", {"winrt": {
                **cache_options, "address_type": "public"}}),
            ("random", {"winrt": {
                **cache_options, "address_type": "random"}}),
        )
        last_error: Exception | None = None
        for address_type, backend_options in attempts:
            client = BleakClient(
                record.device,
                disconnected_callback=self.on_disconnect,
                timeout=self.connect_timeout,
                pair=self.pair,
                **backend_options,
            )
            self.client = client
            self.connected_record = record
            try:
                await client.connect()
                if not client.is_connected:
                    raise RuntimeError(
                        "BLE backend returned without an active connection")
                self.connect_count += 1
                break
            except Exception as error:
                last_error = error
                if client.is_connected:
                    await client.disconnect()
                if self.client is client:
                    self.client = None
                    self.connected_record = None
                print(f"  {address_type} address attempt failed: {error}")
        else:
            assert last_error is not None
            raise last_error
        result = self.connection_status()
        self.write_report("connect", True, connection=result)
        print(f"Connected: {result['address']} (MTU {result['mtu']})")

    def connection_status(self) -> dict[str, Any]:
        connected = self.client is not None and bool(self.client.is_connected)
        return {
            "connected": connected,
            "address": (str(self.connected_record.device.address)
                        if self.connected_record is not None else None),
            "name": ((self.connected_record.advertisement.local_name
                      or self.connected_record.device.name)
                     if self.connected_record is not None else None),
            "mtu": int(self.client.mtu_size) if connected else None,
        }

    def show_status(self) -> None:
        status = self.connection_status()
        print(json.dumps(status, indent=2))
        self.write_report("status", True, connection=status)

    def show_services(self) -> None:
        if self.client is None or not self.client.is_connected:
            raise RuntimeError("connect before requesting services")
        services = serialize_services(self.client.services)
        n6_contract = evaluate_n6_gatt(services)
        for service in services:
            label = f" [{service['label']}]" if service["label"] else ""
            print(f"SERVICE {service['uuid']}{label} ({service['description']})")
            for characteristic in service["characteristics"]:
                char_label = (f" [{characteristic['label']}]"
                              if characteristic["label"] else "")
                properties = ", ".join(characteristic["properties"])
                print(f"  CHAR {characteristic['uuid']}{char_label}")
                print(f"       properties: {properties or '<none>'}; "
                      f"handle: {characteristic['handle']}")
                for descriptor in characteristic["descriptors"]:
                    print(f"    DESC {descriptor['uuid']} "
                          f"handle: {descriptor['handle']}")
        print("N6 GATT contract: "
              + ("PASS" if n6_contract["passed"] else "NOT MATCHED"))
        self.write_report("services", True,
                          connection=self.connection_status(),
                          services=services,
                          n6_gatt_contract=n6_contract)
        print(f"Saved {len(services)} service(s) to {self.report_path}")

    def require_connection(self) -> Any:
        if self.client is None or not self.client.is_connected:
            raise RuntimeError("connect before accessing a characteristic")
        return self.client

    @staticmethod
    def resolve_stream(name: str) -> str:
        stream = name.casefold()
        if stream not in N6_STREAM_UUIDS:
            raise ValueError("stream must be 'cli', 'debug', or 'tof'")
        return stream

    async def write_stream(self, stream_name: str, payload: bytes) -> None:
        client = self.require_connection()
        stream = self.resolve_stream(stream_name)
        if not payload:
            raise ValueError("payload must not be empty")
        if "rx" not in N6_STREAM_UUIDS[stream]:
            raise ValueError(f"{stream.upper()} is a notification-only stream")
        await client.write_gatt_char(N6_STREAM_UUIDS[stream]["rx"], payload,
                                     response=True)
        result = {
            "stream": stream,
            "length": len(payload),
            "hex": bytes_to_hex(payload),
            "connection": self.connection_status(),
        }
        self.write_report("write", True, write=result)
        print(f"Wrote {len(payload)} byte(s) to {stream.upper()} RX.")

    async def subscribe(self, stream_name: str) -> None:
        client = self.require_connection()
        stream = self.resolve_stream(stream_name)
        if stream in self.subscriptions:
            print(f"Already subscribed to {stream.upper()} TX.")
            return

        def notification_handler(_characteristic: Any, data: bytearray) -> None:
            if stream == "tof":
                frame = self.tof_assembler.push(data)
                if frame is not None:
                    self.notifications[stream].append(frame)
                    print("\n[TOF TX] complete CRC-valid frame: "
                          f"id={frame['frame_id']} "
                          f"{frame['width']}x{frame['height']} "
                          f"channel={frame['channel']} "
                          f"bytes={frame['total']}")
                return
            encoded = bytes_to_hex(data)
            self.notifications[stream].append(encoded)
            print(f"\n[{stream.upper()} TX] {len(data)} byte(s): {encoded}")

        await client.start_notify(N6_STREAM_UUIDS[stream]["tx"],
                                  notification_handler)
        self.subscriptions.add(stream)
        self.write_report("subscribe", True, stream=stream,
                          connection=self.connection_status())
        print(f"Subscribed to {stream.upper()} TX notifications.")

    async def unsubscribe(self, stream_name: str) -> None:
        client = self.require_connection()
        stream = self.resolve_stream(stream_name)
        if stream not in self.subscriptions:
            print(f"Not subscribed to {stream.upper()} TX.")
            return
        await client.stop_notify(N6_STREAM_UUIDS[stream]["tx"])
        self.subscriptions.remove(stream)
        self.write_report("unsubscribe", True, stream=stream,
                          connection=self.connection_status())
        print(f"Unsubscribed from {stream.upper()} TX notifications.")

    def show_notifications(self) -> None:
        result = {stream: list(values)
                  for stream, values in self.notifications.items()}
        result["tof_stats"] = {
            "completed": self.tof_assembler.completed,
            "dropped": self.tof_assembler.dropped,
            "crc_errors": self.tof_assembler.crc_errors,
        }
        print(json.dumps(result, indent=2))
        self.write_report("notifications", True, notifications=result,
                          connection=self.connection_status())

    async def disconnect(self) -> None:
        client = self.client
        address = (str(self.connected_record.device.address)
                   if self.connected_record is not None else None)
        if client is None or not client.is_connected:
            self.client = None
            self.connected_record = None
            print("Not connected.")
            self.write_report("disconnect", True, address=address,
                              already_disconnected=True)
            return
        await client.disconnect()
        self.client = None
        self.connected_record = None
        self.write_report("disconnect", True, address=address)
        print(f"Disconnected from {address}.")

    async def soak_tof(self, selector: str, cycles: int,
                       frame_timeout: float) -> None:
        """Repeat connect/subscribe/frame/unsubscribe/disconnect validation."""

        if cycles <= 0 or cycles > 100:
            raise ValueError("cycles must be in the range 1..100")
        if frame_timeout <= 0.0:
            raise ValueError("frame timeout must be positive")
        if self.client is not None and self.client.is_connected:
            await self.disconnect()
        if not self.records:
            await self.scan(self.scan_timeout)

        results: list[dict[str, Any]] = []
        print(f"Starting ToF BLE soak: {cycles} cycle(s), "
              f"{frame_timeout:.1f}s frame timeout")
        for cycle in range(1, cycles + 1):
            cycle_started = time.monotonic()
            result: dict[str, Any] = {"cycle": cycle, "passed": False}
            print(f"\n--- soak cycle {cycle}/{cycles} ---")
            try:
                connect_started = time.monotonic()
                await self.connect(selector)
                result["connect_seconds"] = round(
                    time.monotonic() - connect_started, 3)
                result["mtu"] = self.connection_status()["mtu"]

                services = serialize_services(self.require_connection().services)
                contract = evaluate_n6_gatt(services)
                result["n6_gatt_contract"] = contract
                if not contract["passed"]:
                    raise RuntimeError("N6 GATT contract did not pass")

                before_completed = self.tof_assembler.completed
                before_dropped = self.tof_assembler.dropped
                before_crc_errors = self.tof_assembler.crc_errors
                await self.subscribe("tof")
                frame_started = time.monotonic()
                deadline = frame_started + frame_timeout
                while self.tof_assembler.completed == before_completed:
                    if (self.client is None
                            or not self.client.is_connected):
                        raise RuntimeError(
                            "BLE disconnected while waiting for a ToF frame")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "timed out waiting for a complete ToF frame")
                    await asyncio.sleep(0.05)
                result["first_frame_seconds"] = round(
                    time.monotonic() - frame_started, 3)
                result["frames_while_enabled"] = (
                    self.tof_assembler.completed - before_completed)
                result["drops_while_enabled"] = (
                    self.tof_assembler.dropped - before_dropped)
                result["crc_errors_while_enabled"] = (
                    self.tof_assembler.crc_errors - before_crc_errors)
                if result["crc_errors_while_enabled"] != 0:
                    raise RuntimeError("ToF CRC error observed")

                await self.unsubscribe("tof")
                # An intentionally cancelled partial frame must not contaminate
                # the next connection, and must not be counted as a radio drop.
                self.tof_assembler.reset()
                stopped_at = self.tof_assembler.completed
                await asyncio.sleep(1.0)
                result["frames_after_unsubscribe"] = (
                    self.tof_assembler.completed - stopped_at)
                if result["frames_after_unsubscribe"] != 0:
                    raise RuntimeError(
                        "ToF notifications continued after unsubscribe")

                await self.disconnect()
                await asyncio.sleep(0.4)
                if self.connection_status()["connected"]:
                    raise RuntimeError("BLE remained connected after disconnect")
                result["passed"] = True
            except Exception as exc:
                result["error_type"] = type(exc).__name__
                result["error"] = str(exc)
                print(f"Cycle {cycle} FAILED: {type(exc).__name__}: {exc}")
                try:
                    if (self.client is not None
                            and self.client.is_connected
                            and "tof" in self.subscriptions):
                        await self.unsubscribe("tof")
                except Exception as cleanup_exc:
                    result["unsubscribe_cleanup_error"] = str(cleanup_exc)
                try:
                    if self.client is not None:
                        await self.disconnect()
                except Exception as cleanup_exc:
                    result["disconnect_cleanup_error"] = str(cleanup_exc)
                await asyncio.sleep(0.4)
            result["cycle_seconds"] = round(
                time.monotonic() - cycle_started, 3)
            results.append(result)
            print(f"Cycle {cycle}: "
                  + ("PASS" if result["passed"] else "FAIL"))

        passed_cycles = sum(bool(item["passed"]) for item in results)
        report = {
            "passed": passed_cycles == cycles,
            "cycles_requested": cycles,
            "cycles_passed": passed_cycles,
            "cycles_failed": cycles - passed_cycles,
            "frame_timeout_seconds": frame_timeout,
            "results": results,
        }
        self.write_report("soak-tof", report["passed"], soak=report)
        print("\nToF BLE soak: "
              f"{passed_cycles}/{cycles} cycles passed; "
              f"report saved to {self.report_path}")

    async def _run_latency_probe(self, selector: str, duration_seconds: float,
                                 reply_grace_seconds: float,
                                 invalid_wifi: tuple[str, str] | None
                                 ) -> dict[str, Any]:
        if duration_seconds <= 0.0 or reply_grace_seconds < 0.0:
            raise ValueError("probe duration must be positive and grace nonnegative")
        if invalid_wifi is not None and duration_seconds <= WIFI_TRIGGER_AFTER_SECONDS:
            raise ValueError("Wi-Fi probe duration must exceed the trigger delay")
        if self.client is not None and self.client.is_connected:
            raise RuntimeError("start a noninteractive probe without an existing connection")
        if not self.records:
            await self.scan(self.scan_timeout)

        scenario = "wifi-blocking" if invalid_wifi is not None else "idle"
        started_at = time.monotonic()
        collector = LatencyProbeCollector(started_at)
        connects_before = self.connect_count
        disconnects_before = self.disconnect_count
        trigger_result: dict[str, Any] | None = None
        report: dict[str, Any] | None = None

        try:
            await self.connect(selector)
            client = self.require_connection()
            services = serialize_services(client.services)
            contract = evaluate_n6_gatt(services)
            if not contract["passed"]:
                raise RuntimeError("N6 GATT contract did not pass")
            await client.start_notify(N6_STREAM_UUIDS["cli"]["tx"],
                                      collector.on_notification)
            self.subscriptions.add("cli")
            loop = asyncio.get_running_loop()
            startup_prompt_requested = False
            unsolicited_prompt_deadline = loop.time() + 5.0
            startup_deadline = loop.time() + 15.0
            while "n6> " not in (collector.transcript +
                                  collector.line_buffer):
                if (not startup_prompt_requested
                        and loop.time() >= unsolicited_prompt_deadline):
                    # The connection banner is intentionally much larger than
                    # the bounded BLE CLI TX queue. If its final four-byte
                    # prompt is the one record rejected at startup, request a
                    # fresh empty-command prompt after the banner has drained.
                    # This remains a real end-to-end RX/TX prompt check and is
                    # bounded; it does not retry probe pings or hide a missing
                    # latency reply.
                    await client.write_gatt_char(
                        N6_STREAM_UUIDS["cli"]["rx"], b"\r", response=True)
                    startup_prompt_requested = True
                if loop.time() >= startup_deadline:
                    raise RuntimeError(
                        "BLE CLI did not publish its initial prompt")
                await asyncio.sleep(0.05)

            if not startup_prompt_requested:
                # A newly reset session first shows the banner/menu prompt but
                # remains in menu mode until Enter. Mirror the interactive
                # client contract and require the resulting console prompt
                # before measuring the first command.
                console_prompt_offset = len(
                    collector.transcript + collector.line_buffer)
                await client.write_gatt_char(
                    N6_STREAM_UUIDS["cli"]["rx"], b"\r", response=True)
                console_prompt_deadline = loop.time() + 2.0
                while "n6> " not in (
                        collector.transcript + collector.line_buffer
                        )[console_prompt_offset:]:
                    if loop.time() >= console_prompt_deadline:
                        raise RuntimeError(
                            "BLE CLI did not enter console mode")
                    await asyncio.sleep(0.02)

            measurement_started = loop.time()
            measurement_ends = measurement_started + duration_seconds
            next_ping = measurement_started
            sequence = 0
            trigger_sent = False

            print(f"Starting {scenario} latency probe for "
                  f"{duration_seconds:.1f}s at 200 ms intervals...")
            while loop.time() < measurement_ends:
                now = loop.time()
                if now < next_ping:
                    await asyncio.sleep(next_ping - now)
                    now = loop.time()

                trigger_due = (
                    invalid_wifi is not None
                    and not trigger_sent
                    and (now - measurement_started)
                    >= WIFI_TRIGGER_AFTER_SECONDS)
                latest_ping_in_flight = bool(
                    collector.samples
                    and collector.samples[-1]["reply_ms"] is None)
                if trigger_due and latest_ping_in_flight:
                    # Keep the long connect+password write out of the NCP raw
                    # GATT event window that is still delivering the previous
                    # ping. A successful run must resolve that ping before the
                    # Wi-Fi trigger; a lost ping remains visible and fails.
                    next_ping = loop.time() + 0.05
                    continue
                if trigger_due:
                    ssid, password = invalid_wifi
                    payload = (f'wifi connect "{ssid}"\r{password}\r'
                               .encode("utf-8"))
                    trigger_transcript_offset = len(
                        collector.transcript + collector.line_buffer)
                    trigger_started = loop.time()
                    await self.require_connection().write_gatt_char(
                        N6_STREAM_UUIDS["cli"]["rx"], payload, response=True)
                    trigger_result = {
                        "ssid": ssid,
                        "sent_ms": round(
                            (trigger_started - started_at) * 1000.0, 3),
                        "write_completed_ms": round(
                            (loop.time() - started_at) * 1000.0, 3),
                    }
                    trigger_sent = True
                    print(f"Triggered invalid Wi-Fi connection to {ssid!r}.")
                    # The submission-only contract includes an immediate
                    # acceptance reply and prompt. Observe both before issuing
                    # a subsequent command so the probe never feeds the CLI in
                    # the middle of its command-to-secret parser transition.
                    trigger_reply_deadline = loop.time() + 2.0
                    while True:
                        trigger_reply = (
                            collector.transcript + collector.line_buffer
                        )[trigger_transcript_offset:]
                        if ("Wi-Fi connect request accepted:" in trigger_reply
                                and "n6> " in trigger_reply):
                            break
                        if loop.time() >= trigger_reply_deadline:
                            raise RuntimeError(
                                "Wi-Fi submit did not publish acceptance and prompt")
                        await asyncio.sleep(0.02)
                    next_ping = loop.time() + LATENCY_PING_INTERVAL_SECONDS
                    continue

                if loop.time() >= measurement_ends:
                    break
                if latest_ping_in_flight:
                    # The NCP exposes GATT writes through one raw unsolicited
                    # AT-event window. Do not overlap timely replies. After a
                    # bounded silence, continue with a new numbered command
                    # so the report reveals whether RX recovers. The original
                    # missing sample is retained and still fails the run.
                    last_sent = collector.samples[-1]["sent_ms"] / 1000.0
                    if (loop.time() - collector.started_at - last_sent
                            >= LATENCY_STALLED_REPLY_SECONDS):
                        latest_ping_in_flight = False
                    else:
                        next_ping += LATENCY_PING_INTERVAL_SECONDS
                        continue
                sequence += 1
                # Keep both directions within the smallest reliable BLE CLI
                # record. A single hex digit makes the command exactly 13
                # bytes. Tokens wrap, so the collector keeps an ordered list
                # per token and assigns a PONG to its first unresolved send.
                token = f"{sequence & 0xF:X}"
                sent_at = loop.time()
                sample = collector.add_ping(sequence, token, next_ping,
                                            sent_at)
                try:
                    await self.require_connection().write_gatt_char(
                        N6_STREAM_UUIDS["cli"]["rx"],
                        f"debug ping {token}\r".encode("ascii"),
                        response=True)
                except Exception as exc:
                    sample["write_error"] = f"{type(exc).__name__}: {exc}"
                next_ping += LATENCY_PING_INTERVAL_SECONDS
                if next_ping < loop.time():
                    next_ping = loop.time() + LATENCY_PING_INTERVAL_SECONDS

            if self.client is not None and self.client.is_connected:
                try:
                    await self.client.write_gatt_char(
                        N6_STREAM_UUIDS["cli"]["rx"], b"radio status\r",
                        response=True)
                except Exception as exc:
                    print(f"Unable to request final radio status: {exc}")
            if reply_grace_seconds != 0.0:
                await asyncio.sleep(reply_grace_seconds)

            report = collector.build_result(
                scenario, duration_seconds,
                self.disconnect_count - disconnects_before,
                max(0, self.connect_count - connects_before - 1),
                trigger_result)
            report["startup_prompt_requested"] = startup_prompt_requested
            report["n6_gatt_contract"] = contract
            self.write_report(f"{scenario}-latency-probe", report["passed"],
                              latency_probe=report)
            stats = report["statistics"]
            print(f"Latency probe {scenario}: replies "
                  f"{report['replies_received']}/{report['pings_sent']}, "
                  f"missing={report['missing_replies']}, "
                  f"p50={stats['p50_ms']} ms, p95={stats['p95_ms']} ms, "
                  f"max={stats['maximum_ms']} ms, "
                  f"reconnects={report['reconnects']}")
            print("PASS" if report["passed"] else "FAIL")
            print(f"Raw report saved to {self.report_path}")
            return report
        except Exception as exc:
            self.write_report(
                f"{scenario}-latency-probe", False,
                error_type=type(exc).__name__, error=str(exc),
                latency_probe=(collector.build_result(
                    scenario, duration_seconds,
                    self.disconnect_count - disconnects_before,
                    max(0, self.connect_count - connects_before - 1),
                    trigger_result)))
            raise
        finally:
            cleanup_client = self.client
            if cleanup_client is not None and cleanup_client.is_connected:
                if "cli" in self.subscriptions:
                    try:
                        await cleanup_client.stop_notify(
                            N6_STREAM_UUIDS["cli"]["tx"])
                    except Exception as exc:
                        print(f"CLI unsubscribe cleanup failed: {exc}")
                    self.subscriptions.discard("cli")
                if cleanup_client.is_connected:
                    await cleanup_client.disconnect()

    async def run_latency_probe(self, selector: str,
                                duration_seconds: float,
                                reply_grace_seconds: float
                                ) -> dict[str, Any]:
        """Measure idle BLE CLI ping latency and save every raw observation."""

        return await self._run_latency_probe(
            selector, duration_seconds, reply_grace_seconds, None)

    async def run_wifi_blocking_probe(self, selector: str,
                                      duration_seconds: float,
                                      reply_grace_seconds: float,
                                      invalid_ssid: str,
                                      invalid_password: str
                                      ) -> dict[str, Any]:
        """Measure pings while the current synchronous Wi-Fi path is blocked."""

        if (not invalid_ssid or len(invalid_ssid) > 32
                or any(character in invalid_ssid
                       for character in ('"', "\r", "\n"))):
            raise ValueError(
                "invalid SSID must be 1..32 characters without quote/newline")
        if (len(invalid_password) > 63
                or any(character in invalid_password
                       for character in ("\r", "\n"))):
            raise ValueError(
                "invalid password must be at most 63 characters without newline")
        return await self._run_latency_probe(
            selector, duration_seconds, reply_grace_seconds,
            (invalid_ssid, invalid_password))

    async def run_command(self, line: str) -> bool:
        arguments = parse_command(line)
        if not arguments:
            return True
        command = arguments[0].casefold()
        if command in {"quit", "exit"}:
            return False
        if command in {"help", "?"}:
            print_help()
        elif command == "scan":
            timeout = float(arguments[1]) if len(arguments) == 2 else self.scan_timeout
            if len(arguments) > 2 or timeout <= 0.0:
                raise ValueError("usage: scan [positive-seconds]")
            await self.scan(timeout)
        elif command == "devices" and len(arguments) == 1:
            self.show_devices()
        elif command == "connect" and len(arguments) == 2:
            await self.connect(arguments[1])
        elif command == "status" and len(arguments) == 1:
            self.show_status()
        elif command == "services" and len(arguments) == 1:
            self.show_services()
        elif command == "write-text" and len(arguments) >= 3:
            await self.write_stream(arguments[1],
                                    " ".join(arguments[2:]).encode("utf-8"))
        elif command == "write-hex" and len(arguments) == 3:
            try:
                payload = bytes.fromhex(arguments[2])
            except ValueError as exc:
                raise ValueError("hex payload is invalid") from exc
            await self.write_stream(arguments[1], payload)
        elif command == "subscribe" and len(arguments) == 2:
            await self.subscribe(arguments[1])
        elif command == "unsubscribe" and len(arguments) == 2:
            await self.unsubscribe(arguments[1])
        elif command == "notifications" and len(arguments) == 1:
            self.show_notifications()
        elif command == "disconnect" and len(arguments) == 1:
            await self.disconnect()
        elif command == "soak-tof" and 3 <= len(arguments) <= 4:
            timeout = float(arguments[3]) if len(arguments) == 4 else 15.0
            await self.soak_tof(arguments[1], int(arguments[2]), timeout)
        else:
            raise ValueError("unknown command or wrong arguments; enter 'help'")
        return True

    async def run(self) -> int:
        print("N6 BLE HIL inspector. Enter 'help' for commands.")
        print(f"Machine-readable result: {self.report_path}")
        try:
            while True:
                try:
                    line = await asyncio.to_thread(input, "ble> ")
                except EOFError:
                    break
                try:
                    if not await self.run_command(line):
                        break
                except (ValueError, RuntimeError) as exc:
                    print(f"ERROR: {exc}")
                    self.write_report(line.strip() or "<empty>", False,
                                      error=str(exc))
                except Exception as exc:  # Backend failures must stay visible.
                    print(f"BLE ERROR: {type(exc).__name__}: {exc}")
                    self.write_report(line.strip() or "<empty>", False,
                                      error_type=type(exc).__name__,
                                      error=str(exc))
        finally:
            if self.client is not None and self.client.is_connected:
                await self.client.disconnect()
        return 0


def print_help() -> None:
    print("""Commands:
  scan [seconds]           scan all nearby BLE advertisers
  devices                 print the most recent scan again
  connect <index|address|n6>
                          connect using a result or the unique N6 advertiser
  status                  report the current connection and negotiated MTU
  services                list every service, characteristic, property, and descriptor
  write-text <stream> <text...>
                          write UTF-8 to CLI or DEBUG RX with ATT response
  write-hex <stream> <hex>
                          write exact bytes to CLI or DEBUG RX with ATT response
  subscribe <stream>      enable CLI, DEBUG, or ToF TX notifications
  unsubscribe <stream>    disable CLI, DEBUG, or ToF TX notifications
  notifications           show text fragments and completed CRC-valid ToF frames
  disconnect              close the active BLE connection
  soak-tof <device> <cycles> [frame-timeout]
                          repeatedly connect, validate GATT, enable/disable ToF,
                          require a CRC-valid frame, and disconnect
  quit                     disconnect and exit
""")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive BLE scanner and GATT inspector for N6 HIL")
    parser.add_argument("--scan-timeout", type=float, default=6.0,
                        help="default scan duration in seconds (default: 6)")
    parser.add_argument("--connect-timeout", type=float, default=20.0,
                        help="connection timeout in seconds (default: 20)")
    parser.add_argument("--pair", action="store_true",
                        help="request Just Works pairing while connecting")
    parser.add_argument(
        "--uncached-services", action="store_true",
        help="force Windows to read the current GATT database from the device",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help="JSON file overwritten after every command")
    parser.add_argument(
        "--probe", choices=("latency", "wifi-blocking"),
        help=("run a noninteractive 200 ms ping probe and exit nonzero on "
              "a missing reply or p95 above 250 ms"),
    )
    parser.add_argument(
        "--device", default="n6",
        help="probe target: scan index, address, or unique 'n6' (default: n6)",
    )
    parser.add_argument(
        "--probe-seconds", type=float,
        help="probe duration; defaults to 10 s idle or 45 s Wi-Fi-blocking",
    )
    parser.add_argument(
        "--reply-grace", type=float, default=DEFAULT_REPLY_GRACE_SECONDS,
        help="seconds to collect late replies after sending (default: 3)",
    )
    parser.add_argument(
        "--invalid-ssid",
        help=("known-absent SSID for --probe wifi-blocking; default is a "
              "run-specific N6-HIL-MISSING name"),
    )
    parser.add_argument(
        "--invalid-password", default="N6-invalid-HIL-password",
        help="non-secret password used only by the invalid Wi-Fi probe",
    )
    return parser


def main() -> int:
    arguments = build_argument_parser().parse_args()
    if (arguments.scan_timeout <= 0.0
            or arguments.connect_timeout <= 0.0
            or arguments.reply_grace < 0.0):
        raise SystemExit("timeouts must be positive")
    inspector = BleInspector(arguments.report.resolve(),
                             arguments.scan_timeout,
                             arguments.connect_timeout,
                             arguments.pair,
                             arguments.uncached_services)

    async def run_selected_mode() -> int:
        if arguments.probe is None:
            return await inspector.run()
        if arguments.probe == "latency":
            duration = (arguments.probe_seconds
                        if arguments.probe_seconds is not None
                        else DEFAULT_LATENCY_PROBE_SECONDS)
            result = await inspector.run_latency_probe(
                arguments.device, duration, arguments.reply_grace)
        else:
            duration = (arguments.probe_seconds
                        if arguments.probe_seconds is not None
                        else DEFAULT_WIFI_BLOCKING_PROBE_SECONDS)
            invalid_ssid = (arguments.invalid_ssid
                            or f"N6-HIL-MISSING-{os.getpid():08X}")
            result = await inspector.run_wifi_blocking_probe(
                arguments.device, duration, arguments.reply_grace,
                invalid_ssid, arguments.invalid_password)
        return 0 if result["passed"] else 1

    try:
        return asyncio.run(run_selected_mode())
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except ModuleNotFoundError as exc:
        if exc.name == "bleak":
            print("Bleak is not installed. Run: "
                  "python -m pip install -r hil_tests/requirements.txt",
                  file=sys.stderr)
            return 2
        raise
    except (ValueError, RuntimeError) as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
