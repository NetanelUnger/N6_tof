"""Approved RAM preparation and first pairing commit, actual codec/store/adapter.

Only synthetic media. No board, real SSID/password/token or pairing exchange.
"""
from test_app_settings_store import production
from test_app_settings_ncp import MOCK
from test_wifi_scan_lifetime import ROOT, run_native
import zlib

TESTS = r'''
static void reset_legacy(void){
 assert(scope_begin==scope_end && !settings_gate.owned);
 memset(media,0,sizeof media);memset(media_sizes,0,sizeof media_sizes);
 present=0;old_file=1;cost=1;list_error=read_fail=write_fail=full_list=0;
 cancel_on_yield=cancel_at_scope=0;
 driver.Modem.handler.cmd_handler_data=&driver;
 driver.Modem.handler_data.tx_desynchronized=driver.Modem.handler_data.dns_drain_active=driver.Modem.notify_phase=0;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_LEGACY);
}
static void clean(void){
 assert(scope_begin==scope_end && !settings_gate.owned && !settings_busy && !settings_io_active && !legacy_touched);
 for(unsigned i=0;i<sizeof settings.pending;++i)assert(!((unsigned char*)&settings.pending)[i]);
 for(unsigned i=0;i<APP_SETTINGS_TEXT_MAX;++i)assert(!settings.text[i]);
 assert(old_file);
}
int main(void){
 reset_legacy();unsigned before=mutations;
#if !APP_SETTINGS_TRANSITION_ENABLED || !APP_SETTINGS_WRITES_ENABLED
 assert(AppSettings_PrepareCloudTransition("synthetic-ssid",1)==APP_SETTINGS_READ_ONLY && mutations==before);
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==
   (APP_SETTINGS_WRITES_ENABLED?APP_SETTINGS_LEGACY:APP_SETTINGS_READ_ONLY));
 assert(mutations==before);clean();
 puts("PASS default writesOFF/transitionOFF cannot prepare or bypass legacy storage");
#else
 assert(AppSettings_PrepareCloudTransition(NULL,1)==APP_SETTINGS_INVALID);
 assert(AppSettings_PrepareCloudTransition("s",2)==APP_SETTINGS_INVALID);
 assert(AppSettings_PrepareCloudTransition("bad\"ssid",1)==APP_SETTINGS_INVALID && mutations==before);clean();
 assert(AppSettings_PrepareCloudTransition("synthetic-ssid",1)==APP_SETTINGS_OK && mutations==before && !present);
 assert(settings.result==APP_SETTINGS_ABSENT && settings.loaded && settings.active_slot==-1);
 assert(settings.current.flags==19 && !settings.current.password_length && !settings.current.token_length);
 assert(AppSettings_SaveWifi("s","p")==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_DisconnectWifi(1)==APP_SETTINGS_READ_ONLY && AppSettings_ClearCloud()==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_PrepareCloudTransition("other",1)==APP_SETTINGS_UNAVAILABLE);
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_OK && present==1 && settings.current.flags==31);
 assert(settings.current.generation==1 && !settings_transition_armed && AppSettings_WifiUsesReference());clean();
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK && AppSettings_WifiUsesReference());
 char ssid[33],password[64];uint32_t desired=0;
 assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_OK && desired && !strcmp(ssid,"synthetic-ssid") && !password[0]);
 puts("PASS explicit preparation is RAM-only; first verified pairing commit includes reference/desired/Cloud, original file untouched");
 before=mutations;assert(!AppSettings_WritesEnabled());
 assert(AppSettings_DisconnectWifi(0)==APP_SETTINGS_READ_ONLY && AppSettings_WifiUsesReference());
 assert(AppSettings_DisconnectWifi(1)==APP_SETTINGS_READ_ONLY && AppSettings_SaveWifi("open","")==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_READ_ONLY && mutations==before);
 puts("PASS one-shot candidate locks every mutation after first commit and after a fresh load; reset validation can use a writesOFF reader");
 reset_legacy();before=mutations;
 assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_OK);
 present=2;media_sizes[1]=3;memcpy(media[1],"old",3);
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_IO && mutations==before);
 assert(present==2 && media_sizes[1]==3 && !memcmp(media[1],"old",3));clean();
 reset_legacy();before=mutations;
 assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_OK);AppSettings_Cancel();
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_IO && mutations==before);clean();
 reset_legacy();before=mutations;cancel_on_yield=1;
 assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_IO && mutations==before);clean();
 reset_legacy();assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_OK);
 before=mutations;driver.Modem.handler_data.tx_desynchronized=1;
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_IO && mutations==before);
 assert(driver.Modem.handler_data.tx_desynchronized);clean();
 puts("PASS intervening managed file/cancellation/true fence fail closed before create; no overwritten unknown file or fence clearing");
 reset_legacy();assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_OK);write_fail=1;
 assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_IO && present==1 && !settings.loaded);
 before=mutations;assert(AppSettings_SaveCloud("d","w","synthetic-token",1)==APP_SETTINGS_IO && mutations==before);
 assert(AppSettings_PrepareCloudTransition("s",1)==APP_SETTINGS_UNAVAILABLE);
 write_fail=0;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_CORRUPT);clean();
 puts("PASS partial first save preserves legacy, blocks retry/re-arm, requires explicit readback/arbitration; no automatic cleanup");
 reset_legacy();char maximum_ssid[33],id[65],token[1025];
 memset(maximum_ssid,'s',32);maximum_ssid[32]=0;memset(id,'d',64);id[64]=0;memset(token,'t',1024);token[1024]=0;
 assert(AppSettings_PrepareCloudTransition(maximum_ssid,1)==APP_SETTINGS_OK);
 cost=530;uint32_t started=now;unsigned command_before=scope_begin;
 assert(AppSettings_SaveCloud(id,id,token,1)==APP_SETTINGS_OK);
 assert(settings_calls==13 && scope_begin-command_before==13 && now-started<APP_SETTINGS_OPERATION_MS);
 assert(settings.current.length==2435 && settings.current.flags==31 && !settings.current.password_length);clean();
 puts("PASS maximum reference+pairing first commit: one inventory+create+five writes+size+five reads, immutable13250ms/15 commands");
 for(unsigned boundary=1;boundary<=13;++boundary){
  reset_legacy();assert(AppSettings_PrepareCloudTransition(maximum_ssid,1)==APP_SETTINGS_OK);
  cancel_at_scope=scope_begin+boundary;
  assert(AppSettings_SaveCloud(id,id,token,1)==APP_SETTINGS_IO && !settings.loaded && !settings_transition_armed);
  before=mutations;assert(AppSettings_SaveCloud(id,id,token,1)==APP_SETTINGS_IO && mutations==before);clean();
 }
 puts("PASS all13 retired-command cancellation boundaries preserve legacy/unknown-outcome policy; host model, not Flash durability");
#endif
 return 0;
}
'''

