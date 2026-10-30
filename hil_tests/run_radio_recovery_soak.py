"""Combined BLE/USB/Cloud endurance. Never installs Flash or prints credentials.

Start the authorized Cloud receiver separately; --cloud-evidence contains its
progress, command and matching server-completion files. Wi-Fi password is read
only from N6_TEST_WIFI_PASSWORD. The HIL result retains failures and latency.
"""
from cli_text_protocol import reply_finished, reply_succeeded, reply_results

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import threading
import time

from bleak import BleakClient, BleakScanner
from ble_inspector import TofFrameAssembler
from run_milestone4_gate import UsbCli, find_cn8, atomic_json

RX = '7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
TX = '7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'


def load_json(path):
    # The independent receiver may be replacing a small progress file.
    for _ in range(20):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.02)
    raise RuntimeError('Cloud evidence unavailable: ' + path.name)


async def run_control_plane_soak(args):
    cloud_dir = args.cloud_evidence
    report = {'passed': False, 'duration_required_s': args.seconds,
              'ble': [], 'usb': [], 'warm': [], 'cloud': [], 'snapshots': []}
    stop = threading.Event()
    usb_ready = threading.Event()
    client = None
    worker = None
    started = time.monotonic()
    received = bytearray()
    assembler = TofFrameAssembler()
    address = args.ble_address.upper()

    def frames():
        return load_json(cloud_dir / 'cloud-progress.json')['frameCount']

    async def cloud_command(line, timeout=90):
        nonce = time.monotonic()
        atomic_json(cloud_dir / 'cloud-probe-command.json', {'line': line, 'nonce': nonce})
        until = nonce + timeout
        while time.monotonic() < until and not stop.is_set():
            sent = next((item for item in load_json(cloud_dir / 'cloud-live-sent.json')
                         if item.get('nonce') == nonce), None)
            if sent:
                outputs = load_json(cloud_dir / 'cloud-live-output.json') if (cloud_dir / 'cloud-live-output.json').exists() else []
                matching = [item for item in outputs if item['commandId'] == sent['id']]
                if any(item.get('completed') for item in matching):
                    row = {'line': line, 'id': sent['id'],
                           'ms': round((time.monotonic() - nonce) * 1000),
                           'text': ''.join(item.get('text') or '' for item in matching)}
                    report['cloud'].append(row)
                    assert reply_finished(row['text']), 'Cloud final absent'
                    return row
            await asyncio.sleep(.1)
        raise TimeoutError('Cloud matching completion missing: ' + line)

    def usb_work():
        cli = None
        try:
            cli = UsbCli(find_cn8(args.port))
            usb_ready.set()
            def wait_available():
                until = time.monotonic()+40
                while time.monotonic()<until and not stop.is_set():
                    text = cli.command('radio status', 1)
                    if 'state=available reason=READY' in text: return
                    stop.wait(.2)
                raise TimeoutError('Radio admission did not return')
            next_cycle = time.monotonic() + 5
            next_snapshot = time.monotonic()
            cycle = 0
            while not stop.is_set():
                tick = time.monotonic()
                token = 'U' + str(len(report['usb']))
                text = cli.command('debug ping ' + token, 1)
                report['usb'].append({'ms': round((time.monotonic()-tick)*1000),
                                      'ok': 'PONG ' + token + ' ' in text})
                assert report['usb'][-1]['ok'], 'USB ping missing'
                if time.monotonic() >= next_snapshot:
                    row = {line: cli.command(line, 1) for line in
                           ('radio status', 'ble status', 'tof status', 'cloud status', 'debug uart', 'debug route')}
                    row['elapsed_s'] = round(time.monotonic() - started)
                    report['snapshots'].append(row)
                    next_snapshot = time.monotonic() + 60
                if cycle < args.warm_cycles and time.monotonic() >= next_cycle:
                    row = {'cycle': cycle+1}
                    report['warm'].append(row)
                    wait_available()
                    row['disconnect'] = cli.command('wifi disconnect', 1)
                    assert 'rejected before execution' not in row['disconnect']
                    until = time.monotonic()+30
                    while time.monotonic()<until and not stop.is_set():
                        row['disconnected'] = cli.command('wifi status', 1)
                        if 'STA GOT IP' not in row['disconnected']: break
                        stop.wait(.2)
                    assert 'STA GOT IP' not in row['disconnected'], 'Wi-Fi never lost IP'
                    if stop.wait(3): break
                    wait_available()
                    text = cli.command('wifi connect ' + args.wifi_ssid, 1)
                    assert 'password' in text.lower(), 'Wi-Fi password prompt absent'
                    password = os.environ['N6_TEST_WIFI_PASSWORD']
                    cli.serial.write(password.encode() + b'\r')
                    password = ''
                    cli._read(.5)
                    until = time.monotonic()+45
                    while time.monotonic() < until and not stop.is_set():
                        row['wifi'] = cli.command('wifi status', 1)
                        if 'STA GOT IP' in row['wifi']: break
                        stop.wait(.2)
                    assert 'STA GOT IP' in row['wifi'], 'Wi-Fi IP did not return'
                    before = frames()
                    tick = time.monotonic()
                    while time.monotonic() < tick+30 and frames() < before+3 and not stop.is_set():
                        stop.wait(.1)
                    row['frames'] = frames()-before
                    row['cloud_return_ms'] = round((time.monotonic()-tick)*1000)
                    assert row['frames'] >= 3, 'Cloud CRC-valid frames did not return'
                    cycle += 1
                    next_cycle = time.monotonic()+args.warm_interval
                    print(json.dumps({'wifi_cycle': cycle, 'frames': row['frames'],
                                      'cloud_return_ms': row['cloud_return_ms']}), flush=True)
                stop.wait(1)
        except Exception as exc:
            report['usb_error'] = repr(exc)
            stop.set()
        finally:
            if cli:
                try:
                    report['final_usb'] = {line: cli.command(line, 1) for line in
                                          ('radio status', 'ble status', 'tof status', 'cloud status', 'debug uart', 'debug route')}
                except Exception as exc:
                    report['final_usb_error'] = repr(exc)
                finally:
                    cli.close()

    async def ble_command(line):
        before = len(received)
        tick = time.monotonic()
        payload = line.encode()+b'\r'
        for offset in range(0, len(payload), 20):
            await client.write_gatt_char(RX, payload[offset:offset+20], response=True)
        while time.monotonic() < tick+30 and not stop.is_set():
            text = received[before:].decode(errors='replace')
            if reply_finished(text):
                report['ble'].append({'line': line, 'ms': round((time.monotonic()-tick)*1000, 1), 'text': text})
                return text
            await asyncio.sleep(.01)
        raise TimeoutError('BLE final missing: ' + line)

    async def probes():
        number = 0
        while not stop.is_set():
            await asyncio.sleep(45)
            if stop.is_set(): break
            token = 'C' + str(number)
            row = await cloud_command('debug ping ' + token)
            assert 'PONG ' + token + ' ' in row['text'], 'Cloud PONG absent/wrong'
            assert reply_succeeded(row['text']), 'Cloud command failed'
            number += 1

    cloud_task = None
    try:
        devices = await BleakScanner.discover(timeout=5)
        device = next((item for item in devices if item.address.upper() == address), address)
        client = BleakClient(device, timeout=25,
                            winrt={'use_cached_services': False})
        await client.connect()
        await client.start_notify(TX, lambda _, data: received.extend(data))
        await asyncio.sleep(1)
        report['baseline_ble'] = await ble_command('ble status')
        started = time.monotonic()
        worker = threading.Thread(target=usb_work)
        worker.start()
        assert await asyncio.to_thread(usb_ready.wait, 10), 'USB did not open'
        # Entering the USB console intentionally turns MAP off. Claim Cloud
        # only after that, and after any restored Windows ToF CCCD.
        await cloud_command('map on')
        report['initial_frames'] = frames()
        cloud_task = asyncio.create_task(probes())
        next_progress = time.monotonic()+60
        number = 0
        while time.monotonic()-started < args.seconds and not stop.is_set():
            if cloud_task.done(): cloud_task.result()
            token = 'B' + str(number)
            text = await ble_command('debug ping ' + token)
            assert 'PONG ' + token + ' ' in text, 'Wrong/missing BLE PONG'
            number += 1
            if number % 20 == 0: await ble_command('radio status')
            if time.monotonic() >= next_progress:
                elapsed = round(time.monotonic()-started)
                values = sorted(row['ms'] for row in report['ble'])
                summary = {'elapsed_s': elapsed, 'ble_finals': len(values),
                           'ble_p95_ms': values[int((len(values)-1)*.95)],
                           'max_ms': max(values), 'cloud_frames': frames()-report['initial_frames'],
                           'usb_pings': len(report['usb']), 'wifi_cycles': len(report['warm'])}
                atomic_json(args.report.with_suffix('.progress.json'), summary)
                print(json.dumps(summary), flush=True)
                next_progress = time.monotonic()+60
            await asyncio.sleep(.13)
        report['elapsed_s'] = round(time.monotonic()-started, 1)
        assert not report.get('usb_error'), report.get('usb_error')
        assert report['elapsed_s'] >= args.seconds, 'Soak ended early'
        assert len(report['warm']) == args.warm_cycles, 'Warm cycles incomplete'
        report['final_ble'] = await ble_command('ble status')
        report['cloud_progress'] = load_json(cloud_dir/'cloud-progress.json')
        assert report['cloud_progress']['frameCount'] > report['initial_frames']+100
        assert not report['cloud_progress']['crcErrors'] and not report['cloud_progress']['protocolErrors']
        assert report['cloud'], 'No server-completed Cloud probe'
        values = sorted(row['ms'] for row in report['ble'])
        report['ble_p95_ms'] = values[int((len(values)-1)*.95)]
        report['ble_max_ms'] = max(values)
        report['passed'] = report['ble_p95_ms'] < 250
        if not report['passed']: report['error'] = 'BLE p95 >=250 ms'
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        stop.set()
        if cloud_task:
            cloud_task.cancel()
            await asyncio.gather(cloud_task, return_exceptions=True)
        if worker: await asyncio.to_thread(worker.join, 60)
        if client and client.is_connected: await client.disconnect()
        atomic_json(args.report, report)
        print(json.dumps({'passed': report['passed'], 'error': report.get('error'),
                          'ble_finals': len(report['ble']), 'usb_pings': len(report['usb'])}), flush=True)
    return report['passed']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--wifi-ssid', required=True)
    parser.add_argument('--warm-cycles', type=int, default=10)
    parser.add_argument('--warm-interval', type=int, default=150)
    parser.add_argument('--port')
    parser.add_argument('--ble-address', default='40:82:7B:03:B8:FB')
    parser.add_argument('--cloud-evidence', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('N6_TEST_WIFI_PASSWORD'): parser.error('N6_TEST_WIFI_PASSWORD required')
    raise SystemExit(0 if asyncio.run(run_control_plane_soak(args)) else 1)


if __name__ == '__main__':
    main()
