"""Run the actual vendor scan event handler with tracked buffer ownership.

The parser/callback boundary is mocked. This verifies lifetime, duplicate
completion and failure-completion behavior; it does not emulate SPI/DMA.
"""
from pathlib import Path
import os
import subprocess
import tempfile
from test_tof_recovery import function

ROOT = Path(__file__).resolve().parents[1]
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { W61_WIFI_EVT_SCAN_DONE_ID=1, W61_WIFI_EVT_CONNECTED_ID,
 W61_WIFI_EVT_GOT_IP_ID, W61_WIFI_EVT_DISCONNECTED_ID, W61_WIFI_EVT_CONNECTING_ID,
 W61_WIFI_EVT_REASON_ID, W61_WIFI_EVT_STA_CONNECTED_ID,
 W61_WIFI_EVT_STA_DISCONNECTED_ID, W61_WIFI_EVT_DIST_STA_IP_ID };
typedef struct { uint32_t marker; } AP;
typedef struct { uint32_t Count; AP *AP; uint32_t More; } Scan;
typedef struct {
 struct { Scan ScanResults; char SSID[33]; int STASettings; } WifiCtx;
 struct { int Net_sta_info; } NetCtx;
 struct { void (*UL_wifi_sta_cb)(uint32_t,void*);
          void (*UL_wifi_ap_cb)(uint32_t,void*); } ulcbs;
} W61_Object_t;
typedef struct { uint8_t MAC[6], IP[4]; } W61_WiFi_CbParamData_t;
static W61_Object_t obj;
static AP scratch[20], copied[20];
static unsigned callbacks, releases, copied_count, status;
static void vPortFree(void *p) { assert(p==scratch); ++releases; }
static void callback(uint32_t event, void *arg) {
 assert(event==W61_WIFI_EVT_SCAN_DONE_ID && !arg);
 assert(obj.WifiCtx.ScanResults.AP==scratch);
 assert(callbacks==releases); /* List is still owned/live throughout callback. */
 ++callbacks;
 if (!status) {
   copied_count=obj.WifiCtx.ScanResults.Count;
   memcpy(copied,scratch,copied_count*sizeof(AP));
 }
}
static void W61_AT_RemoveStrQuotes(char *p) { (void)p; }
static void Parser_StrToMAC(char *p,uint8_t *out) { (void)p;(void)out; }
static void Parser_StrToIP(char *p,uint8_t *out) { (void)p;(void)out; }
static int Parser_CheckValidAddress(uint8_t *p,int n) { (void)p;(void)n;return 0; }
#define WIFI_LOG_ERROR(...) ((void)0)
'''
TESTS = r'''
static void complete(void) {
 uint16_t argc=1; char *argv[]={"SCAN_DONE"};
 W61_WiFi_AT_Event(&obj,&argc,argv);
}
static void prepare(unsigned n) {
 obj.WifiCtx.ScanResults.AP=scratch;
 obj.WifiCtx.ScanResults.Count=n;
 obj.WifiCtx.ScanResults.More=1;
 for (unsigned i=0;i<n;++i) scratch[i].marker=1000+i;
}
static void empty(void) {
 assert(!obj.WifiCtx.ScanResults.AP);
 assert(!obj.WifiCtx.ScanResults.Count && !obj.WifiCtx.ScanResults.More);
}
int main(void) {
 obj.ulcbs.UL_wifi_sta_cb=callback;
 prepare(7); complete(); empty();
 assert(callbacks==1 && releases==1 && copied_count==7);
 assert(copied[6].marker==1006);
 memset(scratch,0,sizeof scratch); assert(copied[6].marker==1006);
 puts("PASS result copied before scratch release, application copy survives");
 complete(); assert(callbacks==1 && releases==1);
 puts("PASS duplicate completion neither calls back nor releases twice");
 prepare(20); complete(); empty();
 assert(callbacks==2 && releases==2 && copied_count==20);
 puts("PASS repeated scan publishes a fresh list and returns all scratch storage");
 prepare(0); complete(); empty(); assert(callbacks==3 && releases==3);
 puts("PASS empty result completion still releases allocated scratch");
 status=1; prepare(3); complete(); empty();
 assert(callbacks==4 && releases==4);
 puts("PASS failed-status completion releases after callback");
 obj.ulcbs.UL_wifi_sta_cb=NULL; prepare(3); complete(); empty();
 assert(callbacks==4 && releases==5);
 puts("PASS absent consumer does not retain scan storage");
 uint16_t argc=1; char *argv[]={"CONNECTED"}; prepare(2);
 W61_WiFi_AT_Event(&obj,&argc,argv);
 assert(obj.WifiCtx.ScanResults.AP==scratch && releases==5);
 puts("PASS unrelated events preserve in-flight scan storage");
 return 0;
}
'''


def run_native(c_source):
    # Windows compiler helpers can briefly retain the temporary directory after
    # cl exits. Cleanup must not hide the executable's assertion result.
    with tempfile.TemporaryDirectory(prefix='n6-scan-lifetime-', ignore_cleanup_errors=True) as temp:
        folder = Path(temp)
        (folder / 'test.c').write_text(c_source, encoding='utf-8')
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
            subprocess.run(['cc', '-std=c11', '-Wall', 'test.c', '-o', 'test'], cwd=folder, check=True)
            subprocess.run([str(folder / 'test')], cwd=folder, check=True)


def main():
    source = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_wifi.c').read_text(encoding='utf-8')
    run_native(PREFIX + function(source, 'W61_WiFi_AT_Event') + TESTS)


if __name__ == '__main__':
    main()
