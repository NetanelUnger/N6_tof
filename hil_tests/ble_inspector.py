"""Interactive BLE scan, connection, and GATT-discovery HIL utility.

The tool deliberately performs no characteristic reads, writes, or
subscriptions.  It is the non-destructive discovery layer used before the N6
BLE UART data paths are attached.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import sys
import time
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
    "7a1e0101-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG service",
    "7a1e0102-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG RX",
    "7a1e0103-b5a3-f393-e0a9-e50e24dcca9e": "N6 DEBUG TX",
}
N6_REQUIRED_PROPERTIES = {
    "7a1e0002-b5a3-f393-e0a9-e50e24dcca9e": {"write", "write-without-response"},
    "7a1e0003-b5a3-f393-e0a9-e50e24dcca9e": {"notify"},
    "7a1e0102-b5a3-f393-e0a9-e50e24dcca9e": {"write", "write-without-response"},
    "7a1e0103-b5a3-f393-e0a9-e50e24dcca9e": {"notify"},
}


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
    """Resolve a one-based scan index or an exact BLE address."""

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


class BleInspector:
    def __init__(self, report_path: Path, scan_timeout: float,
                 connect_timeout: float) -> None:
        self.report_path = report_path
        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout
        self.records: list[ScanRecord] = []
        self.client: Any | None = None
        self.connected_record: ScanRecord | None = None

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
        address = (str(self.connected_record.device.address)
                   if self.connected_record is not None else None)
        self.client = None
        self.connected_record = None
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
        client = BleakClient(record.device,
                            disconnected_callback=self.on_disconnect,
                            timeout=self.connect_timeout)
        self.client = client
        self.connected_record = record
        try:
            await client.connect()
            if not client.is_connected:
                raise RuntimeError(
                    "BLE backend returned without an active connection")
        except Exception:
            if client.is_connected:
                await client.disconnect()
            if self.client is client:
                self.client = None
                self.connected_record = None
            raise
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
        elif command == "disconnect" and len(arguments) == 1:
            await self.disconnect()
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
  connect <index|address> connect using a result from the latest scan
  status                  report the current connection and negotiated MTU
  services                list every service, characteristic, property, and descriptor
  disconnect              close the active BLE connection
  quit                     disconnect and exit
""")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive BLE scanner and GATT inspector for N6 HIL")
    parser.add_argument("--scan-timeout", type=float, default=6.0,
                        help="default scan duration in seconds (default: 6)")
    parser.add_argument("--connect-timeout", type=float, default=20.0,
                        help="connection timeout in seconds (default: 20)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help="JSON file overwritten after every command")
    return parser


def main() -> int:
    arguments = build_argument_parser().parse_args()
    if arguments.scan_timeout <= 0.0 or arguments.connect_timeout <= 0.0:
        raise SystemExit("timeouts must be positive")
    inspector = BleInspector(arguments.report.resolve(),
                             arguments.scan_timeout,
                             arguments.connect_timeout)
    try:
        return asyncio.run(inspector.run())
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


if __name__ == "__main__":
    raise SystemExit(main())
