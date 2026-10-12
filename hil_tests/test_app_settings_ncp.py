"""Actual static NCP adapter and cross-owner merges, SDK/RTOS boundary mocked."""
from test_app_settings_store import production
from test_wifi_scan_lifetime import ROOT,run_native

MOCK = r'''
#include <assert.h>
#include <stdio.h>
#define APP_ST67W6X_ENABLED 1
#define APP_ST67W6X_WIFI_SERVICES_ENABLED 1
#define TX_SUCCESS 0
#define TX_NO_WAIT 0
#define TX_INHERIT 1
#define TX_INT_DISABLE 1
typedef unsigned UINT;
typedef struct {unsigned owned;} TX_MUTEX;
static unsigned mutex_fail,scope_begin,scope_end,elapsed,cost=1,mutations,lists;
static uint32_t now,call_budget;static const volatile uint32_t *call_epoch;static uint32_t call_expected;
static unsigned cancel_on_yield,foreign_release,yields,cancel_at_scope;
static uint32_t HAL_GetTick(void){return now;}
static void *xTaskGetCurrentTaskHandle(void){return (void*)2;}
typedef int W61_Status_t;
static UINT tx_interrupt_control(UINT v){return v;}
static UINT tx_mutex_create(TX_MUTEX*m,char*n,unsigned inherit){(void)n;assert(inherit==1);m->owned=0;return 0;}
static UINT tx_mutex_get(TX_MUTEX*m,unsigned wait){assert(!wait);if(mutex_fail || m->owned)return 1;m->owned=1;return 0;}
static UINT tx_mutex_put(TX_MUTEX*m){assert(m->owned);m->owned=0;return 0;}
typedef struct {struct {struct {void*cmd_handler_data;}handler;
 struct {unsigned tx_desynchronized,dns_drain_active;void*budget_owner;}handler_data;unsigned notify_phase;}Modem;}W61_Object_t;
static W61_Object_t driver;
static W61_Object_t *W61_ObjGet(void){return &driver;}
#define W61_SYS_FS_FILENAME_SIZE 32
#define W61_SYS_FS_MAX_FILES 32
#define W61_STATUS_OK 0
typedef struct {char filename[32][32];unsigned nb_files;}W61_FS_FilesList_t;
static char media[2][APP_SETTINGS_TEXT_MAX];static uint32_t media_sizes[2],present,old_file;
static unsigned list_error,full_list,read_fail,write_fail,legacy_touched;
static void W6X_Net_RequestScopeBegin(unsigned budget,const volatile uint32_t*p,unsigned g){assert(budget && budget<=2000 && p && scope_begin==scope_end);++scope_begin;elapsed=0;call_budget=budget;call_epoch=p;call_expected=g;driver.Modem.handler_data.budget_owner=xTaskGetCurrentTaskHandle();}
static void W6X_Net_RequestScopeEnd(void){assert(scope_begin==scope_end+1);++scope_end;driver.Modem.handler_data.budget_owner=NULL;}
static void tx_thread_sleep(unsigned ticks){assert(ticks==1);now+=10;++yields;if(cancel_on_yield || (cancel_at_scope && scope_end==cancel_at_scope)){cancel_at_scope=0;++*(volatile uint32_t*)call_epoch;cancel_on_yield=0;}if(foreign_release){driver.Modem.handler_data.budget_owner=NULL;driver.Modem.notify_phase=0;foreign_release=0;}}
static int step(void){assert(scope_begin==scope_end+1);elapsed+=cost;now+=cost;return elapsed>call_budget || *call_epoch!=call_expected;}
static unsigned slot(char*n){if(!strcmp(n,APP_SETTINGS_SLOT_0))return 0;
 if(!strcmp(n,APP_SETTINGS_SLOT_1))return 1;++legacy_touched;assert(0);return 0;}
static int W61_FS_ListFiles(W61_Object_t*d,W61_FS_FilesList_t*l){assert(d==&driver);++lists;
 if(step() || list_error)return 1;l->nb_files=0;
 for(unsigned i=0;i<2;++i)if(present&(1U<<i))strcpy(l->filename[l->nb_files++],i?APP_SETTINGS_SLOT_1:APP_SETTINGS_SLOT_0);
 if(old_file)strcpy(l->filename[l->nb_files++],"n6cloud.cfg");if(full_list){while(l->nb_files<32){snprintf(l->filename[l->nb_files],32,"synthetic%02u",l->nb_files);++l->nb_files;}if(full_list==2)l->nb_files=33;}return 0;}
static int W61_FS_GetSizeFile(W61_Object_t*d,char*n,uint32_t*s){assert(d==&driver);if(step())return 1;*s=media_sizes[slot(n)];return 0;}
static int W61_FS_ReadFile(W61_Object_t*d,char*n,uint32_t offset,void*out,uint32_t size){
 assert(d==&driver && size<=APP_SETTINGS_IO_CHUNK);unsigned s=slot(n);assert(offset+size<=media_sizes[s]);
 if(step() || read_fail)return 1;memcpy(out,media[s]+offset,size);return 0;}
static int W61_FS_DeleteFile(W61_Object_t*d,char*n){assert(APP_SETTINGS_WRITES_ENABLED && d==&driver);++mutations;
 if(step())return 1;unsigned s=slot(n);present &= ~(1U<<s);media_sizes[s]=0;return 0;}
static int W61_FS_CreateFile(W61_Object_t*d,char*n){assert(APP_SETTINGS_WRITES_ENABLED && d==&driver);++mutations;
 if(step())return 1;unsigned s=slot(n);assert(!(present&(1U<<s)));present|=1U<<s;media_sizes[s]=0;return 0;}
static int W61_FS_WriteFile(W61_Object_t*d,char*n,uint32_t offset,uint8_t*data,uint32_t size){
 assert(APP_SETTINGS_WRITES_ENABLED && d==&driver && size<=APP_SETTINGS_IO_CHUNK);++mutations;unsigned s=slot(n);
 if(step() || write_fail)return 1;assert(offset==media_sizes[s]);memcpy(media[s]+offset,data,size);media_sizes[s]+=size;return 0;}
'''
TESTS = r'''
static void scratch(void){assert(!settings_gate.owned && !AppSettings_IsBusy() && scope_begin==scope_end);
 for(unsigned i=0;i<sizeof settings.pending;++i)assert(!((unsigned char*)&settings.pending)[i]);
 for(unsigned i=0;i<APP_SETTINGS_TEXT_MAX;++i)assert(!settings.text[i]);assert(!legacy_touched);}
int main(void){
 char ssid[33],password[64],device[65],workspace[65],token[1025];uint32_t desired,enabled;
 AppSettings_Status status;AppSettings_GetStatus(&status);assert(status.result==APP_SETTINGS_UNAVAILABLE);
 driver.Modem.handler.cmd_handler_data=&driver;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_ABSENT);scratch();
#if APP_SETTINGS_WRITES_ENABLED
 assert(AppSettings_SaveWifi("synthetic-ssid","synthetic-pass")==APP_SETTINGS_OK);scratch();
 assert(AppSettings_SaveCloud("device","workspace","synthetic-token",1)==APP_SETTINGS_OK);scratch();
 assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_OK && desired && !strcmp(password,"synthetic-pass"));
 assert(AppSettings_GetCloud(device,workspace,token,&enabled)==APP_SETTINGS_OK && enabled && !strcmp(token,"synthetic-token"));
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);scratch();
 assert(AppSettings_SaveWifi("second-ssid","")==APP_SETTINGS_OK);
 assert(AppSettings_GetCloud(device,workspace,token,&enabled)==APP_SETTINGS_OK && enabled && !strcmp(token,"synthetic-token"));
 assert(AppSettings_DisconnectWifi(0)==APP_SETTINGS_OK);
 assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_OK && !desired && !password[0]);
 assert(AppSettings_ClearCloud()==APP_SETTINGS_OK && AppSettings_GetCloud(device,workspace,token,&enabled)==APP_SETTINGS_ABSENT);
 for(unsigned i=0;i<sizeof token;++i)assert(!token[i]);
 assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_OK && !strcmp(ssid,"second-ssid"));
 assert(AppSettings_DisconnectWifi(1)==APP_SETTINGS_OK && AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_ABSENT);
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK && !settings.current.flags);scratch();
 unsigned before=mutations;mutex_fail=1;assert(AppSettings_SaveWifi("s","p")==APP_SETTINGS_BUSY && mutations==before);
 memset(password,0x5a,sizeof password);assert(AppSettings_GetWifi(ssid,password,&desired)==APP_SETTINGS_BUSY);
 for(unsigned i=0;i<sizeof password;++i)assert(!password[i]);mutex_fail=0;
 assert(AppSettings_SaveWifi("s","bad\n")==APP_SETTINGS_INVALID && mutations==before);scratch();
 write_fail=1;assert(AppSettings_SaveWifi("s","p")==APP_SETTINGS_IO);before=mutations;
 assert(AppSettings_SaveCloud("d","w","t",1)==APP_SETTINGS_IO && mutations==before);write_fail=0;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);scratch();
 cost=530;
 char max_ssid[33],max_pass[64],max_id[65],max_token[1025];
 memset(max_ssid,'s',32);max_ssid[32]=0;memset(max_pass,'p',63);max_pass[63]=0;
 memset(max_id,'d',64);max_id[64]=0;memset(max_token,'t',1024);max_token[1024]=0;
 assert(AppSettings_SaveWifi(max_ssid,max_pass)==APP_SETTINGS_OK);
 uint32_t before_time=now;unsigned before_scope=scope_begin;
 assert(AppSettings_SaveCloud(max_id,max_id,max_token,1)==APP_SETTINGS_OK);
 assert(settings.current.length==2561 && settings_calls==15 && scope_begin-before_scope==15);
 assert(now-before_time==15*(530+10) && now-before_time<APP_SETTINGS_OPERATION_MS);scratch();
 full_list=1;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK && settings_calls<=15);scratch();full_list=0;
 puts("PASS complete32-file inventory with managed records loads; impossible count33 fails closed");
 puts("PASS actual maximum2561 save/readback/commit and two-slot reload:530ms commands,15 steps,immutable13250ms bound");
 uint32_t generation=settings.current.generation;cancel_on_yield=1;
 assert(AppSettings_SaveWifi("cancel","p")==APP_SETTINGS_IO && !settings.loaded && settings.current.generation==generation);scratch();
 unsigned cancelled_writes=mutations;assert(AppSettings_SaveWifi("cancel","p")==APP_SETTINGS_IO && mutations==cancelled_writes);
 cost=1;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);scratch();
 driver.Modem.handler_data.budget_owner=(void*)3;foreign_release=1;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK && !foreign_release);scratch();
 generation=settings.current.generation;cancel_at_scope=scope_begin+((settings_present & (settings.active_slot==0?2U:1U))?15U:14U);
 assert(AppSettings_SaveCloud(max_id,max_id,max_token,1)==APP_SETTINGS_IO && settings.current.generation==generation && !settings.loaded);scratch();
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);scratch();
 puts("PASS cancellation after final readback cannot publish; full reload alone arbitrates complete-but-unconfirmed file");
 puts("PASS cancellation between commands retires borrowed state and blocks retry; foreign scope retires before claim");
 now=0xFFFFFF00u;cost=530;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_OK);scratch();
 cost=1500;assert(AppSettings_SaveCloud(max_id,max_id,max_token,1)==APP_SETTINGS_IO && !settings.loaded);scratch();
 puts("PASS clock wrap; individually timely commands still fail the immutable whole-operation limit");
 cost=1;
 puts("PASS actual NCP adapter: interleaved Wi-Fi/Cloud merges, reload, open network, desired cancel/forget/tombstone");
 puts("PASS no legacy file touched; busy/invalid inputs issue zero writes; unknown commit blocks another write");
#else
 assert(AppSettings_SaveWifi("synthetic-ssid","synthetic-pass")==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_SaveCloud("d","w","t",1)==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_DisconnectWifi(1)==APP_SETTINGS_READ_ONLY);
 assert(AppSettings_ClearCloud()==APP_SETTINGS_READ_ONLY && !mutations);scratch();
 puts("PASS shipping write policy blocks all four persistent operations before any SDK mutation");
#endif
 present=0;old_file=1;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_LEGACY);
 unsigned count=mutations;
 assert(AppSettings_SaveWifi("s","p")== (APP_SETTINGS_WRITES_ENABLED?APP_SETTINGS_LEGACY:APP_SETTINGS_READ_ONLY));
 assert(mutations==count);scratch();
 old_file=0;full_list=1;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_ABSENT);scratch();
 full_list=2;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_IO);full_list=0;
 list_error=1;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_IO);list_error=0;
 assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_ABSENT);scratch();
 for(unsigned i=0;i<3;++i){unsigned before=lists;
  driver.Modem.handler_data.tx_desynchronized=i==0;driver.Modem.handler_data.dns_drain_active=i==1;driver.Modem.notify_phase=i==2;
  assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_BUSY && lists==before);scratch();}
 driver.Modem.handler_data.tx_desynchronized=driver.Modem.handler_data.dns_drain_active=driver.Modem.notify_phase=0;
 cost=2001;assert(AppSettings_InitializeAndLoad()==APP_SETTINGS_IO && scope_begin==scope_end);scratch();
 assert(AppSettings_SaveCloud(NULL,NULL,NULL,2)==APP_SETTINGS_INVALID);
 assert(AppSettings_DisconnectWifi(2)==APP_SETTINGS_INVALID);
 puts("PASS inventory truncation/error is not absence; genuine fence/DNS/BLE ownership defer; finite whole transaction; every SDK scope <=2s, cancellation generation retained");
 return 0;
}
'''
def main():
    adapter=(ROOT/'AppliNonSecure/Core/Src/app_settings_ncp.c').read_text()
    for name in ('app_settings_store.h','app_features.h','tx_api.h','w61_at_api.h','w6x_api.h'):
        adapter=adapter.replace(f'#include "{name}"','')
    for enabled in (0,1):
        run_native(f'#define APP_SETTINGS_WRITES_ENABLED {enabled}\n'+production()+MOCK+adapter+TESTS)
if __name__=='__main__':main()
