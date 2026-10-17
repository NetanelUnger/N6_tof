"""Compile the production C codec and test its wire bytes independently.
No hardware. Optional --fixtures writes C-generated vectors for browser tests.
"""
import io
from PIL import Image
import argparse, ctypes as C, json, math, os, random, struct, subprocess, tempfile, zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Info(C.Structure):
    _fields_=[('frame_id',C.c_uint32),('timestamp_ms',C.c_uint32),('payload_crc32',C.c_uint32),
              ('base',C.c_float),('step',C.c_float),('payload_length',C.c_uint16),
              ('width',C.c_uint8),('height',C.c_uint8),('channel',C.c_uint8),('mode',C.c_uint8),('npu_state',C.c_uint8),('npu_class',C.c_uint8),
              ('npu_confidence',C.c_uint16),('npu_frame',C.c_uint32),('npu_runs',C.c_uint32),('npu_inference_ms',C.c_uint32)]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixtures',type=Path);args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='n6-codec-',ignore_cleanup_errors=True) as temp:
        d=Path(temp);inc=ROOT/'AppliNonSecure/Core/Inc';src=ROOT/'AppliNonSecure/Core/Src/tof_image_codec.c'
        vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        vs=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
        batch=d/'build.cmd';batch.write_text(f'@echo off\ncall "{vs}/VC/Auxiliary/Build/vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W4 /WX /LD /I"{inc}" "{src}" "{src.parent / "tof_jpeg.c"}" /link /OUT:codec.dll /EXPORT:TofImage_Encode /EXPORT:TofImage_Header /EXPORT:TofImage_Crc32\n')
        subprocess.run(['cmd.exe','/d','/c',str(batch)],cwd=d,check=True)
        lib=C.CDLL(str(d/'codec.dll'));lib.TofImage_Encode.argtypes=[C.c_void_p,C.c_size_t,C.POINTER(Info)];lib.TofImage_Header.argtypes=[C.c_void_p,C.POINTER(Info),C.c_uint16,C.c_uint8]
        random.seed(71); vectors=[]
        for name in ('smooth','edge','holes','noise','constant','invalid'):
          values=[]
          for y in range(42):
            for x in range(54):
              v=1000+x*10+y*4 if name in ('smooth','holes') else (1000 if x<27 else 5000) if name=='edge' else random.uniform(500,6000) if name=='noise' else 1500
              if name=='invalid' or (name=='holes' and (x+y)%7==0):v=0
              values.append(v)
          raw=struct.pack('<2268f',*values);buf=C.create_string_buffer(raw+b'GUARD'); info=Info(123,456,0,0,0,0,54,42,1,4)
          assert lib.TofImage_Encode(buf,len(raw),C.byref(info))==0,name
          assert buf.raw[len(raw):len(raw)+5]==b'GUARD'
          payload=buf.raw[:info.payload_length];mask=payload[-284:];encoded=payload[:-284]
          assert zlib.crc32(payload)==info.payload_crc32
          img=Image.open(io.BytesIO(encoded));assert img.size==(54,42) and img.mode=='L'
          gray=list(img.getdata());errors=[]
          for i,v in enumerate(values):
            assert bool(mask[i//8]&(1<<(i%8)))==(v>0)
            if v>0:errors.append(abs(v-(info.base+(max(1,gray[i])-1)*info.step)))
          mae=sum(errors)/max(1,len(errors));maximum=max(errors,default=0)
          if name=='smooth':assert mae<20 and maximum<50
          if name in ('constant','invalid'):assert maximum==0
          print(name,info.payload_length,'bytes',round(mae,2),'MAE',round(maximum,2),'max')
          header=C.create_string_buffer(56);lib.TofImage_Header(header,C.byref(info),0,3)
          vectors.append(dict(name=name,packet=(header.raw+payload).hex(),values=values,reference=gray,mae=mae,maxError=maximum))
        # Output too small for JPEG: reject without writing past capacity.
        b=C.create_string_buffer(struct.pack('<f',1)+b'GUARD');i=Info(0,0,0,0,0,0,1,1,1,4)
        assert lib.TofImage_Encode(b,4,C.byref(i))==-1 and b.raw[4:9]==b'GUARD'
        if args.fixtures:args.fixtures.write_text(json.dumps(vectors))
        print('PASS JPEG independent Pillow decode, exact masks, bounded writes and error measurements')
if __name__=='__main__':main()
