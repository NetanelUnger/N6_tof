"""Actual XSHUT/DAA functions with mocked HAL boundaries; no board operations.

Checks response-count proof, bounded extra-target handling, failed-step evidence,
and MCU GPIO readback. This does not measure sensor-side electrical signals.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from test_tof_recovery import function

ROOT = Path(__file__).resolve().parents[1]
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { uint32_t EVR; } I3C_TypeDef;
typedef struct { int unused; } GPIO_TypeDef;
typedef struct {
  struct { struct { uint32_t SCLPPLowDuration, SCLI3CHighDuration, SCLODLowDuration; } CtrlBusCharacteristic; } Init;
  I3C_TypeDef *Instance; uint32_t ErrorCode, State;
} I3C_HandleTypeDef;
typedef struct { uint32_t DeviceIndex, TargetDynamicAddr, IBIAck, IBIPayload, CtrlRoleReqAck, CtrlStopTransfer; } I3C_DeviceConfTypeDef;
#define GPIO_PIN_RESET 0
#define GPIO_PIN_SET 1
#define NB_DEVICES 1U
#define I3C_RSTDAA_THEN_ENTDAA 3U
#define DISABLE 0U
#define __HAL_I3C_GET_BCR(x) ((uint32_t)(x))
#define __HAL_I3C_GET_IBI_CAPABLE(x) ((x)&1U)
#define __HAL_I3C_GET_IBI_PAYLOAD(x) ((x)&2U)
#define __HAL_I3C_GET_CR_CAPABLE(x) ((x)&4U)
static I3C_TypeDef peripheral;
static I3C_HandleTypeDef hi3c1;
static struct { struct { void *port; uint32_t pin; } xshut; } device[1];
static uint32_t tick, pin_state, bad_low, bad_high, write_tick;
static int init_calls, init_fail_at, daa_calls, assign_calls, assign_fail, config_calls, config_fail;
static HAL_StatusTypeDef replies[3];
static const char *failed_stage;
static uint32_t HAL_GetTick(void) { return tick; }
static void HAL_Delay(uint32_t ms) { assert(ms == 50); tick += ms; }
static void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint32_t pin, uint32_t value) {
  (void)port; assert(pin == 8); pin_state = value; write_tick = tick;
}
static uint32_t HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint32_t pin) {
  (void)port; assert(pin == 8); assert(tick - write_tick >= 50);
  return pin_state ? (bad_high ? 0 : 1) : (bad_low ? 1 : 0);
}
static void Debug_UART_Log(const char *tag, const char *fmt, ...) {
  if (!strcmp(tag,"I3C-INIT") && !strncmp(fmt,"failed",6)) {
    va_list args; va_start(args,fmt); failed_stage = va_arg(args,const char *); va_end(args);
  }
}
static HAL_StatusTypeDef HAL_I3C_Init(I3C_HandleTypeDef *h) {
  assert(h == &hi3c1); ++init_calls;
  if (init_calls == init_fail_at) return HAL_ERROR;
  h->State = 0; return HAL_OK;
}
static HAL_StatusTypeDef HAL_I3C_Ctrl_DynAddrAssign(I3C_HandleTypeDef *h, uint64_t *payload, uint32_t option, uint32_t timeout) {
  assert(h == &hi3c1 && option == I3C_RSTDAA_THEN_ENTDAA && timeout == 5000);
  assert(daa_calls < 3); if (!daa_calls) assert(*payload == 0);
  *payload = 7; return replies[daa_calls++];
}
static HAL_StatusTypeDef HAL_I3C_Ctrl_SetDynAddr(I3C_HandleTypeDef *h, uint32_t address) {
  assert(h == &hi3c1 && address == 0x52); ++assign_calls;
  return assign_fail ? HAL_ERROR : HAL_OK;
}
static HAL_StatusTypeDef HAL_I3C_Ctrl_ConfigBusDevices(I3C_HandleTypeDef *h, I3C_DeviceConfTypeDef *d, uint32_t count) {
  assert(h == &hi3c1 && count == 1 && d->TargetDynamicAddr == 0x52 && d->DeviceIndex == 1);
  ++config_calls; return config_fail ? HAL_ERROR : HAL_OK;
}
'''
TESTS = r'''
static void fresh(void) {
  memset(&hi3c1,0,sizeof(hi3c1)); hi3c1.Instance = &peripheral;
  init_calls = init_fail_at = daa_calls = assign_calls = assign_fail = config_calls = config_fail = 0;
  replies[0] = HAL_BUSY; replies[1] = HAL_OK; replies[2] = HAL_OK; failed_stage = NULL;
  tick = bad_low = bad_high = 0; device[0].xshut.pin = 8;
}
int main(void) {
  fresh(); assert(platform_power_reset(0) == 0 && tick == 100 && pin_state == 1);
  bad_low = 1; assert(platform_power_reset(0) == -1);
  bad_low = 0; bad_high = 1; assert(platform_power_reset(0) == -1);
  puts("PASS XSHUT low/high delays and MCU readback; mismatched level reports failure");
  fresh(); assert(platform_assign_dynamic_address() == 0);
  assert(init_calls == 2 && daa_calls == 2 && assign_calls == 1 && config_calls == 1);
  assert(hi3c1.Init.CtrlBusCharacteristic.SCLPPLowDuration == 7 && failed_stage == NULL);
  puts("PASS exactly one target assigned before fast timing/device configuration");
  fresh(); replies[0] = HAL_OK; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"no target") && assign_calls == 0 && config_calls == 0);
  fresh(); replies[1] = HAL_BUSY; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"extra target") && daa_calls == 2 && assign_calls == 1);
  puts("PASS absent target cannot become ready; extra-target sequence is bounded");
  fresh(); replies[0] = HAL_TIMEOUT; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"RSTDAA/ENTDAA") && config_calls == 0);
  fresh(); assign_fail = 1; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"set dynamic address") && daa_calls == 1);
  fresh(); init_fail_at = 1; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"slow timing init") && daa_calls == 0);
  fresh(); init_fail_at = 2; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"fast timing init") && config_calls == 0);
  fresh(); config_fail = 1; assert(platform_assign_dynamic_address() == -1);
  assert(!strcmp(failed_stage,"bus device config"));
  puts("PASS original HAL budgets and precise DAA/init/config failure stages retained");
  return 0;
}
'''

def main():
    source = (ROOT / 'AppliNonSecure/Utilities/vl53l9-common/platform/platform_utils.c').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='n6-tof-startup-', ignore_cleanup_errors=True) as temp:
        folder = Path(temp)
        (folder / 'test.c').write_text(PREFIX + '\n'.join(function(source,n) for n in
            ('platform_power_reset','platform_daa_failure','platform_assign_dynamic_address')) + TESTS, encoding='utf-8')
        if os.name == 'nt':
            vswhere = Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            vsroot = subprocess.check_output([str(vswhere),'-latest','-products','*','-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
            vcvars = Path(vsroot) / 'VC/Auxiliary/Build/vcvars64.bat'
            batch = folder / 'build.cmd'
            batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                'cl /nologo /std:c11 /W3 test.c /Fe:test.exe\n',encoding='utf-8')
            subprocess.run(['cmd.exe','/d','/c',str(batch)],cwd=folder,check=True)
            exe = folder / 'test.exe'
        else:
            exe = folder / 'test'
            subprocess.run([shutil.which('cc'),'-std=c11','-Wall','test.c','-o',str(exe)],cwd=folder,check=True)
        subprocess.run([str(exe)],cwd=folder,check=True)

if __name__ == '__main__':
    main()
