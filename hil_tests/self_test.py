"""Hardware-free tests for the HIL BLE utility's deterministic helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from ble_inspector import (BleInspector, ScanRecord, evaluate_n6_gatt, parse_command,
                           resolve_device, serialize_advertisement,
                           serialize_services)


def main() -> int:
    device = SimpleNamespace(address="40:82:7B:03:B8:FA", name="fallback")
    advertisement = SimpleNamespace(
        local_name="N6-MAINT-B8FA",
        rssi=-47,
        tx_power=0,
        service_uuids=["7A1E0001-B5A3-F393-E0A9-E50E24DCCA9E"],
        manufacturer_data={0x1234: b"\x01\xAB"},
        service_data={"180f": b"\x64"},
    )
    record = ScanRecord(device, advertisement)
    assert resolve_device([record], "1") is record
    assert resolve_device([record], "40:82:7b:03:b8:fa") is record
    try:
        resolve_device([record], "2")
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range scan index was accepted")

    serialized = serialize_advertisement(device, advertisement)
    assert serialized["local_name"] == "N6-MAINT-B8FA"
    assert serialized["rssi_dbm"] == -47
    assert serialized["manufacturer_data"]["0x1234"] == "01AB"
    assert serialized["service_data"]["180f"] == "64"
    assert parse_command('connect "40:82:7B:03:B8:FA"') == [
        "connect", "40:82:7B:03:B8:FA"
    ]

    descriptor = SimpleNamespace(uuid="2902", description="CCCD", handle=13)
    characteristic = SimpleNamespace(
        uuid="7a1e0003-b5a3-f393-e0a9-e50e24dcca9e",
        description="Unknown",
        handle=12,
        properties=["notify", "read"],
        descriptors=[descriptor],
    )
    service = SimpleNamespace(
        uuid="7a1e0001-b5a3-f393-e0a9-e50e24dcca9e",
        description="Unknown",
        handle=10,
        characteristics=[characteristic],
    )
    services = serialize_services([service])
    assert services[0]["label"] == "N6 CLI service"
    assert services[0]["characteristics"][0]["label"] == "N6 CLI TX"
    assert services[0]["characteristics"][0]["properties"] == ["notify", "read"]
    incomplete_contract = evaluate_n6_gatt(services)
    assert incomplete_contract["detected"]
    assert not incomplete_contract["passed"]
    assert "7a1e0101-b5a3-f393-e0a9-e50e24dcca9e" in incomplete_contract["missing_uuids"]

    with tempfile.TemporaryDirectory() as temporary_directory:
        report_path = Path(temporary_directory) / "report.json"
        inspector = BleInspector(report_path, 1.0, 1.0)
        inspector.write_report("self-test", True, value=7)
        report = report_path.read_text(encoding="utf-8")
        assert '"ok": true' in report and '"value": 7' in report

    print("HIL utility self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
