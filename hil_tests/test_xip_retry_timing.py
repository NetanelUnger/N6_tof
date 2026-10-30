"""A retry must not make a32second block look like a2second ACK."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'Tools/analyze_xip_ota_timing.py'
spec=importlib.util.spec_from_file_location('ota_timing',path)
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)

class RetryTimingTests(unittest.TestCase):
    def test_original_start_survives_two_timeouts(self):
        rows=[{'message':'TX','block':473,'monotonicMs':t} for t in [100,15100,30100]]
        rows+=[{'message':'RX','block':473,'control':6,'monotonicMs':32800}]
        self.assertEqual(timing.retry_inclusive_delays(rows),[{'block':473,'attempts':3,'ms':32700}])
    def test_unacknowledged_or_untimed_blocks_are_not_invented(self):
        rows=[{'message':'TX','block':1,'monotonicMs':0},{'message':'RX','block':1,'control':0x15,'monotonicMs':20},
              {'message':'TX','block':2},{'message':'RX','block':2,'control':6}]
        self.assertEqual(timing.retry_inclusive_delays(rows),[])

if __name__=='__main__':unittest.main()
