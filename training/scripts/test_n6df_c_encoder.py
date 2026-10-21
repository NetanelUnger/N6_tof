"""Decode bytes emitted by the actual production C dataset publisher."""
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import numpy as np
from model_contract import create, generate_header
from project_context import ProjectService
from protocol import FrameReader


def extract(source, name):
    source = source.replace('__attribute__((optimize("Os")))', '')
    match = re.search(r"static\s+(?:void|uint32_t)\s+" + name + r"\s*\([^;{]*\)\s*\{", source)
    if not match:
        raise ValueError(f"Missing production function: {name}")
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end] + "\n"


class NativeDataset(unittest.TestCase):
    def test_two_and_four_class_production_records(self):
        training = Path(__file__).resolve().parents[1]
        project = training.parent
        source = (project / "AppliNonSecure/Core/Src/tof_app.c").read_text(encoding="utf-8-sig")
        macros = "\n".join(line for line in source.splitlines() if line.startswith("#define TOF_DATASET_"))
        publisher = ''.join(extract(source, name) for name in
                            ("tof_crc32", "tof_write_u16", "tof_write_u32", "tof_stream_dataset_frame"))
        prefix = r'''
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include <io.h>
#include <fcntl.h>
#include "rps_ai.h"
typedef unsigned long ULONG;
typedef int TOF_ImageFilter_t;
typedef struct {void *data; ULONG capacity;} App_Console_FrameBuffer_t;
#define UX_FALSE 0
#define TX_SUCCESS 0
#define TOF_STREAM_USB 1
static unsigned char buffer[16384], model[3200]; static size_t committed;
static struct {unsigned dataset_stream_enabled;} tof_desired={1};
static struct {struct {unsigned dataset_frames_submitted,dataset_frames_dropped,dataset_last_frame,dataset_last_crc32;}counters;}tof_context;
static int TOF_App_GetStreamDestination(void){return 1;}
static int App_Console_IsReady(void){return 1;}
static int App_Console_AcquireFrameBuffer(App_Console_FrameBuffer_t *out){out->data=buffer;out->capacity=sizeof buffer;return 0;}
static int App_Console_CommitFrameBuffer(App_Console_FrameBuffer_t *out,ULONG n){assert(out->data==buffer);committed=n;return 0;}
static void App_Console_CancelFrameBuffer(App_Console_FrameBuffer_t *out){(void)out;assert(0);}
int RPS_AI_GetModelInputView(RPS_AI_ImageView_t *out){out->pixels=model;out->frame_id=123;out->width=64;out->height=50;out->is_npu_input=1;out->mve_accelerated=1;return 0;}
void RPS_AI_GetStatus(RPS_AI_Status_t *out){memset(out,0,sizeof *out);out->ready=out->enabled=1;out->last_frame=123;out->runs=42;out->class_id=RPS_AI_CLASS_COUNT-1;for(unsigned i=0;i<RPS_AI_CLASS_COUNT;i++)out->scores[i]=(int8_t)(-100+(int)i);}
'''
        main = r'''
int main(void){float depth[54*42];for(unsigned i=0;i<54*42;i++)depth[i]=(float)((i*3U)%1300U);
for(unsigned i=0;i<3200;i++)model[i]=(i%5)?255:0;
tof_stream_dataset_frame(depth,54,42,123,456,0);assert(committed && tof_context.counters.dataset_frames_submitted==1);
_setmode(_fileno(stdout),_O_BINARY);return fwrite(buffer,1,committed,stdout)==committed?0:1;}
'''
        with tempfile.TemporaryDirectory(prefix="n6df-c-") as temporary:
            root = Path(temporary)
            shutil.copytree(training / "config", root / "training/config")
            service = ProjectService(root / "training")
            manifest = service.create("fixture", "Fixture")
            model_path = root / "fixture.tflite"; model_path.write_bytes(b"contract fixture only")
            for count in (2, 4):
                selected = dict(manifest, classes=manifest["classes"][:count])
                contract = create(selected, {"input": {"dtype":"uint8","shape":[1,50,64,1],"scale":1.0,"zero_point":0},
                    "output":{"dtype":"int8","shape":[1,count],"scale":1/256,"zero_point":-128}}, model_path)
                (root / "n6_model_contract.h").write_text(generate_header(contract))
                shutil.copy2(project / "AppliNonSecure/Core/Inc/rps_ai.h", root / "rps_ai.h")
                (root / "test.c").write_text(prefix + macros + '\n' + publisher + main)
                vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
                vsroot = subprocess.check_output([str(vswhere),"-latest","-products","*","-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64","-property","installationPath"], text=True).strip()
                batch = root / "build.cmd"
                batch.write_text(f'@echo off\ncall "{vsroot}/VC/Auxiliary/Build/vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W3 test.c /Fe:test.exe\n')
                build = subprocess.run(["cmd.exe","/d","/c",str(batch)],cwd=root,capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stdout+build.stderr)
                actual = subprocess.check_output([str(root / "test.exe")], cwd=root)
                frame = FrameReader(io.BytesIO(actual)).read_frame()
                self.assertEqual(frame.class_count,count)
                self.assertEqual(frame.npu_scores,tuple(range(-100,-100+count)))
                self.assertEqual(frame.contract_sha256,contract["contract_sha256"])
                self.assertEqual((frame.frame_id,frame.model_frame_id,frame.npu_frame_id),(123,123,123))
                expected = ((np.arange(54*42)*3)%1300).astype(np.uint16).reshape(42,54)
                expected[expected==0]=65535
                np.testing.assert_array_equal(frame.depth_mm,expected)
                np.testing.assert_array_equal(frame.model_input,(np.where(np.arange(3200)%5,255,0)).astype(np.uint8).reshape(50,64))
                if os.environ.get("N6DF_FIXTURE_OUTPUT"):
                    output = Path(os.environ["N6DF_FIXTURE_OUTPUT"])
                    output.mkdir(parents=True,exist_ok=True)
                    (output/f"n6df4-{count}-class-c.bin").write_bytes(actual)


if __name__ == "__main__":
    unittest.main()
