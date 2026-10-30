"""N6 diagnostic BLE session shared by the desktop UI and unattended runner."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from collections import deque

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hil_tests'))
from cli_text_protocol import reply_finished, reply_succeeded
from ble_inspector import TofFrameAssembler

RX = '7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
TX = '7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
SERVICE = '7a1e0001-b5a3-f393-e0a9-e50e24dcca9e'
IMAGE = '7a1e0004-b5a3-f393-e0a9-e50e24dcca9e'
READ_COMMANDS = ('version', 'status', 'tof status', 'rps status', 'radio status',
                 'radio info', 'ble status', 'wifi status', 'debug uart',
                 'dataset stream status', 'DEMO MAP STATUS', 'MAP ENCODING', 'help')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class BleConsoleError(RuntimeError):
    pass


class HardwareLease:
    """Use the repository's shared lease, including linked worktrees."""
    def __init__(self):
        self.process = None

    async def acquire(self):
        if self.process is not None:
            return
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / 'hil_tests/n6_hardware_lease.py'),
            '--owner-thread', 'n6-ble-console-' + uuid.uuid4().hex[:12],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=0x08000000 if sys.platform == 'win32' else 0)
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), 10)
            if b'"ownership": "HELD"' not in line:
                raise BleConsoleError(line.decode(errors='replace').strip() or 'Cannot acquire hardware lease')
        except BaseException:
            await self.release()
            raise

    async def release(self):
        process, self.process = self.process, None
        if process is not None:
            try:
                await asyncio.wait_for(process.communicate(b'release\n'), 10)
            except (BrokenPipeError, ConnectionResetError):
                await process.wait()
            except asyncio.TimeoutError:
                self.process = process
                raise BleConsoleError('Lease cleanup did not finish; close this app before another hardware test')


