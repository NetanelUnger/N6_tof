from pathlib import Path
import hashlib,json,ast
HERE=Path(__file__).parent
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
path=ROOT/'hil_tests/run_ble_npu_soak.py'
expected=json.loads((HERE/'evidence/st67-cp4-20261028/image-harness-adaptations.json').read_text())['source_sha256']
assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
source=path.read_text()
helper='''def require_receive_window_counts(start, end, duration):
    """Check the existing delivery floors using the frozen measurement window.

    Notifications arriving during end-state queries or cleanup cannot rescue
    a window that missed its throughput requirement.
    """
    measured = {name: end[name] - start[name] for name in ('images', 'results')}
    minimum = {'images': duration * 3000 // 3600,
               'results': duration * 6000 // 3600}
    for name in ('images', 'results'):
        assert measured[name] >= minimum[name], (
            f'{name} in measurement window: {measured[name]} < {minimum[name]}'
        )
    return {'measured': measured, 'minimum': minimum}


'''
source=source.replace('def cli_main():',helper+'def cli_main():',1)
old="                assert len(report['images'])>=start_images+int(duration*3000/3600) and len(report['results'])>=start_results+int(duration*6000/3600) and assembler.crc_errors==0"
assert source.count(old)==1
source=source.replace(old,"                report['receive_count_gate']=require_receive_window_counts(report['soak_start_counts'],report['soak_end_counts'],duration)\n                assert assembler.crc_errors==0")
ast.parse(source);path.write_text(source,encoding='utf-8',newline='\n')
test='''"""A soak must not gain credit for frames received after its measurement window."""
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
'''
dest=ROOT/'hil_tests/test_ble_soak_measurement_window.py';assert not dest.exists();dest.write_text(test,encoding='utf-8',newline='\n')
print('Fixed only host soak acceptance window; original rates/latency/gap/CRC limits unchanged.')
