"""Actual Wi-Fi helpers: unified persistence, secret lifetime and desired intent."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef int W6X_Status_t;
#define W6X_STATUS_OK 0
#define W6X_STATUS_ERROR 2
typedef int AppSettings_Result;
#define APP_SETTINGS_OK 0
typedef struct {uint8_t SSID[33],Password[64];unsigned Secured;}W6X_WiFi_Connect_Opts_t;
static uint8_t wifi_desired_ssid[33];
static unsigned wifi_connection_desired,wifi_credentials_saved,wifi_unified_settings;
static struct {unsigned wifi_reconnect_required;}radio_recovery;
static struct {struct {unsigned wifi_has_ip;}shadow;struct {unsigned wifi_connect_call_active;}work;}radio_manager;
static unsigned now,save_calls,connect_calls,cancel_calls,stored_status,load_status,connect_status,cancel_status,ip,loaded_desired;
static void AppSettings_Scrub(void*p,size_t n){volatile unsigned char*b=p;while(n--)*b++=0;}
static int AppSettings_SaveWifi(const char*s,const char*p){assert(!strcmp(s,"test-network") && !strcmp(p,"synthetic-secret"));++save_calls;return stored_status;}
static unsigned reference;
static unsigned AppSettings_WifiUsesReference(void){return reference;}
static int AppSettings_GetWifi(char*s,char*p,uint32_t*d){strcpy(s,"test-network");strcpy(p,reference?"":"synthetic-secret");*d=loaded_desired;return load_status;}
static int AppSettings_DisconnectWifi(unsigned f){assert(f<=1);++cancel_calls;return cancel_status;}
static unsigned HAL_GetTick(void){return now;}
static void Debug_UART_Log(const char*a,const char*b,...){(void)a;(void)b;}
static int W6X_WiFi_Connect(W6X_WiFi_Connect_Opts_t*o){assert(radio_manager.work.wifi_connect_call_active);
 assert(!strcmp((char*)o->SSID,"test-network"));
 if(wifi_unified_settings && !reference)assert(!o->Secured && !strcmp((char*)o->Password,"synthetic-secret"));
 else {assert(o->Secured==1);for(unsigned i=0;i<sizeof o->Password;++i)assert(!o->Password[i]);}
 ++connect_calls;now+=123;return connect_status;}
static void wifi_refresh_status(void){radio_manager.shadow.wifi_has_ip=ip;}
static void reset(void){memset(&radio_manager,0,sizeof radio_manager);memset(wifi_desired_ssid,0,sizeof wifi_desired_ssid);
 wifi_connection_desired=wifi_credentials_saved=wifi_unified_settings=0;now=100;
 reference=0;save_calls=connect_calls=cancel_calls=stored_status=load_status=connect_status=cancel_status=0;ip=loaded_desired=1;}
static W6X_WiFi_Connect_Opts_t supplied(void){W6X_WiFi_Connect_Opts_t o={0};strcpy((char*)o.SSID,"test-network");strcpy((char*)o.Password,"synthetic-secret");return o;}
'''
TESTS = r'''
int main(void){
 reset();W6X_WiFi_Connect_Opts_t o=supplied();wifi_remember_connection(&o);
 assert(wifi_connection_desired && wifi_credentials_saved && wifi_unified_settings && save_calls==1);
 for(unsigned i=0;i<sizeof o.Password;++i)assert(!o.Password[i]);
 wifi_restore_connection();assert(connect_calls==1 && !radio_recovery.wifi_reconnect_required && !radio_manager.work.wifi_connect_call_active);
 puts("PASS unified verified save restores with unchanged CWJAP personal/open authentication; working password scrubbed");
 reset();stored_status=6;o=supplied();wifi_remember_connection(&o);wifi_restore_connection();
 assert(wifi_connection_desired && !wifi_credentials_saved && !wifi_unified_settings && !connect_calls && radio_recovery.wifi_reconnect_required);
 for(unsigned i=0;i<sizeof o.Password;++i)assert(!o.Password[i]);
 puts("PASS blocked/failed save cannot claim persisted credentials or select another network");
 for(unsigned mode=0;mode<2;++mode){reset();o=supplied();wifi_remember_connection(&o);
  if(mode)loaded_desired=0;else load_status=5;wifi_restore_connection();assert(!connect_calls && radio_recovery.wifi_reconnect_required);}
 reset();wifi_restore_connection();assert(!connect_calls && !radio_recovery.wifi_reconnect_required);
 reset();o=supplied();wifi_remember_connection(&o);connect_status=2;ip=0;wifi_restore_connection();assert(connect_calls==1 && radio_recovery.wifi_reconnect_required);
 connect_status=0;wifi_restore_connection();assert(radio_recovery.wifi_reconnect_required);
 puts("PASS busy load/canceled saved intent/no network/association error/missing IP never produce false restore success");
 reset();o=supplied();wifi_remember_connection(&o);assert(!wifi_forget_connection(0));wifi_restore_connection();
 assert(!wifi_connection_desired && wifi_credentials_saved && cancel_calls==1 && !connect_calls);
 reset();o=supplied();wifi_remember_connection(&o);assert(!wifi_forget_connection(1));
 assert(!wifi_connection_desired && !wifi_credentials_saved && !wifi_unified_settings && !wifi_desired_ssid[0]);
 reset();o=supplied();wifi_remember_connection(&o);cancel_status=6;assert(wifi_forget_connection(1)==W6X_STATUS_ERROR);
 assert(!wifi_connection_desired && wifi_credentials_saved && wifi_desired_ssid[0]);
 puts("PASS disconnect cancels volatile intent even when persistence denied; verified forget retires unified credentials");
 reset();wifi_connection_desired=wifi_credentials_saved=1;strcpy((char*)wifi_desired_ssid,"test-network");
 wifi_restore_connection();assert(connect_calls==1 && !wifi_unified_settings);
 reset();wifi_connection_desired=wifi_credentials_saved=wifi_unified_settings=reference=1;strcpy((char*)wifi_desired_ssid,"test-network");
 wifi_restore_connection();assert(connect_calls==1 && wifi_unified_settings);
 puts("PASS managed explicit NCP reference uses Secured=1 and empty working password, no credential mutation");
 puts("PASS retained legacy NCP reference restores with Secured=1 without password fetch/migration");
 return 0;}
'''
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    run_native(PREFIX+'\n'.join(function(source,n) for n in (
        'wifi_remember_connection','wifi_restore_connection','wifi_forget_connection'))+TESTS)
    assert 'W6X_WiFi_AddCredentials(' not in source and 'W6X_WiFi_DeleteCredentials(' not in source
    assert 'status = W6X_WiFi_Disconnect(0U);' in source
    print('PASS no legacy CWCRED mutations or implicit forget remains in application')
if __name__=='__main__':main()