def main():
    adapter=(ROOT/'AppliNonSecure/Core/Src/app_settings_ncp.c').read_text()
    for name in ('app_settings_store.h','app_features.h','tx_api.h','w61_at_api.h','w6x_api.h'):
        adapter=adapter.replace(f'#include "{name}"','')
    for writes,transition in ((0,0),(1,0),(0,1),(1,1)):
        run_native(f'#define APP_SETTINGS_WRITES_ENABLED {writes}\n#define APP_SETTINGS_TRANSITION_ENABLED {transition}\n'+production()+MOCK+adapter+TESTS)

def check_rollback_reader():
    folder=ROOT/'.local-dependencies/diagnostics/settings-transition-20261011'
    paths=('app_settings.h.before','app_settings_store.h.before','app_settings_format.c.before','app_settings_store.c.before')
    if not all((folder/f).exists() for f in paths):
        return  # exact prior-reader evidence is local, not a regression dependency
    older='\n'.join((folder/f).read_text().replace('#include "app_settings.h"','').replace('#include "app_settings_store.h"','') for f in paths)
    fields=(b'synthetic-ssid',b'',b'd',b'w',b'synthetic-token')
    payload=''.join(f'{len(f):04X}:'+f.hex().upper()+'|' for f in fields)
    size=28+len(payload)+9
    text=f'N6S1|00000001|{size:04X}|0000001F|'+payload
    text+=f'{zlib.crc32(text.encode()):08X}!'
    run_native(older+f'''
#include <assert.h>
#include <stdio.h>
int main(void){{AppSettings_Record r;
 assert(AppSettings_Decode("{text}",{len(text)},&r)==APP_SETTINGS_UNSUPPORTED);
 puts("PASS exact prior reader rejects reference flag as UNSUPPORTED; rollback cannot mistake reference for open Wi-Fi");return 0;}}
''')

if __name__=='__main__':
    main()
    check_rollback_reader()
