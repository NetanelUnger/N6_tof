"""Actual Secure updater/flash-gate host simulation. NOR, CMSE and HAL are mocked."""
from pathlib import Path
from test_xip_boot import ROOT, HARNESS, run_native

MAIN = r'''
#ifndef MAIN_H
#define MAIN_H
#include <stdint.h>
#include <string.h>
typedef struct {unsigned FifoThresholdByte,MemoryMode,MemoryType,MemorySize,ChipSelectHighTimeCycle,FreeRunningClock,ClockMode,WrapSize,ClockPrescaler,SampleShifting,DelayHoldQuarterCycle,ChipSelectBoundary,MaxTran,Refresh,MemorySelect;} XSPI_InitTypeDef;
typedef struct {void *Instance;XSPI_InitTypeDef Init;} XSPI_HandleTypeDef;
typedef struct {unsigned nCSOverride,IOPort,Req2AckTime;} XSPIM_CfgTypeDef;
typedef struct {unsigned CCR,CSAR,CDAR,CLLR;} DMA_Channel_TypeDef;
static DMA_Channel_TypeDef gp[16],hp[16];
#define GPDMA1_Channel0 (&gp[0])
#define GPDMA1_Channel1 (&gp[1])
#define HPDMA1_Channel0 (&hp[0])
#define HPDMA1_Channel1 (&hp[1])
#define DMA_CCR_EN 1
#define __HAL_RCC_GPDMA1_IS_CLK_ENABLED() 1
#define __HAL_RCC_HPDMA1_IS_CLK_ENABLED() 1
static unsigned primask_ns,tick_enabled,clean_calls,icache_calls;
static struct {unsigned AIRCR;} mock_scb;
#define SCB (&mock_scb)
#define SCB_AIRCR_BFHFNMINS_Msk 0x2000U
#define __DSB() ((void)0)
#define __ISB() ((void)0)
#define __WFI() assert(!"unexpected fail-closed mapping failure")
#define __TZ_get_PRIMASK_NS() primask_ns
#define __TZ_set_PRIMASK_NS(x) (primask_ns=(x))
#define SCB_CleanInvalidateDCache() (++clean_calls)
#define SCB_InvalidateICache() (++icache_calls)
#define HAL_ResumeTick() (tick_enabled=1)
#define HAL_SuspendTick() (tick_enabled=0)
#define HAL_GetTick() 1U
#define HAL_XSPI_Init(x) 0
#define HAL_XSPIM_Config(x,y,z) 0
#define HAL_RCCEx_GetPeriphCLKFreq(x) 1U
#define EXTMEM_Init(x,y) 0
#define XSPI2 ((void *)2)
#define HAL_OK 0
static struct {unsigned CR,SR;} mock_pka,mock_rng;
#define PKA (&mock_pka)
#define RNG (&mock_rng)
#define Secure_Trace(x) ((void)0)
#define Secure_TraceHex(x,y) ((void)0)
#endif
'''
CONSTANTS='HAL_XSPI_SINGLE_MEM HAL_XSPI_MEMTYPE_MACRONIX HAL_XSPI_SIZE_512MB HAL_XSPI_FREERUNCLK_DISABLE HAL_XSPI_CLOCK_MODE_0 HAL_XSPI_WRAP_NOT_SUPPORTED HAL_XSPI_SAMPLE_SHIFT_NONE HAL_XSPI_DHQC_ENABLE HAL_XSPI_BONDARYOF_NONE HAL_XSPI_CSSEL_NCS1 HAL_XSPI_CSSEL_OVR_NCS1 HAL_XSPIM_IOPORT_2 HAL_XSPI_TIMEOUT_DEFAULT_VALUE RCC_PERIPHCLK_XSPI2'
MAIN+='\n'+''.join('#define '+n+' 0\n' for n in CONSTANTS.split())
EXTRA=r'''
#include "secure_firmware_update.c"
int32_t FW_Crypto_Init(void) {return 0;}

static void secure_cases(void) {
  void *ram=VirtualAlloc((void *)(uintptr_t)FW_NS_RAM_START,0x100000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
  assert(ram==(void *)(uintptr_t)FW_NS_RAM_START);
  FW_UpdateManifest_t *m=(void *)(uintptr_t)(FW_NS_RAM_START+0x1000);
  unsigned *session=(void *)(uintptr_t)(FW_NS_RAM_START+0x2000);
  unsigned char *image=(void *)(uintptr_t)(FW_NS_RAM_START+0x10000);
  FW_BootRecord_t r;unsigned bank;
  assert(SecureFirmwareUpdate_Init()==0);
  fresh(&r);manifest(m,1,12,2);memcpy(image,(void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_B_OFFSET),2048);
  memset((void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_B_OFFSET),255,FW_SLOT_SIZE);
  unsigned char recovery[2048];memcpy(recovery,(void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_A_OFFSET),2048);
  reject_signature=1;assert(SecureFirmwareUpdate_Begin(m,session)==SECURE_FW_UPDATE_ERROR_AUTHENTICATION);reject_signature=0;
  assert(!erase_calls&&!writes);
  m->flags=1;assert(SecureFirmwareUpdate_Begin(m,session)==SECURE_FW_UPDATE_ERROR_PARAMETER);assert(!erase_calls&&!writes);m->flags=2;
  m->firmware_version=11;assert(SecureFirmwareUpdate_Begin(m,session)==SECURE_FW_UPDATE_ERROR_VERSION);m->firmware_version=12;
  assert(SecureFirmwareUpdate_Begin(m,session)==0);
  assert(SecureFirmwareUpdate_Write(*session,image,512)==0);
  assert(SecureFirmwareUpdate_Abort(*session)==0);
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_CONFIRMED&&r.confirmed_version==11);
  assert(SecureFirmwareUpdate_Finalize(*session)==SECURE_FW_UPDATE_ERROR_STATE);
  puts("PASS actual Secure rejects signature/version/wrong slot before erase; interrupted-transfer abort retains confirmed image");
  assert(SecureFirmwareUpdate_Begin(m,session)==0);
  assert(SecureFirmwareUpdate_Write(*session,image,512)==0);
  assert(SecureFirmwareUpdate_Finalize(*session)==SECURE_FW_UPDATE_ERROR_SIZE);
  puts("PASS actual Secure truncated transfer cannot commit pending metadata");
  assert(SecureFirmwareUpdate_Begin(m,session)==0);
  image[1200]^=1;
  assert(SecureFirmwareUpdate_Write(*session,image,1024)==0);
  assert(SecureFirmwareUpdate_Write(*session,image+1024,1024)==0);
  assert(SecureFirmwareUpdate_Finalize(*session)==SECURE_FW_UPDATE_ERROR_VERIFY);image[1200]^=1;
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_CONFIRMED&&r.confirmed_version==11);
  puts("PASS actual Secure corrupt transfer fails hash without pending commit");
  assert(SecureFirmwareUpdate_Begin(m,session)==0);
  assert(SecureFirmwareUpdate_Write(*session,image,1024)==0);
  assert(SecureFirmwareUpdate_Write(*session,image+1024,1024)==0);
  assert(SecureFirmwareUpdate_Finalize(*session)==0);
  assert(!memcmp(recovery,(void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_A_OFFSET),sizeof recovery));
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_B_OFFSET);
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_TRIAL);
  assert(SecureFirmwareUpdate_ConfirmBoot()==0);
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_CONFIRMED&&r.confirmed_version==12&&r.pending_version==11&&r.pending_slot==0);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_B_OFFSET);
  puts("PASS actual Secure write/readback/finalize -> actual FSBL trial -> actual Secure confirmation -> persistent boot selection");
  SecureFirmwareUpdate_SetExecutionVector(0x70280400);
  guard_mapping_checks=mapped=1;
  mock_scb.AIRCR=0x2000U;
  assert(SecureFirmwareUpdate_EnterFlash()==SECURE_FW_UPDATE_ERROR_STATE);
  mock_scb.AIRCR=0;
  assert(SecureFirmwareUpdate_EnterFlash()==0&&primask_ns==1&&tick_enabled==1);
  assert(SecureFirmwareUpdate_EnterFlash()==SECURE_FW_UPDATE_ERROR_STATE);
  SecureFirmwareUpdate_LeaveFlash();assert(primask_ns==0&&tick_enabled==0&&clean_calls==2&&icache_calls==1&&mapped==1&&disable_count==1&&enable_count==1);
  gp[5].CCR=1;gp[5].CSAR=0x70280000;
  assert(SecureFirmwareUpdate_EnterFlash()==SECURE_FW_UPDATE_ERROR_STATE&&primask_ns==0&&!tick_enabled);memset(gp,0,sizeof gp);
  hp[1].CCR=1;hp[1].CLLR=1;
  assert(SecureFirmwareUpdate_EnterFlash()==SECURE_FW_UPDATE_ERROR_STATE&&primask_ns==0&&!tick_enabled);memset(hp,0,sizeof hp);
  gp[5].CCR=1;gp[5].CSAR=0x24102000;gp[5].CDAR=0x40000000;primask_ns=1;
  assert(SecureFirmwareUpdate_EnterFlash()==0);SecureFirmwareUpdate_LeaveFlash();assert(primask_ns==1);
  puts("PASS actual XIP gate preserves NS mask, keeps Secure tick, rejects reentry/external DMA/linked DMA and permits SRAM DMA");
  VirtualFree(ram,0,MEM_RELEASE);
}
'''

