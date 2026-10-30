"""Host-only regression for the old-source CDC race; no serial port is opened."""
import unittest
from types import SimpleNamespace
from run_xip_usb_update import wait_usb_disconnect

class DisconnectTests(unittest.TestCase):
    def test_source_must_disappear(self):
        ticks=[0.0];calls=[];source=SimpleNamespace(device='COM8',serial_number='N6TOF001')
        def ports():
            calls.append(ticks[0]);return [source] if ticks[0]<.15 else []
        wait_usb_disconnect(ports,now=lambda:ticks[0],sleep=lambda n:ticks.__setitem__(0,ticks[0]+n))
        self.assertGreaterEqual(ticks[0],.15);self.assertGreater(len(calls),1)
    def test_absent_source_returns_without_wait(self):
        wait_usb_disconnect(lambda:[],now=lambda:0,sleep=lambda n:self.fail('unexpected wait'))
    def test_still_running_source_stops_bounded(self):
        ticks=[0.0];source=SimpleNamespace(device='COM8',serial_number='N6TOF001')
        with self.assertRaisesRegex(RuntimeError,'No automatic USB disconnect'):
            wait_usb_disconnect(lambda:[source],now=lambda:ticks[0],sleep=lambda n:ticks.__setitem__(0,ticks[0]+n),seconds=.1)
        self.assertLess(ticks[0],.2)
if __name__=='__main__':unittest.main()
