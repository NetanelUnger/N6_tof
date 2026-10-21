import io
import struct
import unittest
import numpy as np
from protocol import (VERSION_V3, VERSION_V4, HEADER_SIZE_V4, HEADER_V4,
                      FrameReader, ProtocolError, ChecksumError, build_test_record, crc32, decode_record)


class ClassifierRecords(unittest.TestCase):
    def test_two_four_sixteen_and_legacy(self):
        depth = np.arange(54*42, dtype=np.uint16).reshape(42, 54)
        tensor = (np.arange(3200) % 256).astype(np.uint8).reshape(50, 64)
        for count in (2, 4, 16):
            scores = tuple(range(-128, -128 + count))
            packet = build_test_record(depth, protocol_version=VERSION_V4, npu_scores=scores,
                npu_valid=True, npu_class_id=count-1, model_input=tensor, contract_sha256="ab"*32)
            frame = FrameReader(io.BytesIO(packet)).read_frame()
            self.assertEqual(frame.class_count, count)
            self.assertEqual(frame.npu_scores, scores)
            self.assertEqual(frame.contract_sha256, "ab"*32)
            np.testing.assert_array_equal(frame.model_input, tensor)
        old = FrameReader(io.BytesIO(build_test_record(depth, protocol_version=VERSION_V3))).read_frame()
        self.assertEqual(old.class_count, 4)
        self.assertIsNone(old.contract_sha256)

    def test_corrupt_and_incompatible_never_emit_records(self):
        depth = np.full((42, 54), 350, dtype=np.uint16)
        packet = build_test_record(depth, protocol_version=VERSION_V4, npu_scores=(-100, 100), npu_valid=True, npu_class_id=1)
        for offset, value in ((92, 17), (92, 1), (64, 2), (94, 99)):
            bad = bytearray(packet)
            bad[offset] = value
            struct.pack_into("<I", bad, 128, crc32(bad[:128]))
            with self.assertRaises(ProtocolError):
                decode_record(bytes(bad[:132]), bytes(bad[132:]))
        bad = bytearray(packet); bad[-1] ^= 1
        with self.assertRaises(ChecksumError):
            decode_record(bytes(bad[:132]), bytes(bad[132:]))
        self.assertEqual(HEADER_V4.size, HEADER_SIZE_V4)


if __name__ == "__main__":
    unittest.main()
