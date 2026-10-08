"""Exercise the actual SPI CS wait with skipped-zero and stopped-timer reads."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_tof_recovery import function

ROOT = Path(__file__).resolve().parents[1]
PREFIX = r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
static uint32_t load, samples[8], length, reads, cs_hold_timer_fallbacks;
static uint32_t next(void) {
  uint32_t index = reads++;
  return samples[(index < length) ? index : length - 1];
}
#define SYSTICK_LOAD load
#define SYSTICK_VALUE next()
'''
TESTS = r'''
static void init(uint32_t first, uint32_t second) {
  load = 5999999; samples[0] = first; samples[1] = second; length = 2;
  reads = cs_hold_timer_fallbacks = 0;
}
int main(void) {
  init(1, 5999998); spi_port_wait_cs_hold(1200, 1200);
  assert(reads == 2 && !cs_hold_timer_fallbacks);
  puts("PASS endpoint zero: a reload that skips zero still completes");
  init(1000, 998); spi_port_wait_cs_hold(2200, 1200);
  assert(reads == 1 && !cs_hold_timer_fallbacks);
  puts("PASS ordinary hold completes at requested elapsed ticks");
  init(5999900, 5999800); spi_port_wait_cs_hold(1000, 1200);
  assert(reads == 2 && !cs_hold_timer_fallbacks);
  puts("PASS reload uses LOAD+1 and waits for remaining ticks");
  init(3000, 3000); spi_port_wait_cs_hold(3000, 1200);
  assert(reads == 1264 && cs_hold_timer_fallbacks == 1);
  puts("PASS frozen timer falls back after bounded core-cycle budget");
  init(0, 0); spi_port_wait_cs_hold(0, 1200);
  assert(reads == 1264 && cs_hold_timer_fallbacks == 1);
  puts("PASS disabled timer cannot strand SPI owner");
  return 0;
}
'''

def main():
    source = (ROOT / 'AppliNonSecure/Core/Src/spi_port.c').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='n6-spi-hold-') as temp:
        folder = Path(temp)
        (folder / 'test.c').write_text(PREFIX + function(source, 'spi_port_wait_cs_hold') + TESTS, encoding='utf-8')
        if os.name == 'nt':
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            vsroot = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            vcvars = Path(vsroot) / 'VC/Auxiliary/Build/vcvars64.bat'
            batch = folder / 'build.cmd'
            batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                             'cl /nologo /std:c11 /W3 test.c /Fe:test.exe\n', encoding='utf-8')
            subprocess.run(['cmd.exe', '/d', '/c', str(batch)], cwd=folder, check=True)
            subprocess.run([str(folder / 'test.exe')], cwd=folder, check=True)
        else:
            subprocess.run(['cc', '-std=c11', 'test.c', '-o', 'test'], cwd=folder, check=True)
            subprocess.run([str(folder / 'test')], cwd=folder, check=True)

if __name__ == '__main__':
    main()
