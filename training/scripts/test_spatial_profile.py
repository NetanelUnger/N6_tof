"""Compile the production C spatial helper and compare all bytes with Python."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np
from spatial_profile import preprocess


class SpatialProfile(unittest.TestCase):
    def test_actual_c_matches_python_and_preserves_position_depth(self):
        cfg = {"near_mm": 100, "far_mm": 1200, "invalid_mm": 65535,
               "model_width": 64, "model_height": 50}
        depth = ((np.arange(54 * 42, dtype=np.uint32) * 17) % 1300).astype(np.uint16).reshape(42, 54)
        depth.flat[0], depth.flat[1] = 0, 65535
        expected = preprocess(depth, cfg)[..., 0].tobytes()
        header = Path(__file__).with_name("spatial_depth_profile.h").as_posix()
        if not Path(header).exists():
            header = (Path(__file__).resolve().parents[2] / "AppliNonSecure/Core/Inc/spatial_depth_profile.h").as_posix()
        code = f'''#include <stdio.h>
#include "{header}"
int main(void) {{
  float input[54*42]; unsigned char output[64*50];
  for(unsigned i=0;i<54*42;i++) input[i]=(float)((i*17U)%1300U);
  input[0]=0; input[1]=65535;
  N6_SpatialDepthProfile(input,54,42,output,64,50,100,1200,65535);
#ifdef _WIN32
  _setmode(_fileno(stdout), _O_BINARY);
#endif
  return fwrite(output,1,sizeof(output),stdout)==sizeof(output)?0:1;
}}'''
        if os.name == "nt":
            code = "#include <io.h>\n#include <fcntl.h>\n" + code
        with tempfile.TemporaryDirectory(prefix="n6-spatial-") as temporary:
            folder = Path(temporary)
            (folder / "test.c").write_text(code, encoding="utf-8")
            if os.name == "nt":
                vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
                vsroot = subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
                vcvars = Path(vsroot) / "VC/Auxiliary/Build/vcvars64.bat"
                batch = folder / "build.cmd"
                batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W3 test.c /Fe:test.exe\n')
                subprocess.run(["cmd.exe", "/d", "/c", str(batch)], cwd=folder, check=True, capture_output=True)
                actual = subprocess.check_output([str(folder / "test.exe")], cwd=folder)
            else:
                subprocess.run(["cc", "-std=c11", "test.c", "-o", "test"], cwd=folder, check=True)
                actual = subprocess.check_output([str(folder / "test")], cwd=folder)
        self.assertEqual(actual, expected)
        left = np.full((42, 54), 1000, dtype=np.uint16)
        left[10:20, 3:13] = 300
        right = np.fliplr(left)
        farther = left.copy(); farther[10:20, 3:13] = 500
        self.assertFalse(np.array_equal(preprocess(left, cfg), preprocess(right, cfg)))
        self.assertFalse(np.array_equal(preprocess(left, cfg), preprocess(farther, cfg)))
        self.assertGreater(len(np.unique(preprocess(depth, cfg))), 2)


if __name__ == "__main__":
    unittest.main()
