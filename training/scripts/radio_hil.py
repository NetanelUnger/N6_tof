"""Host-side ST67 feature, version, and advertising checks for Stage 11."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any


CLI_SERVICE_UUID = "7a1e0001-b5a3-f393-e0a9-e50e24dcca9e"


def _feature_value(header: str, name: str) -> bool:
    match = re.search(
        rf"(?m)^\s*#define\s+{re.escape(name)}\s+\(\s*([01])U\s*\)\s*$",
        header,
    )
    if match is None:
        raise RuntimeError(f"Cannot read {name} from app_features.h")
    return match.group(1) == "1"


def load_feature_flags(project_root: Path) -> dict[str, bool]:
    header = (project_root / "AppliNonSecure" / "Core" / "Inc" /
              "app_features.h").read_text(encoding="utf-8")
    return {
        "radio": _feature_value(header, "APP_ST67W6X_ENABLED"),
        "ble": _feature_value(header, "APP_ST67W6X_BLE_GATT_ENABLED"),
        "wifi": _feature_value(header, "APP_ST67W6X_WIFI_SERVICES_ENABLED"),
    }


def load_radio_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / "radio_firmware" / "contract.json"
    if not path.is_file():
        raise RuntimeError(
            "radio_firmware/contract.json is missing; the module version "
            "cannot be validated."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _enabled(value: str) -> bool:
    return value.casefold() == "enabled"


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise RuntimeError(f"Invalid ST67 SDK version: {value}") from exc


def validate_radio_cli(text: str, flags: dict[str, bool],
                       expected_sdk_version: str) -> dict[str, Any]:
    hardware = re.search(
        r"build:\s*radio\s+(enabled|disabled),\s*BLE GATT\s+"
        r"(enabled|disabled),\s*Wi-Fi services\s+(enabled|disabled)",
        text,
        re.IGNORECASE,
    )
    if hardware is None:
        raise RuntimeError(
            "radio hardware did not return parseable feature flags. The "
            "connected image may not match the current source."
        )
    observed_flags = {
        "radio": _enabled(hardware.group(1)),
        "ble": _enabled(hardware.group(2)),
        "wifi": _enabled(hardware.group(3)),
    }
    if observed_flags != flags:
        raise RuntimeError(
            f"Radio feature mismatch: source={flags}, board={observed_flags}. "
            "Run 10_LOAD_RAM.bat again."
        )

    report: dict[str, Any] = {
        "source_flags": dict(flags),
        "board_flags": observed_flags,
        "expected_sdk_version": expected_sdk_version,
        "cli_text": text,
    }
    if not flags["radio"]:
        report.update({"result": "pass", "reason": "radio disabled by source"})
        return report

    status = re.search(
        r"ST67 radio status:.*?manager:\s*([^\r\n]+).*?"
        r"W6X_Init:\s*([^\r\n]+).*?"
        r"BLE maintenance GATT:\s*([^,\r\n]+),\s*advertising:\s*"
        r"([^,\r\n]+),\s*link:\s*([^\r\n]+).*?"
        r"Wi-Fi services:\s*([^\r\n]+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if status is None:
        raise RuntimeError("radio status did not return a parseable runtime state.")
    manager = status.group(1).strip().casefold()
    init_result = status.group(2).strip().casefold()
    ble_gatt = status.group(3).strip().casefold()
    advertising = status.group(4).strip().casefold()
    wifi_services = status.group(6).strip().casefold()
    report["runtime"] = {
        "manager": manager,
        "w6x_init": init_result,
        "ble_gatt": ble_gatt,
        "advertising": advertising,
        "wifi_services": wifi_services,
    }
    if manager != "ready" or init_result != "passed":
        raise RuntimeError(
            "ST67 initialization is not ready: "
            f"manager={manager}, W6X_Init={init_result}. Check the ST-LINK "
            "UART boot log, 3.3 V target power, shield jumpers and SPI_RDY."
        )

    sdk_match = re.search(r"SDK:\s*(\d+\.\d+\.\d+)(?:\.\d+)?", text)
    if sdk_match is None:
        raise RuntimeError("radio info did not report an NCP SDK version.")
    observed_sdk = sdk_match.group(1)
    report["observed_sdk_version"] = observed_sdk
    if _version_tuple(observed_sdk) != _version_tuple(expected_sdk_version):
        raise RuntimeError(
            f"ST67 NCP SDK {observed_sdk} does not match the required "
            f"{expected_sdk_version}. Run radio_firmware\\01_UPDATE_MODULE.bat."
        )

    if flags["ble"]:
        if ble_gatt != "ready" or advertising != "on":
            raise RuntimeError(
                "BLE is enabled in app_features.h but its GATT server is not "
                f"ready/advertising (gatt={ble_gatt}, advertising={advertising})."
            )
        ble_detail = re.search(
            r"BLE GATT:\s*([^,\r\n]+),.*?advertising:\s*([^,\r\n]+),"
            r"\s*MTU:\s*(\d+).*?Name:\s*([^\r\n]+)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if ble_detail is None:
            raise RuntimeError("ble status did not return a parseable GATT status/name.")
        if (ble_detail.group(1).strip().casefold() != "ready" or
                ble_detail.group(2).strip().casefold() != "on"):
            raise RuntimeError("BLE detailed status is not ready and advertising.")
        report["ble"] = {
            "gatt": "ready",
            "advertising": "on",
            "mtu": int(ble_detail.group(3)),
            "device_name": ble_detail.group(4).strip(),
        }

    if flags["wifi"]:
        if wifi_services != "enabled":
            raise RuntimeError(
                "Wi-Fi is enabled in app_features.h but runtime reports it disabled."
            )
        station = re.search(r"Wi-Fi station:\s*([^\r\n]+)", text)
        scan = re.search(r"Wi-Fi scan complete \(status\s+(-?\d+)\)", text)
        if station is None or scan is None or int(scan.group(1)) != 0:
            raise RuntimeError(
                "Wi-Fi basic HIL did not complete both station-status and a "
                "successful passive connectivity scan."
            )
        report["wifi"] = {
            "station": station.group(1).strip(),
            "scan_status": int(scan.group(1)),
        }

    report["result"] = "pass"
    return report


async def _scan_ble(expected_name: str, timeout: float) -> dict[str, Any]:
    try:
        from bleak import BleakScanner
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Bleak is missing from training/.venv. Run 00_SETUP.bat again."
        ) from exc

    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches: list[dict[str, Any]] = []
    for device, advertisement in discovered.values():
        name = str(advertisement.local_name or device.name or "")
        uuids = {str(item).lower() for item in advertisement.service_uuids}
        if name == expected_name or (name.startswith("N6-MAINT-") and
                                     CLI_SERVICE_UUID in uuids):
            matches.append({
                "name": name,
                "address": str(device.address),
                "rssi_dbm": int(advertisement.rssi),
                "service_uuids": sorted(uuids),
            })
    exact = [item for item in matches if item["name"] == expected_name]
    if len(exact) != 1:
        raise RuntimeError(
            f"Expected one BLE advertisement named {expected_name!r}; "
            f"found {len(exact)}. Confirm Bluetooth is enabled and the "
            "ST67 antenna is not obstructed."
        )
    if CLI_SERVICE_UUID not in exact[0]["service_uuids"]:
        raise RuntimeError(
            f"{expected_name} is advertising but does not expose the N6 CLI "
            "service UUID in its advertisement."
        )
    return {"result": "pass", "timeout_seconds": timeout, **exact[0]}


def scan_ble_advertisement(expected_name: str, timeout: float = 8.0) -> dict[str, Any]:
    return asyncio.run(_scan_ble(expected_name, timeout))