class BleSession:
    def __init__(self, event=None, *, scanner=None, client_factory=None, lease=None):
        self.emit = event or (lambda kind, data: None)
        self.scanner = scanner
        self.client_factory = client_factory
        self.lease = lease or HardwareLease()
        self.client = None
        self.devices = {}
        self.address = None
        self.generation = 0
        self.pending = None
        self.changed = asyncio.Event()
        self.lock = asyncio.Lock()
        self.disconnected = False
        self.last_error = None
        self.subscribed = False
        self.last_failure = None
        self.images = TofFrameAssembler(retain_payload=True)
        self.image_subscribed = False
        self.original_encoding = None
        self.latest_image = None
        self.image_events = deque(maxlen=4000)
        self.lifecycle = deque(maxlen=200)
        self.image_errors = 0
        self.last_notification = None
        self.last_cli_notification = None
        self.last_image_at = None
        self.max_image_gap = 0
        self.host_closing = False
        self.tainted = False
        self.chars = {}

    @property
    def connected(self):
        return self.client is not None and self.client.is_connected and not self.disconnected

    async def scan(self):
        if self.connected:
            raise BleConsoleError('Disconnect before scanning')
        await self.lease.acquire()
        try:
            if self.scanner is None:
                from bleak import BleakScanner
                self.scanner = BleakScanner
            found = await self.scanner.discover(timeout=5, return_adv=True)
            self.devices = {device.address: device for device, adv in found.values()
                            if (adv.local_name or device.name or '').startswith('N6-MAINT-')
                            or SERVICE in [s.lower() for s in adv.service_uuids]}
            return [{'address': d.address, 'name': d.name or 'N6'} for d in self.devices.values()]
        finally:
            await self.lease.release()

    async def connect(self, address):
        if self.client is not None:
            raise BleConsoleError('Disconnect the current session first')
        await self.lease.acquire()
        try:
            if self.scanner is None:
                from bleak import BleakScanner
                self.scanner = BleakScanner
            device = await self.scanner.find_device_by_address(address, timeout=8)
            if device is None:
                raise BleConsoleError('N6 advertisement not found. Check power and disconnect another BLE client.')
            if self.client_factory is None:
                from bleak import BleakClient
                self.client_factory = BleakClient
            self.generation += 1
            generation = self.generation
            self.disconnected = False
            self.last_error = None
            self.tainted = False
            self.host_closing = False
            self.images = TofFrameAssembler(retain_payload=True)
            self.latest_image = None
            self.image_events.clear()
            self.last_image_at = None
            self.max_image_gap = 0
            self.image_errors = 0
            self.last_notification = None
            self.last_cli_notification = None
            def disconnected(client):
                if generation == self.generation:
                    self.disconnected = True
                    self.images.reset(count_drop=True)
                    self.lifecycle.append({'event':'disconnect', 'monotonic':time.monotonic(), 'utc':utc_now(),
                                           'host_requested':self.host_closing})
                    self.changed.set()
                    self.emit('connection', 'Disconnected')
            self.client = self.client_factory(device, pair=False, timeout=15,
                disconnected_callback=disconnected,
                winrt={'use_cached_services': True, 'address_type': 'public'})
            await asyncio.wait_for(self.client.connect(), 20)
            if sys.platform == 'win32':
                requester = self.client._backend._requester
                if requester.device_information.pairing.is_paired:
                    raise BleConsoleError('Windows already reports this device paired; no pairing changes were made')
            chars = {c.uuid.lower(): c for service in self.client.services for c in service.characteristics}
            self.chars = chars
            if RX not in chars or TX not in chars or 'notify' not in chars[TX].properties or 'write' not in chars[RX].properties:
                raise BleConsoleError('Expected N6 CLI GATT characteristics/properties are missing')
            await asyncio.wait_for(self.client.start_notify(TX,
                lambda sender, data: self._notify(generation, data)), 10)
            self.subscribed = True
            self.address = address
            self.lifecycle.append({'event':'connect', 'monotonic':time.monotonic(), 'utc':utc_now()})
            self.emit('connection', 'Connected: ' + address)
        except BaseException:
            await self.close()
            raise

    def _notify(self, generation, data):
        if generation != self.generation or self.pending is None:
            return
        self.last_cli_notification = time.monotonic()
        if len(self.pending) + len(data) > 131072:
            self.last_error = 'CLI response exceeds 128 KiB'
        else:
            self.pending.extend(data)
        self.changed.set()

    def _image_notify(self, generation, data):
        if generation != self.generation or not self.image_subscribed:
            return
        self.last_notification = time.monotonic()
        try:
            frame = self.images.push(data)
            if frame is not None:
                now = time.monotonic()
                if self.last_image_at is not None:
                    self.max_image_gap = max(self.max_image_gap, now-self.last_image_at)
                self.last_image_at = now
                frame['host_monotonic'] = now
                self.latest_image = frame
                self.image_events.append({k:v for k,v in frame.items() if k!='payload'})
        except Exception:
            self.image_errors += 1
            self.images.reset(count_drop=True)

    async def start_images(self, mode='UINT8'):
        if mode not in ('RAW','UINT16','UINT8','JPEG'): raise ValueError('Unsupported display encoding')
        if not self.connected: raise BleConsoleError('Connect first')
        if IMAGE not in self.chars: raise BleConsoleError('ToF Notify characteristic is missing')
        if self.image_subscribed:
            result=await self.command('MAP ENCODING '+mode)
            if not result['passed']: raise BleConsoleError(result['response'])
            return
        status=await self.command('tof status')
        if 'requested NONE, active NONE' not in status['response']:
            raise BleConsoleError('Another image route is active; stop it before starting this viewer')
        demo=await self.command('DEMO MAP STATUS')
        if 'Demo map: ON' in demo['response']:
            raise BleConsoleError('Stop the demo stream before viewing actual sensor images')
        original=await self.command('MAP ENCODING')
        found=re.search(r'Wireless encoding: (RAW|UINT16|UINT8|JPEG)',original['response'])
        if not found: raise BleConsoleError('Cannot determine existing image encoding')
        self.original_encoding=found[1]
        changed=await self.command('MAP ENCODING '+mode)
        if not changed['passed']: raise BleConsoleError(changed['response'])
        self.images.reset(count_drop=True)
        self.latest_image=None
        self.last_image_at=None
        self.max_image_gap=0
        self.image_subscribed=True
        generation=self.generation
        try:
            await self.client.start_notify(IMAGE,lambda _,data:self._image_notify(generation,data))
            result=await self.command('MAP ON')
            if not result['passed']: raise BleConsoleError(result['response'])
        except BaseException:
            try:
                await self.stop_images()
            except Exception as cleanup_error:
                self.lifecycle.append({'event':'image_cleanup_error','utc':utc_now(),
                                       'monotonic':time.monotonic(),'error':str(cleanup_error)})
            raise

    async def stop_images(self):
        if self.connected and self.image_subscribed:
            if not self.tainted:
                result=await self.command('MAP OFF')
                if not result['passed']: raise BleConsoleError(result['response'])
            await self.client.stop_notify(IMAGE)
        self.image_subscribed=False
        self.images.reset(count_drop=True)
        if self.connected and self.original_encoding and not self.tainted:
            result=await self.command('MAP ENCODING '+self.original_encoding)
            if not result['passed']: raise BleConsoleError('Encoding restoration failed')
            self.original_encoding=None
        elif self.original_encoding:
            raise BleConsoleError('Image notifications stopped; encoding restoration could not be confirmed after the link/session failed')

    async def command(self, text, timeout=8, disconnect_on_error=True):
        text = text.strip()
        if not text or len(text)>240 or any(ord(c)<32 or ord(c)>126 for c in text):
            raise BleConsoleError('Enter one printable ASCII command, at most 240 characters')
        if re.match(r'(?i)^(update(?:\s|$)|wifi\s+connect(?:\s|$)|cloud\s+pair(?:\s|$))',text):
            raise BleConsoleError('Interactive credential entry and binary firmware upload are not supported in this console')
        async with self.lock:
            if not self.connected:
                raise BleConsoleError('Connect to N6 first')
            if self.tainted: raise BleConsoleError('Previous command did not complete; reconnect before sending another')
            self.pending = bytearray()
            self.last_failure = None
            self.changed.clear()
            start = time.monotonic()
            try:
                async with asyncio.timeout(timeout):
                    await self.client.write_gatt_char(RX, (text + '\r').encode('ascii'), response=True)
                    while True:
                        if self.last_error:
                            raise BleConsoleError(self.last_error)
                        if self.disconnected:
                            raise BleConsoleError('BLE disconnected before the command completed')
                        raw = bytes(self.pending)
                        if reply_finished(raw):
                            response = raw.decode('utf-8', 'replace')
                            result = {'command': text, 'response': response,
                                      'ms': round((time.monotonic()-start)*1000, 2),
                                      'completed': True, 'passed': reply_succeeded(raw)}
                            self.emit('reply', result)
                            return result
                        self.changed.clear()
                        await self.changed.wait()
            except BaseException as error:
                # A late terminal must never be credited to the next command.
                self.last_failure = {'command': text, 'response': bytes(self.pending).decode('utf-8', 'replace'),
                                     'ms': round((time.monotonic()-start)*1000, 2),
                                     'completed': False, 'passed': False,
                                     'error': type(error).__name__+': '+str(error)}
                self.last_error = 'Command did not complete; reconnect before sending another command'
                self.tainted = True
                if disconnect_on_error:
                    # Already holding the command lock: only unsubscribe/close here.
                    await self.close(graceful=False)
                raise
            finally:
                self.pending = None

    async def close(self, graceful=True):
        client = self.client
        self.host_closing = True
        if client is not None:
            try:
                if self.image_subscribed:
                    if graceful and not self.tainted:
                        await self.stop_images()
                    elif client.is_connected:
                        await client.stop_notify(IMAGE)
                    self.image_subscribed=False
                if self.subscribed and client.is_connected:
                    if graceful and not self.tainted:
                        # WinRT disposal alone can leave the peripheral linked.
                        # Ask only our established N6 session to end its link;
                        # never reset the radio or replay a timed-out command.
                        await asyncio.wait_for(client.write_gatt_char(
                            RX, b'ble disconnect\r', response=True), 3)
                        deadline = time.monotonic()+2
                        while client.is_connected and time.monotonic()<deadline:
                            await asyncio.sleep(.05)
                    if client.is_connected:
                        await asyncio.wait_for(client.stop_notify(TX), 5)
                    self.subscribed = False
                await asyncio.wait_for(client.disconnect(), 10)
            except BaseException:
                self.emit('connection', 'Disconnect not confirmed; close again before another hardware test')
                raise
        self.client = None
        self.generation += 1
        self.disconnected = True
        self.changed.set()
        self.subscribed = False
        await self.lease.release()
        self.emit('connection', 'Disconnected')