def main():
    # Reuse the actual-FSBL harness, extending the NOR mock for inactive-slot erases.
    harness=HARNESS.replace('#include "firmware_boot.c"','#include "main.h"\n#include "firmware_boot.c"\nstatic void secure_cases(void);')
    harness=harness.replace('assert(offset==FW_METADATA_0_OFFSET||offset==FW_METADATA_1_OFFSET);',
        'assert(offset==FW_METADATA_0_OFFSET||offset==FW_METADATA_1_OFFSET||(offset>=FW_SLOT_A_OFFSET&&offset<FW_SLOT_B_OFFSET+FW_SLOT_SIZE));')
    harness=harness.replace('  VirtualFree(mapped,0,MEM_RELEASE);','  secure_cases();\n  VirtualFree(mapped,0,MEM_RELEASE);')
    harness=harness.replace('static unsigned erase_calls, writes, fail_write, reject_signature;',
        'static unsigned erase_calls, writes, fail_write, reject_signature, guard_mapping_checks, mapped, disable_count, enable_count;')
    harness=harness.replace('int EXTMEM_MemoryMappedMode(unsigned a,unsigned b) {(void)a;(void)b;return 0;}',
        'int EXTMEM_MemoryMappedMode(unsigned a,unsigned b) {(void)a; if(guard_mapping_checks){assert(primask_ns==1&&tick_enabled==1);mapped=b;if(b)++enable_count;else ++disable_count;}return 0;}')
    harness=harness.replace('PASS all 21 actual-C host cases (PKA/NOR mocked)',
        'PASS 21 boot/vector cases plus 5 actual Secure scenario groups (PKA/NOR/CMSE/HAL mocked)')
    harness+='\n'+EXTRA
    cmse='''#include <stddef.h>\n#define CMSE_NONSECURE 1\n#define CMSE_MPU_READ 2\n#define CMSE_MPU_READWRITE 4\n#define cmse_check_address_range(p,n,f) (p)\n'''
    run_native(harness,{'main.h':MAIN,'arm_cmse.h':cmse},[ROOT/'AppliSecure/Core/Src',ROOT/'AppliSecure/Core/Inc',ROOT/'Secure_nsclib'])
if __name__=='__main__':main()
