import io
from pathlib import Path
import struct
import sys
import unittest
import zlib
import numpy as np
from protocol import FrameReader, build_test_record, VERSION_V4
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'hil_tests'))
from ble_inspector import TofFrameAssembler


def fragments(wire):
    for offset in range(0,len(wire),160):
        part=wire[offset:offset+160]
        header=bytearray(56)
        struct.pack_into('<HBBIHHBBBBI',header,0,0x364e,3,(1 if offset==0 else 0)|(2 if offset+len(part)==len(wire) else 0),
                         123,offset,len(wire),54,42,1,5,zlib.crc32(wire))
        struct.pack_into('<ffIH',header,20,0,0,456,56)
        struct.pack_into('<I',header,52,zlib.crc32(header[:52]))
        yield bytes(header)+part


class TrainingAssembly(unittest.TestCase):
    def test_complete_record_callback_has_no_stream_polling_timeout(self):
        from ble_sample_source import BleSampleSource
        source=BleSampleSource()
        source.device_id='fixture'; source.boot_id='ab'*16; source.device_info={}
        wire=build_test_record(np.full((42,54),350,dtype=np.uint16),frame_id=123,timestamp_ms=456,protocol_version=VERSION_V4)
        for _ in range(10):
            for packet in fragments(wire):source._image(None,packet)
            sample=source.frames.get_nowait()
            self.assertEqual(sample.frame.wire_record,wire)
        self.assertEqual(source.callback_errors,0)

    def test_production_fixture_roundtrip_and_disconnect(self):
        path=Path(__file__).resolve().parents[1]/'testdata/two-class-production-c.n6df'
        wire=path.read_bytes()
        assembler=TofFrameAssembler(retain_payload=True)
        packets=list(fragments(wire))
        for packet in packets: result=assembler.push(packet)
        self.assertEqual(result['payload'],wire)
        frame=FrameReader(io.BytesIO(result['payload'])).read_frame()
        self.assertEqual(frame.class_count,2)
        assembler.push(packets[0]); assembler.reset(count_drop=True)
        for packet in packets[1:]: self.assertIsNone(assembler.push(packet))
        self.assertEqual(assembler.completed,1)
        self.assertGreaterEqual(assembler.dropped,1)

    def test_bad_crc_and_out_of_order_never_complete(self):
        wire=build_test_record(np.full((42,54),350,dtype=np.uint16),protocol_version=VERSION_V4)
        packets=list(fragments(wire)); assembler=TofFrameAssembler(retain_payload=True)
        for packet in packets[:-1]: assembler.push(packet)
        bad=bytearray(packets[-1]);bad[-1]^=1
        self.assertIsNone(assembler.push(bad)); self.assertEqual(assembler.crc_errors,1)
        assembler.push(packets[0]);self.assertIsNone(assembler.push(packets[2]))
        self.assertEqual(assembler.completed,0)


if __name__=='__main__':unittest.main()
