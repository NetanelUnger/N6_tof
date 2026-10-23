"""Actual C supervisor/policy with mocked IWDG/RTOS; no hardware access.

Includes starvation, startup bound, latch, expiry, updater guard and tick wrap.
Hardware reset timing and external peripheral recovery require separate HIL.
"""
from pathlib import Path
import os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdint.h>
#include <stdarg.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "n6_watchdog_policy.h"
#define N6_WATCHDOG_ENABLED 1
#define APP_USB_CLI_ENABLED 1
#define APP_GC9A01_DISPLAY_ENABLED 1
#define APP_ST67W6X_ENABLED 1
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1
#define APP_ST67W6X_BLE_GATT_ENABLED 1
#define APP_ST67W6X_CLOUD_RELAY_ENABLED 1
#define TX_TIMER_TICKS_PER_SECOND 100U
#define __ATOMIC_RELAXED 0
#define __ATOMIC_ACQUIRE 0
#define __ATOMIC_RELEASE 0
#define __atomic_store_n(p,v,m) (*(p)=(v))
#define __atomic_load_n(p,m) (*(p))
#define __atomic_add_fetch(p,v,m) (*(p)+=(v))
#define LL_IWDG_PRESCALER_256 6
#define IWDG_SR_PVU 1
#define IWDG_SR_RVU 2
#define IWDG_SR_WVU 4
#define IWDG_SR_EWU 8
#define IWDG_ICR_EWIC 1
#define RCC_RSR_IWDGRSTF (1U<<26)
typedef struct { uint32_t SR,EWCR,ICR; } IWDG_TypeDef;
static IWDG_TypeDef mock_iwdg;
#define IWDG (&mock_iwdg)
static struct {uint32_t RSR;} mock_rcc;
#define RCC (&mock_rcc)
static uint32_t tick,irq,busy,feeds,enabled,confirmed,sleeps,mode,limit,flushed,logs;
static jmp_buf escape;
static uint32_t tx_time_get(void){return tick;}
static uint32_t __get_IPSR(void){return irq;}
static uint32_t Firmware_Update_IsBusy(void){return busy;}
static void Firmware_Update_ConfirmBoot(void){confirmed++;}
static int Debug_UART_Flush(uint32_t ms){assert(ms==1000);flushed++;return 0;}
static void Debug_UART_Log(const char *tag,const char *fmt,...){(void)tag;(void)fmt;logs++;}
static void LL_IWDG_Enable(IWDG_TypeDef *p){assert(p==IWDG);enabled++;}
static void LL_IWDG_EnableWriteAccess(IWDG_TypeDef *p){assert(p==IWDG);}
static void LL_IWDG_SetPrescaler(IWDG_TypeDef *p,uint32_t v){assert(p==IWDG&&v==6);}
static void LL_IWDG_SetReloadCounter(IWDG_TypeDef *p,uint32_t v){assert(p==IWDG&&v==1999);}
static void LL_IWDG_SetWindow(IWDG_TypeDef *p,uint32_t v){assert(p==IWDG&&v==4095);}
static void LL_IWDG_ReloadCounter(IWDG_TypeDef *p){assert(p==IWDG);feeds++;}
#define __HAL_RCC_CLEAR_RESET_FLAGS() (mock_rcc.RSR=0)
#define __NOP() longjmp(escape,2)
static void tx_thread_sleep(uint32_t ticks);
#include "n6_watchdog_impl.inc"
static void tx_thread_sleep(uint32_t ticks){
  tick+=ticks;sleeps++;
  if(sleeps>=limit)longjmp(escape,1);
  if(mode==1 || mode==2 || mode==4){
    for(unsigned i=0;i<N6H_COUNT;i++)
      if(mode!=2 || i!=N6H_UART_CONTROL || sleeps>100)N6H_Beat(i);
  }
  if(mode==4 && sleeps==5)n6h_supervisor_fault=1;
}
static void fresh(void){
  memset(n6h_progress,0,sizeof n6h_progress);memset(&mock_iwdg,0,sizeof mock_iwdg);
  n6h_started=n6h_required=n6h_failure=n6h_ready=n6h_supervisor_fault=0;
  n6h_arm=n6h_armed_at=tick=irq=busy=feeds=enabled=confirmed=sleeps=flushed=logs=0;
  mode=1;limit=100;
}
int main(void){
  fresh();N6H_Progress p[N6H_COUNT]={{0}};uint32_t b[N6H_COUNT];
  for(unsigned i=0;i<N6H_COUNT;i++){p[i].count=1;p[i].last=0xfffffff0U;b[i]=32;}
  assert(!N6H_BadMask(p,b,511,0x10));assert(N6H_BadMask(p,b,511,0x11)==511);
  p[3].count=0;assert(N6H_BadMask(p,b,1U<<3,0x10)==(1U<<3));
  assert(N6H_ArmValid(1,499,0,500,1,0));assert(!N6H_ArmValid(1,500,0,500,1,0));
  assert(!N6H_ArmValid(1,1,0,500,1,1));assert(!N6H_ArmValid(1,1,0,500,0,0));
  assert(N6H_ArmValid(2,0x10,0xfffffff0U,500,1,0));
  puts("PASS policy boundary/wrap/missing-task/busy/unhealthy/expiry");
  fresh();irq=1;N6H_Beat(0);assert(!n6h_progress[0].count);irq=0;N6H_Beat(0);assert(n6h_progress[0].count==1);
  puts("PASS ISR heartbeat cannot certify task progress");
  fresh();N6H_Beat(N6H_COUNT);assert(!n6h_progress[0].count);
  for(unsigned n=0;n<100;n++)N6H_Beat(0);assert(n6h_progress[0].count==2);
  puts("PASS owner heartbeat seen-count saturates; invalid task index ignored");
  fresh();if(!setjmp(escape))N6H_Run();assert(enabled==1&&feeds>90&&confirmed==1&&!n6h_failure);
  puts("PASS healthy progress feeds only supervisor; confirms once");
  fresh();mode=2;limit=150;for(unsigned i=0;i<N6H_COUNT;i++){N6H_Beat(i);N6H_Beat(i);}
  if(!setjmp(escape))N6H_Run();assert(n6h_failure==(1U<<N6H_UART_CONTROL));assert(feeds>=40&&feeds<=42);
  assert(n6h_progress[N6H_UART_CONTROL].last>1000);
  puts("PASS stuck UART task stops feed and remains latched after recovery");
  fresh();mode=3;limit=500;if(!setjmp(escape))N6H_Run();assert(n6h_failure==511&&feeds==450&&confirmed==0);
  puts("PASS startup grace bounded45s; missing tasks never confirm");
  fresh();mode=4;limit=100;int stop=setjmp(escape);if(!stop)N6H_Run();assert(stop==2&&feeds==5);
  puts("PASS supervisor tight loop cannot feed hardware watchdog");
  fresh();mock_iwdg.SR=1;limit=200;if(!setjmp(escape))N6H_Run();assert(!feeds&&!confirmed);
  puts("PASS IWDG register sync failure never feeds/confirms");
  fresh();assert(N6H_UartCommand('W')==1&&!flushed);n6h_ready=1;
  N6H_UartCommand('w');tick=500;N6H_UartCommand('W');assert(!flushed);
  N6H_UartCommand('w');busy=1;N6H_UartCommand('W');assert(!flushed&&!n6h_arm);busy=0;
  N6H_UartCommand('w');N6H_UartCommand('x');N6H_UartCommand('W');assert(!flushed);
  N6H_UartCommand('w');N6H_UartCommand('\r');stop=setjmp(escape);if(!stop)N6H_UartCommand('W');
  assert(stop==2&&flushed==1&&!n6h_arm);
  puts("PASS W requires fresh arm/no-update; unrelated input cancels; consumes arm before hang");
  fresh();n6h_ready=1;N6H_UartCommand('s');N6H_UartCommand('W');assert(n6h_supervisor_fault&&flushed==1);
  puts("PASS separate explicitly armed supervisor fault target");
  puts("PASS 10 actual-C watchdog test groups; IWDG/RTOS mocked, no hardware reset claim");
}
'''
def main():
    with tempfile.TemporaryDirectory(prefix='n6-wdt-') as tmp:
        p=Path(tmp);(p/'test.c').write_text(C);(p/'stm32n6xx_ll_iwdg.h').write_text('/* mocked by harness */\n')
        vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        vs=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
        flags=' '.join('/I"'+str(x)+'"' for x in [p,ROOT/'AppliNonSecure/Core/Inc',ROOT/'AppliNonSecure/Core/Src'])
        (p/'build.cmd').write_text('@echo off\ncall "'+str(Path(vs)/'VC/Auxiliary/Build/vcvars64.bat')+'" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W3 '+flags+' test.c /Fe:test.exe\n')
        subprocess.run(['cmd.exe','/d','/c',str(p/'build.cmd')],cwd=p,check=True)
        subprocess.run([str(p/'test.exe')],cwd=p,check=True)
if __name__=='__main__':main()
