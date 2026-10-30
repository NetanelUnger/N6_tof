"""Protocol/lifecycle fault tests; no hardware or OS pairing changes."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from ble_console_core import BleSession, BleConsoleError, RX, TX, IMAGE, run_checks, save_report


class Lease:
    def __init__(self): self.held = False
    async def acquire(self): self.held = True
    async def release(self): self.held = False


class Scanner:
    @staticmethod
    async def find_device_by_address(address, timeout):
        return NS(address=address)


class Client:
    def __init__(self, device, **kwargs):
        assert kwargs['pair'] is False
        assert kwargs['winrt']['address_type'] == 'public'
        self.disconnected_callback = kwargs['disconnected_callback']
        self.is_connected = False
        self._backend = NS(_requester=NS(device_information=NS(pairing=NS(is_paired=False))))
        self.services = [NS(characteristics=[NS(uuid=RX,properties=['write']),NS(uuid=TX,properties=['notify']),NS(uuid=IMAGE,properties=['notify'])])]
        self.writes = []
        self.mode = 'normal'
        self.disconnect_error = False
    async def connect(self): self.is_connected = True
    async def disconnect(self):
        if self.disconnect_error: raise RuntimeError('disconnect failed')
        self.is_connected = False
        self.disconnected_callback(self)
    async def start_notify(self, characteristic, callback):
        if characteristic==TX:self.callback=callback
        else:self.image_callback=callback
    async def stop_notify(self, characteristic): self.stopped_notify = True
    async def write_gatt_char(self, characteristic, data, response):
        assert characteristic == RX and response
        self.writes.append(data)
        if self.mode == 'timeout': return
        if self.mode == 'disconnect':
            await self.disconnect();return
        if self.mode == 'overflow':
            self.callback(None,b'x'*131073);return
        if self.mode == 'failure':
            self.callback(None,b'not available\rFAIL\r\n');return
        command = data.decode().strip()
        if command == 'ble disconnect':
            self.device_disconnect_requested = True
            await self.disconnect()
            return
        if command == 'version': text = 'Firmware version: 57'
        elif command == 'tof status': text = 'ToF state: ready; requested NONE, active NONE'
        elif command == 'MAP ENCODING': text = 'Wireless encoding: RAW'
        elif command == 'rps status': text = 'ready=1 errors=0'
        elif command.startswith('debug ping '): text = 'PONG '+command.split()[-1]+' 100'
        else: text = 'status ready'
        wire = ('[CLI-RESULT] state=accepted\r\n'+text+'\r\r\n').encode()
        for chunk in (wire[:7],wire[7:32],wire[32:-1],wire[-1:]):
            self.callback(None,chunk)
            await asyncio.sleep(0)


class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lease=Lease()
        self.session=BleSession(scanner=Scanner,client_factory=Client,lease=self.lease)
        await self.session.connect('test')
    async def asyncTearDown(self):
        if self.session.client: self.session.client.disconnect_error=False
        await self.session.close()

    async def test_fragmented_accepted_is_not_final(self):
        reply=await self.session.command('version')
        self.assertTrue(reply['passed'])
        self.assertIn('Firmware version: 57',reply['response'])

    async def test_timeout_disconnects_and_prevents_late_reply_reuse(self):
        client=self.session.client;client.mode='timeout'
        with self.assertRaises(TimeoutError): await self.session.command('version',timeout=.02)
        self.assertFalse(self.lease.held)
        self.assertFalse(self.session.connected)
        self.assertFalse(self.session.last_failure['completed'])
        self.assertGreater(self.session.last_failure['ms'],0)
        await self.session.connect('test')
        old_generation=self.session.generation-2
        self.session.pending=bytearray()
        self.session._notify(old_generation,b'old reply\n')
        self.assertEqual(self.session.pending,bytearray())
        self.assertTrue((await self.session.command('version'))['passed'])

    async def test_disconnect_wakes_pending_command(self):
        self.session.client.mode='disconnect'
        with self.assertRaisesRegex(BleConsoleError,'disconnected'):
            await self.session.command('version')
        self.assertFalse(self.lease.held)

    async def test_overflow_is_bounded_and_disconnects(self):
        self.session.client.mode='overflow'
        with self.assertRaisesRegex(BleConsoleError,'128 KiB'):
            await self.session.command('version')
        self.assertFalse(self.lease.held)

    async def test_failed_terminal_is_not_pass(self):
        self.session.client.mode='failure'
        self.assertFalse((await self.session.command('version'))['passed'])

    async def test_commands_serialized(self):
        rows=await asyncio.gather(self.session.command('version'),self.session.command('tof status'))
        self.assertIn('Firmware version',rows[0]['response'])
        self.assertNotIn('Firmware version',rows[1]['response'])

    async def test_no_raw_or_multiline_commands(self):
        for command in ('update','version\rupdate','wifi connect secret','cloud pair 123456'):
            with self.assertRaises(BleConsoleError): await self.session.command(command)
        self.assertEqual(self.session.client.writes,[])

    async def test_disconnect_failure_keeps_coordination_lease(self):
        self.session.client.disconnect_error=True
        with self.assertRaises(RuntimeError): await self.session.close()
        self.assertTrue(self.lease.held)
        self.assertIsNotNone(self.session.client)

    async def test_device_disconnect_requested_while_notifications_available(self):
        client=self.session.client
        await self.session.close()
        self.assertTrue(client.device_disconnect_requested)
        self.assertFalse(self.lease.held)

    async def test_checks_and_report(self):
        report=await run_checks(self.session,pings=3,interval=0)
        self.assertTrue(report['passed'])
        self.assertEqual(report['pings_completed'],3)
        self.assertEqual(len(report['checks']),9)
        with tempfile.TemporaryDirectory() as folder:
            first=save_report(report,folder);second=save_report(report,folder)
            self.assertNotEqual(first,second)
            self.assertTrue(json.loads(first.read_text())['passed'])

    async def test_cancel_is_not_success(self):
        stop=asyncio.Event();stop.set()
        report=await run_checks(self.session,pings=1,stop=stop)
        self.assertTrue(report['cancelled']);self.assertFalse(report['passed'])
        self.assertEqual(self.session.client.writes,[])

    async def test_fail_fast_retains_response(self):
        self.session.client.mode='failure'
        report=await run_checks(self.session,pings=3)
        self.assertFalse(report['passed']);self.assertEqual(len(report['checks']),1)
        self.assertIn('FAIL',report['checks'][0]['response'])

    async def test_latency_failure_is_not_hidden(self):
        original=self.session.command
        async def slow(command):
            row=await original(command)
            if command.startswith('debug ping '): row['ms']=1501
            return row
        self.session.command=slow
        report=await run_checks(self.session,pings=3,interval=0)
        self.assertFalse(report['passed'])
        self.assertEqual(report['pings_completed'],1)
        self.assertEqual(report['ping_max_ms'],1501)

    async def test_existing_lease_blocks_before_scan(self):
        await self.session.close()
        class BlockedLease(Lease):
            async def acquire(self): raise BleConsoleError('Existing owner')
        session=BleSession(scanner=Scanner,client_factory=Client,lease=BlockedLease())
        with self.assertRaisesRegex(BleConsoleError,'Existing owner'):
            await session.connect('test')
        self.assertIsNone(session.client)

    async def test_stream_start_stop_restores_encoding(self):
        client=self.session.client
        await self.session.start_images('UINT8')
        self.assertTrue(self.session.image_subscribed)
        self.assertIn(b'MAP ON\r',client.writes)
        await self.session.stop_images()
        self.assertFalse(self.session.image_subscribed)
        self.assertEqual(client.writes[-2:],[b'MAP OFF\r',b'MAP ENCODING RAW\r'])

    async def test_soak_timeout_does_not_invent_a_disconnect(self):
        self.session.client.mode='timeout'
        with self.assertRaises(TimeoutError):
            await self.session.command('version',timeout=.02,disconnect_on_error=False)
        self.assertTrue(self.session.connected)
        self.assertTrue(self.lease.held)
        self.assertTrue(self.session.tainted)
        with self.assertRaisesRegex(BleConsoleError,'Previous command'):
            await self.session.command('version')


if __name__=='__main__': unittest.main()
