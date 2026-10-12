"""One-hour unreachable Wi-Fi/Cloud profile with BLE reconnect/backpressure.

Uses a nonexistent test SSID and a non-secret test password, never installs
firmware or changes the Cloud endpoint/token. Radio/Cloud loop rates are observed
as bounded-worker evidence, not a measurement of whole-chip CPU utilization.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import threading
import time

from bleak import BleakClient, BleakScanner
from run_milestone4_gate import UsbCli, find_cn8, atomic_json

RX = '7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
TX = '7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'


async def run(args):
    report = {'passed': False, 'required_s': args.seconds, 'ble': [],
              'usb': [], 'attempts': [], 'snapshots': [], 'connections': [],
              'bursts': [], 'cpu_measurement': 'Radio/Cloud loop rate only'}
    stop, ready = threading.Event(), threading.Event()
    client = None
    received = bytearray()
    started = time.monotonic()

    def usb_work():
        cli = None
        try:
            cli = UsbCli(find_cn8(args.port))
            report['initial'] = {c: cli.command(c, 1) for c in ('radio status', 'wifi status', 'cloud status')}
            if 'STA GOT IP' in report['initial']['wifi status']:
                report['disconnect'] = cli.command('wifi disconnect', 1)
                until = time.monotonic()+35
                while time.monotonic()<until:
                    if 'STA GOT IP' not in cli.command('wifi status', 1): break
                    time.sleep(.2)
                else: raise TimeoutError('Wi-Fi disconnect did not complete')
            ready.set()
            next_attempt, next_snapshot = time.monotonic(), time.monotonic()
            while not stop.is_set():
                tick = time.monotonic()
                token = 'F'+str(len(report['usb']))
                text = cli.command('debug ping '+token, 1)
                report['usb'].append({'ms': round((time.monotonic()-tick)*1000), 'ok': 'PONG '+token+' ' in text})
                assert report['usb'][-1]['ok'], 'USB ping missing'
                if tick>=next_snapshot:
                    row = {c: cli.command(c, 1) for c in ('status', 'radio status', 'ble status', 'cloud status', 'debug uart')}
                    row['elapsed_s'] = round(time.monotonic()-started, 2)
                    report['snapshots'].append(row)
                    assert 'Wi-Fi IP ready' not in row['status'], 'Unexpected reachable network'
                    assert 'ToF: ready' in row['status'], 'ToF stopped during failure profile'
                    assert 'Radio allocations: failed=0' in row['radio status'], 'Radio allocation failure'
                    assert 'state=3 stage=' not in row['radio status'], 'Recovery failed closed'
                    next_snapshot = time.monotonic()+60
                if tick>=next_attempt:
                    # Gate admission; rejected means no uncertain command replay.
                    state = cli.command('radio status', 1)
                    if 'state=available reason=READY' in state:
                        text = cli.command('wifi connect '+args.invalid_ssid, 1)
                        assert 'password' in text.lower(), 'Password prompt absent'
                        cli.serial.write(b'N6-invalid-HIL-password\r')
                        cli._read(.5)
                        report['attempts'].append({'elapsed_s': round(time.monotonic()-started), 'ssid': args.invalid_ssid})
                        next_attempt = time.monotonic()+300
                stop.wait(1)
        except Exception as exc:
            report['usb_error'] = repr(exc)
            stop.set()
            ready.set()
        finally:
            if cli:
                try: report['final_usb'] = {c: cli.command(c, 1) for c in ('status', 'radio status', 'ble status', 'cloud status', 'debug uart')}
                except Exception as exc: report['final_usb_error'] = repr(exc)
                finally: cli.close()

    async def connect():
        nonlocal client, received
        devices = await BleakScanner.discover(timeout=6)
        device = next((d for d in devices if d.address.upper()==args.ble_address.upper()), None)
        assert device is not None, 'BLE advertisement absent'
        client = BleakClient(device, timeout=25, winrt={'use_cached_services': False})
        await client.connect()
        chars = {c.uuid for s in client.services for c in s.characteristics}
        assert RX in chars and TX in chars, 'BLE GATT contract missing'
        received = bytearray()
        await client.start_notify(TX, lambda _, data: received.extend(data))
        report['connections'].append({'elapsed_s': round(time.monotonic()-started), 'mtu': client.mtu_size})
        await asyncio.sleep(1)

    async def send(tokens):
        before, tick = len(received), time.monotonic()
        for token in tokens:
            payload = ('debug ping '+token+'\r').encode()
            for offset in range(0, len(payload), 20):
                await client.write_gatt_char(RX, payload[offset:offset+20], response=True)
            # Deliberate four-command burst: no wait for a previous final.
            if len(tokens)>1: await asyncio.sleep(.02)
        while time.monotonic()<tick+30 and not stop.is_set():
            text = received[before:].decode(errors='replace')
            if all('PONG '+token+' ' in text for token in tokens) and len(re.findall(r'\[CLI-RESULT\] state=complete\b', text))>=len(tokens):
                row = {'tokens': tokens, 'ms': round((time.monotonic()-tick)*1000), 'text': text}
                report['ble'].append(row)
                if len(tokens)>1: report['bursts'].append(row)
                return
            await asyncio.sleep(.01)
        report['failed_command'] = {
            'tokens': tokens, 'ms': round((time.monotonic()-tick)*1000),
            'text': received[before:].decode(errors='replace'),
            'connected': bool(client.is_connected),
        }
        raise TimeoutError('BLE final/PONG missing: '+','.join(tokens))

    worker = threading.Thread(target=usb_work)
    try:
        worker.start()
        assert await asyncio.to_thread(ready.wait, 45), 'USB setup not ready'
        assert not report.get('usb_error'), report.get('usb_error')
        await connect()
        started = time.monotonic()
        next_burst, next_reconnect, next_progress = started+30, started+300, started+60
        count = 0
        while time.monotonic()-started<args.seconds and not stop.is_set():
            now = time.monotonic()
            if now>=next_reconnect:
                await client.disconnect()
                await connect()
                next_reconnect = time.monotonic()+300
            tokens = ['B'+str(count)]
            if now>=next_burst:
                tokens = ['Q'+str(count)+'_'+str(i) for i in range(4)]
                next_burst = time.monotonic()+60
            await send(tokens)
            count += 1
            if now>=next_progress:
                summary = {'elapsed_s': round(time.monotonic()-started), 'ble_commands': sum(len(r['tokens']) for r in report['ble']), 'usb_pings': len(report['usb']), 'connections': len(report['connections']), 'bursts': len(report['bursts']), 'invalid_attempts': len(report['attempts'])}
                atomic_json(args.report.with_suffix('.progress.json'), summary)
                # Preserve the raw replies and counters if the host session is
                # interrupted. A checkpoint is never a completed acceptance.
                atomic_json(args.report.with_suffix('.checkpoint.json'), report)
                print(json.dumps(summary), flush=True)
                next_progress = time.monotonic()+60
            await asyncio.sleep(.13)
        report['elapsed_s'] = round(time.monotonic()-started, 2)
        assert not report.get('usb_error'), report.get('usb_error')
        assert report['elapsed_s']>=args.seconds, 'Failure soak ended early'
        assert len(report['connections'])>=args.seconds//600+1, 'Reconnect evidence insufficient'
        assert report['bursts'], 'No deliberate backpressure bursts'
        assert report['attempts'], 'No unreachable-AP attempt'
        # Cumulative reset/loop counters expose unclassified reboots and busy
        # worker cadence. This does not claim parser/SPI worst-case CPU usage.
        rows = report['snapshots']
        recovery_counts = [int(re.search(r'attempts=(\d+) ready=', r['radio status'])[1]) for r in rows]
        assert len(set(recovery_counts))==1, 'Unexpected NCP recovery during offline test'
        uptime = [int(re.search(r'Uptime: (\d+)', r['status'])[1]) for r in rows]
        assert all(b>a for a,b in zip(uptime, uptime[1:])), 'Unclassified MCU reset'
        rates = []
        for a,b in zip(rows, rows[1:]):
            dt = b['elapsed_s']-a['elapsed_s']
            radio = (int(re.search(r'Radio loop: count=(\d+)', b['radio status'])[1])-int(re.search(r'Radio loop: count=(\d+)', a['radio status'])[1]))/dt
            cloud = (int(re.search(r'Worker: loops (\d+)', b['cloud status'])[1])-int(re.search(r'Worker: loops (\d+)', a['cloud status'])[1]))/dt
            rates.append({'radio_per_s': round(radio, 2), 'cloud_per_s': round(cloud, 2)})
            # Notifications legitimately wake Radio faster than its20 ms
            # idle timeout. Loop counts are not CPU utilization; an arbitrary
            # 100 Hz cap would reject useful event-driven work as a busy loop.
            assert radio>=0 and cloud>=0, 'Worker counter regressed'
        report['worker_rates'] = rates
        report['passed'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        report['elapsed_s'] = round(time.monotonic()-started, 2)
        stop.set()
        await asyncio.to_thread(worker.join, 60)
        if client:
            try: await client.disconnect()
            except Exception as exc:
                report['cleanup_error'] = repr(exc)
                report['passed'] = False
        atomic_json(args.report, report)
        print(json.dumps({'passed': report['passed'], 'error': report.get('error'), 'ble_commands': sum(len(r['tokens']) for r in report['ble']), 'usb_pings': len(report['usb'])}), flush=True)
    return report['passed']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=3600)
    parser.add_argument('--invalid-ssid', default='N6-HIL-MISSING-FAILURE-SOAK')
    parser.add_argument('--ble-address', default='40:82:7B:03:B8:FB')
    parser.add_argument('--port')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds<60: parser.error('at least60 seconds required')
    raise SystemExit(0 if asyncio.run(run(args)) else 1)


if __name__ == '__main__':
    main()
