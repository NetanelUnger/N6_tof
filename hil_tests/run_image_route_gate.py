"""Physical CRC/ownership gate: BLE -> USB dataset -> BLE, without reset/Flash.

Requires an otherwise free BLE link and CN8 port. With --cloud, an already
paired Cloud image stream must be running; its accepted-frame counter must
stop while BLE/USB own the destination. Browser rendering is checked separately.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from ble_inspector import BleInspector, N6_STREAM_UUIDS, TofFrameAssembler
from run_milestone4_gate import UsbCli, find_cn8

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training/scripts"))
from protocol import FrameReader


async def run(args: argparse.Namespace) -> dict:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    inspector = BleInspector(args.report.with_name("image-route-ble.json"),
                             6, 20, uncached_services=True)
    assembler = TofFrameAssembler()
    frames: list[dict] = []
    packet_count = 0
    invalid_headers = 0
    usb = None
    result = {"passed": False, "cloud_tested": False}

    def receive(_, data):
        nonlocal packet_count, invalid_headers
        packet_count += 1
        if len(data) < 20 or data[:3] != b"N6\x01":
            invalid_headers += 1
        frame = assembler.push(data)
        if frame is not None:
            frames.append(frame)

    async def wait_frames(count):
        start = len(frames)
        deadline = time.monotonic() + args.frame_timeout
        while len(frames) - start < count:
            if time.monotonic() >= deadline:
                raise TimeoutError("BLE did not deliver enough complete CRC-valid frames")
            await asyncio.sleep(0.05)

    async def cloud_count(label):
        reply = await asyncio.to_thread(usb.command, "cloud status")
        result[label] = reply
        match = re.search(r"ToF: sent (\d+)", reply)
        assert match and ", paired," in reply, "Cloud must remain paired"
        return int(match.group(1))

    try:
        usb = await asyncio.to_thread(UsbCli, find_cn8(args.port))
        if args.cloud:
            assert await cloud_count("cloud_initial") > 0, "No accepted Cloud image yet"
            route = await asyncio.to_thread(usb.command, "tof status")
            assert "requested CLOUD, active CLOUD" in route, route
        await inspector.scan(6)
        await inspector.connect(args.device)
        client = inspector.require_connection()
        # Firmware drains BLE CLI input only for an active CLI Notify session.
        await client.start_notify(N6_STREAM_UUIDS["cli"]["tx"], lambda _, data: None)
        await asyncio.sleep(0.5)
        await client.start_notify(N6_STREAM_UUIDS["tof"]["tx"], receive)
        await wait_frames(args.ble_frames)
        result["before"] = await asyncio.to_thread(usb.command, "tof status")
        assert "requested BLE, active BLE" in result["before"], result["before"]
        if args.cloud:
            cloud_stopped = await cloud_count("cloud_during_ble")
        print("BLE frames and CRC: PASS", flush=True)

        usb.serial.write(b"dataset stream on\r")
        reader = FrameReader(usb.serial)
        usb_ids = []
        for index in range(args.usb_frames):
            frame = await asyncio.to_thread(reader.read_frame, 5)
            usb_ids.append(frame.frame_id)
            if index == 0:
                # Allow already-delivered WinRT callbacks to settle. The first
                # USB frame proves the device has drained the old BLE owner.
                await asyncio.sleep(0.2)
                ble_at_usb_start = packet_count
        await asyncio.sleep(1.0)
        assert packet_count == ble_at_usb_start, "BLE image fragments continued during USB ownership"
        assert reader.crc_errors == 0, "USB record CRC failure"
        assert len(set(usb_ids)) == args.usb_frames, "Repeated USB frame identity"
        result["usb_frames"] = usb_ids
        result["usb_crc_errors"] = reader.crc_errors
        print("USB frames/CRC; BLE image traffic stopped: PASS", flush=True)

        usb.serial.write(b"dataset stream off\r")
        await asyncio.sleep(0.5)
        usb.serial.reset_input_buffer()
        result["middle"] = await asyncio.to_thread(usb.command, "tof status")
        if args.cloud:
            assert await cloud_count("cloud_after_usb") == cloud_stopped, "Cloud images continued during BLE/USB ownership"
        await client.write_gatt_char(N6_STREAM_UUIDS["cli"]["rx"], b"map on\r", response=True)
        await wait_frames(args.ble_frames)
        result["after"] = await asyncio.to_thread(usb.command, "tof status")
        assert "requested BLE, active BLE" in result["after"], result["after"]
        assert "ToF state: ready" in result["after"], result["after"]
        assert assembler.crc_errors == 0, "BLE frame CRC failure"
        assert invalid_headers == 0, "Non-image bytes appeared on the ToF characteristic"
        if args.cloud:
            assert await cloud_count("cloud_after_ble") == cloud_stopped, "Cloud images continued during BLE ownership"
            result["cloud_tested"] = True
            print("Cloud accepted-image counter stopped during BLE/USB ownership: PASS", flush=True)
        result["passed"] = True
        print("PASS: BLE -> USB -> BLE; complete frames, exclusive image destination", flush=True)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result.update(ble_frames=frames, ble_packets=packet_count,
                      ble_crc_errors=assembler.crc_errors,
                      ble_interrupted_frames=assembler.dropped,
                      invalid_ble_headers=invalid_headers)
        if inspector.client is not None and inspector.client.is_connected:
            for stream in ("tof", "cli"):
                try:
                    await inspector.client.stop_notify(N6_STREAM_UUIDS[stream]["tx"])
                except Exception:
                    pass
            try:
                await inspector.disconnect()
            except Exception:
                pass
        if usb:
            try:
                usb.serial.write(b"\rdataset stream off\r")
                await asyncio.sleep(0.3)
                usb.serial.reset_input_buffer()
                # Windows can retain a cached GATT link after Bleak disconnect.
                await asyncio.to_thread(usb.command, "ble disconnect")
            finally:
                usb.close()
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--cloud", action="store_true",
                        help="Require a live paired Cloud image stream and verify it stops during BLE/USB ownership")
    parser.add_argument("--device", default="n6")
    parser.add_argument("--ble-frames", type=int, default=10)
    parser.add_argument("--usb-frames", type=int, default=25)
    parser.add_argument("--frame-timeout", type=float, default=90)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "hil_tests/results/image-route-gate.json")
    args = parser.parse_args()
    if args.ble_frames < 1 or args.usb_frames < 2 or args.frame_timeout <= 0:
        parser.error("positive BLE count/timeout and at least two USB frames are required")
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
