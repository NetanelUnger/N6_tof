"""A soak must not gain credit for frames received after its measurement window."""
import unittest
from run_ble_npu_soak import require_receive_window_counts


class ReceiveWindowTests(unittest.TestCase):
    def test_observed_99_frame_window_fails_despite_101_final_frames(self):
        # Actual B52 baseline: one warmup image,100 at window end,101 after queries.
        start={'images':1,'results':17}
        frozen_end={'images':100,'results':247}
        final_buffer={'images':101,'results':249}
        self.assertGreaterEqual(final_buffer['images']-start['images'],100)
        with self.assertRaisesRegex(AssertionError,'images in measurement window: 99 < 100'):
            require_receive_window_counts(start,frozen_end,120)

    def test_exact_window_thresholds_pass(self):
        result=require_receive_window_counts({'images':7,'results':19},
                                             {'images':107,'results':219},120)
        self.assertEqual(result['measured'],{'images':100,'results':200})
        self.assertEqual(result['minimum'],{'images':100,'results':200})

    def test_npu_shortfall_also_fails(self):
        with self.assertRaisesRegex(AssertionError,'results in measurement window: 199 < 200'):
            require_receive_window_counts({'images':0,'results':20},
                                         {'images':100,'results':219},120)

    def test_hourly_floors_preserved(self):
        result=require_receive_window_counts({'images':1,'results':3},
                                             {'images':3001,'results':6003},3600)
        self.assertEqual(result['minimum'],{'images':3000,'results':6000})


if __name__=='__main__':unittest.main(verbosity=2)
