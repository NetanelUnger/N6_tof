"""Nonbonded BLE adapter using the existing N6 GATT and ToF assembler."""
from __future__ import annotations
import asyncio
from dataclasses import asdict
import io
from pathlib import Path
import queue
import re
import sys
import threading
import time
import uuid
from sample_sources import Sample, SourceError, SourceStats, utc_now
from protocol import decode_record, HEADER_SIZE_V4

HIL_ROOT = Path(__file__).resolve().parents[2] / 'hil_tests'
if str(HIL_ROOT) not in sys.path: sys.path.insert(0, str(HIL_ROOT))
from ble_inspector import TofFrameAssembler

RX='7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
TX='7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
TOF='7a1e0004-b5a3-f393-e0a9-e50e24dcca9e'


async def scan_devices(timeout=5):
    from bleak import BleakScanner
    return [d for d in await BleakScanner.discover(timeout=timeout)
            if (d.name or '').startswith('N6-MAINT-')]


def discover_ble():
    return [{'address':d.address, 'name':d.name} for d in asyncio.run(scan_devices())]


class BleSampleSource:
    kind='ble'
    def __init__(self, port=None, *, expected_device=None, address=None):
        self.address=address or (port if port and ':' in port else None)
        self.expected_device=expected_device
        self.stats=SourceStats()
        self.connection_id=uuid.uuid4().hex
        self.device_id=self.boot_id=None
        self.before={}; self.after={}; self.restore_error=None
        self.owns_stream=False; self.client=None
        self.frames=queue.Queue(maxsize=2)
        self.assembler=TofFrameAssembler(retain_payload=True)
        self.cli=bytearray(); self.queue_drops=0; self.callback_errors=0
        self.loop=None; self.worker=None; self.os_is_paired=None

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    def _submit(self, coroutine, timeout=45):
        async def bounded():
            return await asyncio.wait_for(coroutine, timeout=timeout)
        return asyncio.run_coroutine_threadsafe(bounded(),self.loop).result(timeout+2)

    def _disconnected(self, client):
        self.stats.state='disconnected'
        self.assembler.reset(count_drop=True)
        while not self.frames.empty():
            try: self.frames.get_nowait()
            except queue.Empty: break

    async def command(self, command, expected=None, timeout=5):
        self.cli.clear()
        await self.client.write_gatt_char(RX,(command+'\r').encode('ascii'),response=True)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            response=bytes(self.cli)
            if ((b'[CLI-RESULT] state=complete' in response or b'\r\nn6> ' in response) and
                    (expected is None or expected in response)):
                return response.decode('utf-8','replace')
            if len(response)>131072: raise SourceError('BLE command response exceeded bounded window.')
            await asyncio.sleep(.01)
        raise SourceError('BLOCKED: BLE command timed out: '+command.split()[0])

    def _image(self, _, data):
        try:
            packet=self.assembler.push(data)
            self.stats.crc_errors=self.assembler.crc_errors
            if packet is None: return
            if packet['pixel_format'] != 5:
                self.callback_errors+=1; return
            wire=packet['payload']
            # The existing assembler already provides a complete bounded
            # datagram. Decode it directly; a serial stream reader would poll
            # BytesIO one byte at a time and invent an I/O timeout here.
            frame=decode_record(wire[:HEADER_SIZE_V4],wire[HEADER_SIZE_V4:])
            if frame.frame_id != packet['frame_id'] or frame.timestamp_ms != packet['timestamp_ms']:
                raise SourceError('BLE envelope and N6DF source identity differ.')
            sample=Sample(frame,self.device_id,self.boot_id,self.connection_id,self.kind,
                          utc_now(),time.monotonic_ns(),device_info=self.device_info)
            try: self.frames.put_nowait(sample)
            except queue.Full: self.queue_drops+=1
        except Exception as exc:
            self.callback_errors+=1
            self.stats.last_error=str(exc)
            self.stats.framing_errors+=1

    async def _open(self):
        from bleak import BleakClient
        devices=await scan_devices()
        if self.address:
            devices=[d for d in devices if d.address.upper()==self.address.upper()]
        if len(devices)!=1: raise SourceError('BLOCKED: select exactly one advertised N6 BLE device using Discover.')
        device=devices[0]; self.address=device.address
        failures=[]
        for kind in ('public','random','automatic'):
            opts={'use_cached_services':True}
            if kind!='automatic': opts['address_type']=kind
            candidate=BleakClient(device,pair=False,timeout=12,winrt=opts,disconnected_callback=self._disconnected)
            try:
                await candidate.connect(); self.client=candidate; break
            except Exception as exc:
                failures.append(type(exc).__name__)
                await candidate.disconnect()
        else: raise SourceError('BLOCKED: nonbonded BLE connect failed ('+', '.join(failures)+'). No Pair/cache operation performed.')
        if sys.platform=='win32':
            self.os_is_paired=bool(self.client._backend._requester.device_information.pairing.is_paired)
            if self.os_is_paired: raise SourceError('BLOCKED: Windows device is already paired; no pairing changes were made.')
        chars={c.uuid.lower():c for service in self.client.services for c in service.characteristics}
        if not all(u in chars for u in (RX,TX,TOF)): raise SourceError('BLOCKED: required existing N6 GATT characteristics absent.')
        if 'notify' not in chars[TOF].properties: raise SourceError('BLOCKED: ToF training characteristic does not support Notify.')
        await self.client.start_notify(TX,lambda _,data:self.cli.extend(data))
        capabilities=await self.command('dataset capabilities',b'Dataset capabilities:')
        if not all(x in capabilities for x in ('record=N6DF4','ble=1','ble_format=5','boot_identity=1')):
            raise SourceError('BLOCKED: firmware does not advertise lossless BLE training capability.')
        info=await self.command('radio info',b'NCP MAC:')
        mac=re.search(r'NCP MAC:\s*([0-9A-Fa-f:]{17})',info)
        if not mac: raise SourceError('BLOCKED: cannot establish BLE device identity.')
        self.device_id='n6:'+mac[1].lower()
        if self.expected_device and self.device_id.lower()!=self.expected_device.lower():
            raise SourceError('BLOCKED: discovered BLE device is not the selected N6 target.')
        tof=await self.command('tof status',b'ToF state:')
        dataset=await self.command('dataset stream status',b'Dataset stream:')
        self.before={'tof':tof,'dataset':dataset,'capabilities':capabilities}
        if 'Dataset stream: on' in dataset or 'Map: on' in tof:
            raise SourceError('BLOCKED: an existing stream is active; no takeover performed.')
        if 'ToF state: ready' not in tof or 'acquisition: running' not in tof:
            raise SourceError('BLOCKED: ToF is not running and ready.')
        route=re.search(r'Image destination: requested (\w+)',tof)
        if not route: raise SourceError('BLOCKED: cannot establish prior stream route.')
        self.previous_route=route[1].lower()
        identity=await self.command('dataset session',b'Dataset session:')
        match=re.search(r'Dataset session:\s*([a-f0-9]{32})',identity)
        if not match:
            identity=await self.command('dataset session '+uuid.uuid4().hex,b'Dataset session:')
            match=re.search(r'Dataset session:\s*([a-f0-9]{32})',identity)
        if not match: raise SourceError('BLOCKED: RAM capture identity unavailable.')
        self.boot_id=match[1]
        version=await self.command('version',b'Firmware version:')
        self.device_info={'firmware_version':re.search(r'Firmware version:\s*(\d+)',version)[1],
                          'ble_address':self.address,'identity_source':'NCP MAC','pair_requested':False,
                          'os_is_paired':self.os_is_paired}
        await self.client.start_notify(TOF,self._image)
        # Set ownership before requesting start: cleanup also handles an ACK
        # timeout after a command that may already have executed.
        self.owns_stream=True
        await self.command('dataset stream on',b'Dataset stream enabled')
        self.stats.state='streaming'

    def open(self):
        self.loop=asyncio.new_event_loop()
        self.worker=threading.Thread(target=self._run,daemon=True); self.worker.start()
        try: self._submit(self._open(),timeout=55)
        except Exception:
            self.stop(); raise

    def read(self,timeout=3):
        if self.stats.state!='streaming': raise SourceError('BLE disconnected; partial records were discarded.')
        try:
            sample=self.frames.get(timeout=timeout); self.stats.received+=1; return sample
        except queue.Empty:
            self.stats.timeouts+=1; raise TimeoutError('No complete BLE training record in bounded receive window.')

    async def _stop(self):
        try:
            if self.client and self.client.is_connected and self.owns_stream:
                await self.command('dataset stream off',b'Dataset stream disabled')
                self.owns_stream=False
                await self.command('dataset route '+self.previous_route,b'Capture route restored.')
                self.after['tof']=await self.command('tof status',b'ToF state:')
                self.after['dataset']=await self.command('dataset stream status',b'Dataset stream:')
                if 'Dataset stream: off' not in self.after['dataset'] or 'requested '+self.previous_route.upper() not in self.after['tof']:
                    raise SourceError('BLE capture runtime restoration was not confirmed.')
            elif self.owns_stream:
                raise SourceError('BLE disconnected before stream-off/route restoration was confirmed.')
        except Exception as exc: self.restore_error=str(exc)
        finally:
            if self.client:
                if self.client.is_connected:
                    for characteristic in (TOF,TX):
                        try: await self.client.stop_notify(characteristic)
                        except Exception: pass
                await self.client.disconnect()
            self.assembler.reset(count_drop=True)

    def stop(self):
        if not self.loop or not self.loop.is_running(): return
        try: self._submit(self._stop(),timeout=25)
        except Exception as exc: self.restore_error=str(exc)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.worker.join(timeout=3)
            self.stats.state='closed'

    def status(self):
        return {**asdict(self.stats),'source':self.kind,'device_id':self.device_id,'boot_id':self.boot_id,
                'connection_id':self.connection_id,'before':self.before,'after':self.after,
                'restore_error':self.restore_error,'queue_capacity':2,'queue_drops':self.queue_drops,
                'partial_drops':self.assembler.dropped,'callback_errors':self.callback_errors,
                'pair_requested':False,'os_is_paired':self.os_is_paired,'address':self.address,
                'worker_closed':self.worker is None or not self.worker.is_alive()}
