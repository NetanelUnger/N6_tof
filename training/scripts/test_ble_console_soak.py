import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from ble_console_core import BleSession
from ble_console_soak import run_soak
from test_ble_console import Scanner,Client,Lease
from test_ble_console_images import packets


class SoakTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session=BleSession(scanner=Scanner,client_factory=Client,lease=Lease())
        await self.session.connect('test')
    async def asyncTearDown(self):
        await self.session.close()
    async def test_cancelled_measurement_is_not_pass_or_disconnect(self):
        self.session.images.dropped=7  # Earlier stream teardown is outside this measurement.
        stop=asyncio.Event();stop.set()
        with tempfile.TemporaryDirectory() as folder:
            report,path=await run_soak(self.session,10,stop=stop,report_dir=folder)
            self.assertFalse(report['passed']);self.assertTrue(report['cancelled'])
            self.assertFalse(report['disconnect_observed_before_cleanup'])
            self.assertEqual(report['assembly_drops'],0)
            self.assertEqual(report['assembly_drops_total'],7)
            self.assertTrue(self.session.connected)
            self.assertFalse(self.session.image_subscribed)
            self.assertTrue(Path(path).exists())
    async def test_timeout_records_evidence_before_host_close(self):
        original=self.session.command
        async def command(text,**kwargs):
            if text.startswith('debug ping '):
                self.session.client.mode='timeout'
                kwargs['timeout']=.02
            return await original(text,**kwargs)
        self.session.command=command
        with tempfile.TemporaryDirectory() as folder:
            report,path=await run_soak(self.session,10,report_dir=folder)
            self.assertFalse(report['passed'])
            self.assertIn('TimeoutError',report['failure'])
            self.assertFalse(report['disconnect_observed_before_cleanup'])
            self.assertTrue(self.session.connected)
            self.assertFalse(report['commands'][-1]['completed'])
            self.assertEqual(report['lifecycle_before_cleanup'],[])
            self.assertIn('without proof',report['finding'])
            self.assertTrue(json.loads(Path(path).read_text())['failure'])


if __name__=='__main__':unittest.main()
