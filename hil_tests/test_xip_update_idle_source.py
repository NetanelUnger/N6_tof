import unittest
from run_xip_usb_update import validate_source_cloud_idle

def status(count,route='NONE'):
 return {'tof status':f'requested {route}, active {route}','cloud status':f'ToF: sent {count}, dropped 0'}
class AdmissionTests(unittest.TestCase):
 def test_default_requires_zero(self):
  self.assertEqual(validate_source_cloud_idle(status(0)),0)
  with self.assertRaises(AssertionError):validate_source_cloud_idle(status(674))
 def test_history_requires_stable_idle_recheck(self):
  self.assertEqual(validate_source_cloud_idle(status(674),status(674)),674)
  with self.assertRaises(AssertionError):validate_source_cloud_idle(status(674),status(675))
 def test_active_route_is_never_accepted(self):
  for route in ('BLE','CLOUD','USB'):
   with self.assertRaises(AssertionError):validate_source_cloud_idle(status(1,route),status(1))
   with self.assertRaises(AssertionError):validate_source_cloud_idle(status(1),status(1,route))
 def test_missing_counter_is_rejected(self):
  with self.assertRaises(AssertionError):validate_source_cloud_idle({'tof status':'requested NONE, active NONE','cloud status':'truncated'},status(0))
if __name__=='__main__':unittest.main()
