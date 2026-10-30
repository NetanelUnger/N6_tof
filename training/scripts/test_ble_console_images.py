import io
import struct
import unittest
import zlib
import numpy as np
from PIL import Image
from ble_console_core import TofFrameAssembler
from ble_console_images import decode_pixels, colorize


def packets(payload,code=3,base=100,step=10):
    for offset in range(0,len(payload),5):
        part=payload[offset:offset+5];h=bytearray(56)
        struct.pack_into('<HBBIHHBBBBI',h,0,0x364e,3,(1 if offset==0 else 0)|(2 if offset+len(part)==len(payload) else 0),
                         7,offset,len(payload),4,2,1,code,zlib.crc32(payload))
        struct.pack_into('<ffIH',h,20,base,step,1234,56)
        struct.pack_into('<I',h,52,zlib.crc32(h[:52]))
        yield bytes(h)+part


def assembled(payload,code=3,base=100,step=10):
    assembler=TofFrameAssembler(retain_payload=True)
    for part in packets(payload,code,base,step):result=assembler.push(part)
    assert result is not None
    return result


class Images(unittest.TestCase):
    def test_raw_keeps_float_values_and_nan(self):
        values=np.array([1,2,np.nan,4,5,6,7,8],dtype='<f4')
        result=decode_pixels(assembled(values.tobytes(),1,0,0))
        np.testing.assert_allclose(result.reshape(-1),values,equal_nan=True)

    def test_quantized_affine_and_invalid(self):
        for code,dtype in [(2,'<u2'),(3,'u1')]:
            values=np.array([0,1,2,3,4,5,6,7],dtype=dtype)
            result=decode_pixels(assembled(values.tobytes(),code))
            np.testing.assert_allclose(result.reshape(-1),[np.nan,100,110,120,130,140,150,160],equal_nan=True)

    def test_jpeg_mask_and_constant(self):
        buffer=io.BytesIO();Image.new('L',(4,2),10).save(buffer,format='JPEG')
        frame=assembled(buffer.getvalue()+b'\x7f',4)
        pixels=decode_pixels(frame).reshape(-1)
        np.testing.assert_allclose(pixels[:7],190)
        self.assertTrue(np.isnan(pixels[-1]))

    def test_corruption_never_published(self):
        parts=list(packets(bytes(range(8))))
        for bad_header in (True,False):
            assembler=TofFrameAssembler(retain_payload=True)
            bad=bytearray(parts[-1]);bad[12 if bad_header else -1]^=1
            self.assertIsNone(assembler.push(parts[0]))
            self.assertIsNone(assembler.push(bad))
            self.assertEqual(assembler.completed,0);self.assertEqual(assembler.crc_errors,1)

    def test_missing_fragment_and_disconnect_reset(self):
        parts=list(packets(bytes(range(32)),code=1,base=0,step=0))
        assembler=TofFrameAssembler(retain_payload=True)
        assembler.push(parts[0]);assembler.push(parts[2])
        self.assertIsNone(assembler.pending)
        assembler.push(parts[0]);assembler.reset(count_drop=True)
        for part in parts[1:]:self.assertIsNone(assembler.push(part))
        self.assertEqual(assembler.completed,0)

    def test_dimension_and_mode_rejected(self):
        frame=assembled(bytes(range(8)))
        with self.assertRaises(ValueError):decode_pixels({**frame,'width':200})
        with self.assertRaises(ValueError):decode_pixels({**frame,'pixel_format':5})

    def test_render_invalid_and_range(self):
        image,low,high=colorize(np.array([[np.nan,10],[20,30]],dtype='f4'))
        self.assertEqual(image.size,(2,2));self.assertEqual((low,high),(10,30))
        self.assertEqual(image.getpixel((0,0)),(18,23,30))


if __name__=='__main__':unittest.main()
