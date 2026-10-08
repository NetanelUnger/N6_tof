"""Run the actual updater and XMODEM parser; mock only hardware/Secure calls.

Verifies duplicate-block handling and the Cloud reset barrier. This host test
does not establish Flash integrity or delivery over the physical radio.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "firmware_update.c"
static uint32_t tick, reset_count, drained, writes, bytes_written, finalized;
static uint8_t last_control;
uint32_t HAL_GetTick(void) { return tick; }
void NVIC_SystemReset(void) { ++reset_count; }
void Debug_UART_Log(const char *a, const char *b, ...) { (void)a; (void)b; }
void TOF_App_SetMapEnabled(uint32_t x) { (void)x; }
void TOF_App_SetPaused(uint32_t x) { (void)x; }
uint32_t SECURE_FirmwareUpdateBegin(const FW_UpdateManifest_t *m, uint32_t *s) {
  assert(m->image_size == 1024); *s = 1; return 0;
}
uint32_t SECURE_FirmwareUpdateWrite(uint32_t s, const void *p, uint32_t n) {
  assert(s == 1 && p); ++writes; bytes_written += n; return 0;
}
uint32_t SECURE_FirmwareUpdateFinalize(uint32_t s) {
  assert(s == 1 && bytes_written == 1024); ++finalized; return 0;
}
uint32_t SECURE_FirmwareUpdateAbort(uint32_t s) { (void)s; return 0; }
uint32_t SECURE_FirmwareUpdateConfirmBoot(void) { return 0; }
static int32_t output(const void *p, size_t n, void *ctx) {
  assert(ctx == &drained); if(n == 1) last_control = *(const uint8_t *)p; return 0;
}
static uint32_t ready(void *ctx) { assert(ctx == &drained); return drained; }
static void block(uint8_t sequence, const uint8_t *data) {
  uint8_t packet[1029] = { 2, 0, 0 };
  packet[1] = sequence; packet[2] = 255 - sequence;
  memcpy(packet + 3, data, 1024);
  uint16_t crc = 0;
  for (unsigned i=0;i<1024;++i) {
    crc ^= (uint16_t)data[i] << 8;
    for(unsigned j=0;j<8;++j) crc = (crc & 0x8000) ? (uint16_t)((crc<<1)^0x1021) : (uint16_t)(crc<<1);
  }
  packet[1027] = (uint8_t)(crc>>8); packet[1028] = (uint8_t)crc;
  Firmware_Update_Feed(packet, sizeof packet, tick);
  assert(last_control == 6);
}
static void transfer(uint32_t now, Firmware_Update_Drained_t drain) {
  tick = now; reset_count = writes = bytes_written = finalized = drained = 0;
  assert(Firmware_Update_Start(output, &drained, "test", drain) == 0);
  assert(last_control == 'C');
  uint8_t first[1024] = {0}, last[1024];
  FW_UpdateManifest_t manifest = {0}; manifest.image_size = 1024;
  memcpy(first, &manifest, sizeof manifest);
  memset(last, 0x1a, sizeof last); memset(last, 0, 256);
  block(1, first); block(2, last);
  unsigned before = writes;
  block(2, last); assert(writes == before); // Lost ACK retry must not rewrite Flash.
  uint8_t eot = 4;
  Firmware_Update_Feed(&eot, 1, tick);
  assert(finalized == 1 && last_control == 6 && !Firmware_Update_IsActive());
  Firmware_Update_Poll(tick);
  assert(!reset_count);
}
int main(void) {
  transfer(100, ready);
  Firmware_Update_Poll(1099); assert(!reset_count);
  Firmware_Update_Poll(1100); assert(!reset_count);
  Firmware_Update_Poll(31099); assert(!reset_count);
  drained = 1; Firmware_Update_Poll(31099); assert(reset_count == 1);
  puts("PASS Cloud waits for actual output drain; no duplicate Flash writes");
  transfer(100, ready);
  Firmware_Update_Poll(31100); assert(reset_count == 1);
  puts("PASS failed Cloud delivery cannot delay committed candidate reset forever");
  transfer(100, NULL);
  Firmware_Update_Poll(1099); assert(!reset_count);
  Firmware_Update_Poll(1100); assert(reset_count == 1);
  puts("PASS USB/BLE retain original one-second reset delay");
  transfer(UINT32_MAX - 999, ready);
  drained = 1;
  Firmware_Update_Poll(UINT32_MAX); assert(!reset_count);
  Firmware_Update_Poll(0); assert(reset_count == 1);
  puts("PASS reset deadline wrapping to zero still resets correctly");
  reset_count = 0;
  assert(Firmware_Update_Start(output, &drained, "test", ready) == 0);
  Firmware_Update_Cancel(); Firmware_Update_Poll(tick + 60000);
  assert(!reset_count);
  puts("PASS cancelled transfer does not reset");
  return 0;
}
'''

def main():
    with tempfile.TemporaryDirectory(prefix='n6-update-drain-') as temp:
        folder = Path(temp)
        stubs = {
            'debug_uart.h': 'void Debug_UART_Log(const char *, const char *, ...);',
            'main.h': '#include <stdint.h>\nuint32_t HAL_GetTick(void);\nvoid NVIC_SystemReset(void);',
            'tof_app.h': '#include <stdint.h>\nvoid TOF_App_SetMapEnabled(uint32_t);\nvoid TOF_App_SetPaused(uint32_t);',
            'secure_nsc.h': '''#include "firmware_update_format.h"
#define SECURE_FW_UPDATE_OK 0U
uint32_t SECURE_FirmwareUpdateBegin(const FW_UpdateManifest_t *,uint32_t *);
uint32_t SECURE_FirmwareUpdateWrite(uint32_t,const void *,uint32_t);
uint32_t SECURE_FirmwareUpdateFinalize(uint32_t);
uint32_t SECURE_FirmwareUpdateAbort(uint32_t);
uint32_t SECURE_FirmwareUpdateConfirmBoot(void);''',
        }
        for name, data in stubs.items():
            (folder / name).write_text(data, encoding='utf-8')
        (folder / 'test.c').write_text(HARNESS, encoding='utf-8')
        source = ROOT / 'AppliNonSecure/Core/Src'
        includes = [folder, source, ROOT / 'AppliNonSecure/Core/Inc', ROOT / 'Common/Update']
        if os.name == 'nt':
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            vsroot = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            vcvars = Path(vsroot) / 'VC/Auxiliary/Build/vcvars64.bat'
            batch = folder / 'build.cmd'
            include_flags = ' '.join(f'/I"{p}"' for p in includes)
            batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                f'cl /nologo /std:c11 /W3 {include_flags} test.c "{source / "xmodem_receiver.c"}" /Fe:test.exe\n', encoding='utf-8')
            subprocess.run(['cmd.exe', '/d', '/c', str(batch)], cwd=folder, check=True)
            subprocess.run([str(folder / 'test.exe')], cwd=folder, check=True)
        else:
            subprocess.run(['cc', '-std=c11', *sum((['-I', str(p)] for p in includes), []),
                'test.c', str(source / 'xmodem_receiver.c'), '-o', 'test'], cwd=folder, check=True)
            subprocess.run([str(folder / 'test')], cwd=folder, check=True)

if __name__ == '__main__':
    main()
