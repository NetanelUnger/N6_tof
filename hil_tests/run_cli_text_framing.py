"""Read-only BLE framing check: version, help, unknown command; never pair."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from cli_text_protocol import reply_finished, reply_succeeded


async def verify(report, version, wifi_scan=False):
    from bleak import BleakClient, BleakScanner
    device = await BleakScanner.find_device_by_address('40:82:7B:03:B8:FB', timeout=10)
    assert device is not None, 'Exact N6 advertisement absent'
    async with BleakClient(device, pair=False, timeout=20) as client:
        assert not client._backend._requester.device_information.pairing.is_paired, 'OS paired; stop without changes'
        received = bytearray()
        parts = []
        def incoming(_, data):
            received.extend(data)
            parts.append(bytes(data).hex())
        tx = '7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
        await client.start_notify(tx, incoming)
        try:
            # The lazy GATT CLI may greet the new session before its first
            # command. Drain that handshake with an empty input line.
            await client.write_gatt_char('7a1e0002-b5a3-f393-e0a9-e50e24dcca9e', b'\r', response=True)
            deadline = time.monotonic()+5
            while not reply_finished(received) and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert reply_finished(received), 'Session handshake did not finish'
            report['handshake_hex'] = received.hex()
            commands = ['version', 'help', 'not-a-command'] + (['wifi scan'] if wifi_scan else [])
            for command in commands:
                received.clear(); parts.clear(); start = time.monotonic()
                await client.write_gatt_char('7a1e0002-b5a3-f393-e0a9-e50e24dcca9e',
                                             (command+'\r').encode(), response=True)
                while time.monotonic()-start < 15:
                    data = bytes(received)
                    if reply_finished(data): break
                    await asyncio.sleep(.01)
                else: raise TimeoutError('Final LF missing: '+command)
                report['commands'].append({'command': command, 'text': data.decode(errors='replace'),
                    'hex': data.hex(), 'parts': parts.copy(), 'ms': round((time.monotonic()-start)*1000, 2)})
                assert data.count(b'\n') == 1 and data.endswith(b'\n'), repr(data)
                assert b'CLI-RESULT' not in data and b'RADIO-SERVICE' not in data
                if command == 'version':
                    assert ('Firmware version: '+str(version)+'\r').encode() in data and reply_succeeded(data)
                elif command == 'help': assert data.count(b'\r') > 10 and reply_succeeded(data)
                elif command == 'wifi scan':
                    assert b'Wi-Fi scan request accepted:' in data and b'Wi-Fi scan:' in data and reply_succeeded(data)
                else: assert data.endswith(b'FAIL\r\n') and not reply_succeeded(data)
                print('PASS BLE', command, len(data), 'bytes', len(parts), 'notifications; one final LF', flush=True)
        finally: await client.stop_notify(tx)
    report['disconnected'] = True
    report['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--version', type=int, default=46)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--wifi-scan', action='store_true', help='Also verify one read-only asynchronous Wi-Fi scan')
    args = parser.parse_args()
    if not args.execute:
        print('HOST PREFLIGHT; no hardware opened'); return
    root = Path(__file__).resolve().parents[1]
    owner = json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert owner['thread'] == args.owner_thread, 'Matching held lease required'
    from n6_hardware_lease import windows_process_identity
    identity = windows_process_identity(owner['pid'])
    assert identity['state'] == 'alive' and identity['created_utc'] == owner['process_created_utc']
    assert args.output and args.output.resolve().is_relative_to(root) and not args.output.exists()
    report = {'passed': False, 'pair_requested': False, 'commands': []}
    try: asyncio.run(verify(report, args.version, args.wifi_scan))
    except BaseException as error:
        report['error'] = repr(error); raise
    finally: args.output.write_text(json.dumps(report, indent=2))


if __name__ == '__main__': main()
