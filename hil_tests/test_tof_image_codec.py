"""Compile the production C codec and test its wire bytes independently.
No hardware. Optional --fixtures writes C-generated vectors for browser tests.
"""
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
        random.seed(42);vectors=[];cases=0
        datasets=[('mixed',[0,4000,4001.25,4123.75,4508,float('nan'),float('inf'),-1]),('constant',[123.5]*8),('invalid',[float('nan'),0,-1,float('inf')]*2),('zeros',[0.0]*8),('tiny',[1e-40,2e-40,3e-40,0]*2),('random',[random.uniform(1,8000) for _ in range(2268)])]
        for name,values in datasets:
          width,height=(54,42) if len(values)==2268 else (8,1)
          original=struct.pack('<'+'f'*len(values),*values);values=struct.unpack('<'+'f'*len(values),original)
          for channel in (1,2,3,4,5):
            for mode in (1,2,3):
              buffer=C.create_string_buffer(original+b'GUARD');info=Info(123,456,0,0,0,0,width,height,channel,mode)
              assert lib.TofImage_Encode(buffer,len(original),C.byref(info))==0
              assert buffer.raw[len(original):len(original)+5]==b'GUARD'
              payload=buffer.raw[:info.payload_length];assert zlib.crc32(payload)==info.payload_crc32
              assert len(payload)==len(values)*{1:4,2:2,3:1}[mode]
              if mode==1: assert payload==original
              else:
                codes=struct.unpack('<'+('H' if mode==2 else 'B')*len(values),payload)
                for value,code in zip(values,codes):
                  valid=math.isfinite(value) and (value>0 if channel==1 else value>=0)
                  assert (code!=0)==valid
                  if valid:
                    decoded=info.base+(code-1)*info.step
                    assert abs(decoded-value)<=info.step/2+max(abs(value)*1e-7,1e-44),(value,decoded,info.step)
              info.npu_state=3;info.npu_class=2;info.npu_confidence=987;info.npu_frame=123;info.npu_runs=789;info.npu_inference_ms=4
              header=C.create_string_buffer(56);lib.TofImage_Header(header,C.byref(info),0,3);h=header.raw
              assert h[:4]==b'N6\x03\x03' and struct.unpack_from('<H',h,10)[0]==len(payload)
              assert zlib.crc32(h[:52])==struct.unpack_from('<I',h,52)[0]
              assert struct.unpack_from('<BBHHIII',h,34)==(3,2,987,0,123,789,4)
              if channel in (1,2) and name in ('mixed','constant','invalid','zeros'):
                vectors.append(dict(name=f'{name}-{channel}-{mode}',packet=(h+payload).hex(),values=[v if math.isfinite(v) else None for v in values],mode=mode,channel=channel))
              cases+=1
        b=C.create_string_buffer(32);info=Info(0,0,0,0,0,0,8,1,1,2)
        assert lib.TofImage_Encode(b,31,C.byref(info))==-1
        for field,value in [('width',55),('height',43),('channel',0),('mode',5)]:
          old=getattr(info,field);setattr(info,field,value);assert lib.TofImage_Encode(b,32,C.byref(info))==-1;setattr(info,field,old)
        if args.fixtures: args.fixtures.parent.mkdir(parents=True,exist_ok=True);args.fixtures.write_text(json.dumps(vectors,indent=2)+'\n',encoding='utf-8')
        print(f'PASS {cases} actual-C codec cases, capacity/shape/mode guards, CRC and quantization error bounds')
if __name__=='__main__':main()
