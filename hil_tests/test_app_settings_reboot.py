"""Actual adapter reboot model: persistent synthetic media, fresh RAM/driver only.

No physical power failure is emulated. Cancellation is injected after each
retired SDK command; a separately modeled fresh driver admits cold cache load.
"""
from test_app_settings_store import production
from test_app_settings_ncp import MOCK
from test_wifi_scan_lifetime import ROOT,run_native

TESTS = r'''
static char snapshot[2][APP_SETTINGS_TEXT_MAX],old_active[APP_SETTINGS_TEXT_MAX];
static uint32_t snapshot_sizes[2];
static void fresh_ram(void){
 assert(scope_begin==scope_end && !settings_gate.owned && !AppSettings_IsBusy());
 /* Model a new MCU boot after all owners have retired; no live fence is cleared. */
 memset(&settings,0,sizeof settings);memset(&settings_buffer,0,sizeof settings_buffer);
 memset(&settings_gate,0,sizeof settings_gate);memset(&settings_status,0,sizeof settings_status);
 settings_ready=settings_present=settings_busy=settings_io_active=settings_cancel_epoch=0;
 settings_expected=settings_started=settings_stage=settings_calls=0;settings_driver=NULL;
 memset(&driver,0,sizeof driver);driver.Modem.handler.cmd_handler_data=&driver;
 cancel_at_scope=cancel_on_yield=0;
}
static void seed(void){
 fresh_ram();assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_ABSENT);
 settings.current.version=1;settings.current.flags=APP_SETTINGS_WIFI_PRESENT;
 settings.current.ssid_length=32;settings.current.password_length=63;
 memset(settings.current.ssid,'s',32);memset(settings.current.password,'p',63);
 char id[65],workspace[65],token[1025];memset(id,'d',64);id[64]=0;
 memset(workspace,'w',64);workspace[64]=0;memset(token,'t',1024);token[1024]=0;
 assert(AppSettings_SaveCloud(id,workspace,token,0)==APP_SETTINGS_OK);
 memset(id,'e',64);assert(AppSettings_SaveCloud(id,workspace,token,0)==APP_SETTINGS_OK);
 assert(settings.current.generation==2 && settings.current.flags==5 && present==3);
 memcpy(snapshot,media,sizeof media);memcpy(snapshot_sizes,media_sizes,sizeof media_sizes);
 memcpy(old_active,media[1],sizeof old_active);
}
int main(void){
 seed();
 for(unsigned boundary=1;boundary<=15;++boundary){
  memcpy(media,snapshot,sizeof media);memcpy(media_sizes,snapshot_sizes,sizeof media_sizes);present=3;
  fresh_ram();assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK && settings.current.generation==2);
  char id[65];memset(id,'f',64);id[64]=0;
  cancel_at_scope=scope_begin+boundary;unsigned start_scope=scope_begin;
  assert(AppSettings_SaveCloud(id,settings.current.workspace_id,settings.current.token,0)==APP_SETTINGS_IO);
  assert(settings.current.generation==2 && !settings.loaded && scope_begin-start_scope==boundary);
  assert(!memcmp(media[1],old_active,sizeof old_active));
  unsigned attempted=scope_begin;
  assert(AppSettings_SaveCloud(id,settings.current.workspace_id,settings.current.token,0)==APP_SETTINGS_IO && scope_begin==attempted);
  fresh_ram();assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);
  assert(settings.current.generation==(boundary>=8?3U:2U));
  assert(settings.current.device_id[0]==(boundary>=8?'f':'e'));
  char ssid[33],password[64],device[65],workspace[65],token[1025];uint32_t desired,enabled;
  assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_OK && desired==0);
  assert(AppSettings_GetCloud(device,workspace,token,&enabled)==APP_SETTINGS_OK && enabled==0);
  assert(settings.current.flags==5 && !memcmp(media[1],old_active,sizeof old_active));
 }
 /* Live true fence blocks inventory, unchanged until modeled fresh init. */
 driver.Modem.handler_data.tx_desynchronized=1;unsigned calls=lists;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_BUSY && lists==calls && driver.Modem.handler_data.tx_desynchronized);
 fresh_ram();assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);
 assert(!legacy_touched && !settings_gate.owned && scope_begin==scope_end);
 puts("PASS 15 retired-command interruption boundaries: inactive delete/create/all writes/size/all verify reads; fresh RAM+driver load chooses only full CRC-valid generation");
 puts("PASS old active bytes exact, unknown blocks retry, disabled desired flags survive cold cache load, live fence remains until fresh modeled driver");
 return 0;
}
'''

def main():
 adapter=(ROOT/'AppliNonSecure/Core/Src/app_settings_ncp.c').read_text()
 for header in ('app_settings_store.h','app_features.h','tx_api.h','w61_at_api.h','w6x_api.h'):
  adapter=adapter.replace('#include "'+header+'"','')
 run_native('#define APP_SETTINGS_WRITES_ENABLED 1\n'+production()+MOCK+adapter+TESTS)
if __name__=='__main__':main()