async def run_checks(session, pings=20, interval=.2, stop=None):
    """Read-only health/latency checks. No image subscriptions or state setters."""
    if not 1 <= pings <= 500 or not 0 <= interval <= 10:
        raise ValueError('pings must be 1..500 and interval 0..10 seconds')
    result = {'started_utc': utc_now(), 'address': session.address, 'passed': False,
              'cancelled': False, 'pair_requested': False, 'image_subscription': False,
              'latency_limit_ms': 1500, 'checks': []}
    try:
        items = [(c, None) for c in ('version','tof status','rps status','radio status','debug uart','ble status')]
        token = uuid.uuid4().hex[:8]
        items += [('debug ping N6-'+token+'-'+str(i), 'N6-'+token+'-'+str(i)) for i in range(pings)]
        for command, ping in items:
            if stop and stop.is_set():
                result['cancelled'] = True
                break
            row = await session.command(command)
            if ping:
                row['passed'] &= ('PONG '+ping+' ') in row['response'] and row['ms'] <= 1500
            elif command == 'version':
                row['passed'] &= bool(re.search(r'Firmware version: \d+', row['response']))
            elif command == 'tof status':
                row['passed'] &= 'ToF state: ready' in row['response']
            elif command == 'rps status':
                row['passed'] &= all(s in row['response'] for s in ('ready=1','errors=0'))
            result['checks'].append(row)
            session.emit('check', row)
            if not row['passed']:
                result['error'] = 'Check failed: '+command
                break
            if ping:
                await asyncio.sleep(interval)
        result['passed'] = len(result['checks']) == len(items) and all(r['passed'] for r in result['checks'])
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
        if session.last_failure:
            result['checks'].append(session.last_failure)
            session.emit('check', session.last_failure)
    finally:
        result['finished_utc'] = utc_now()
        timings = [r['ms'] for r in result['checks'] if r['command'].startswith('debug ping ') and r.get('completed', True)]
        result['pings_completed'] = len(timings)
        result['ping_max_ms'] = max(timings, default=None)
    return result


def save_report(report, folder=None):
    folder = Path(folder or ROOT/'training/reports/ble_console')
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
    target = folder/name
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return target
