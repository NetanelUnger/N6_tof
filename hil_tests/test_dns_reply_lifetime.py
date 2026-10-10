"""Actual static DNS callback never writes a returned caller's stack storage."""
from test_raw_send_response import extract
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
struct modem_cmd_handler_data { void *user_data; bool dns_drain_active; };
struct modem { bool dns_query_live;void *rx_data;char **argv;uint16_t *argc;char cmd_match_buf[128]; };
#define MODEM_CMD_DEFINE(name) static int32_t name(struct modem_cmd_handler_data *data,uint16_t len,char **argv,uint16_t argc)
static unsigned critical;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
'''
TESTS = r'''
int main(void) {
 struct modem mdm={0};struct modem_cmd_handler_data data={&mdm,false};
 char output[128]={0},*result[4];uint16_t argc=0;
 strcpy(mdm.cmd_match_buf,"+CIPDOMAIN:192.0.2.1");char *args[]={mdm.cmd_match_buf+11};
 mdm.rx_data=output;mdm.argv=result;mdm.argc=&argc;mdm.dns_query_live=true;
 on_cmd_dns_query(&data,20,args,1);
 assert(!critical && argc==1 && !strcmp(result[0],"192.0.2.1"));
 puts("PASS live DNS query copies the address into its active caller");
 mdm.rx_data=mdm.argv=NULL;mdm.argc=NULL;mdm.dns_query_live=false;
 on_cmd_dns_query(&data,20,args,1);assert(!critical);
 puts("PASS late static callback after caller retirement never accesses dead pointers");
 mdm.dns_query_live=true;data.dns_drain_active=true;
 on_cmd_dns_query(&data,20,args,1);assert(!critical);
 puts("PASS pending terminal drain cannot populate a replacement caller's result");
 return 0;
}
'''
WIFI_PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef unsigned W6X_Status_t;
typedef unsigned W6X_WiFi_StaStateType_e;
enum {W6X_STATUS_OK,W6X_STATUS_BUSY,W6X_STATUS_ERROR};
enum {W6X_WIFI_STATE_STA_DISCONNECTED,W6X_WIFI_STATE_STA_CONNECTED,W6X_WIFI_STATE_STA_GOT_IP};
typedef struct {char SSID[33];uint8_t MAC[6];unsigned Channel,Rssi;} W6X_WiFi_Connect_t;
typedef struct {struct {struct {unsigned dns_drain_active;} handler_data;} Modem;} W61_Object_t;
static struct {struct {unsigned station_state,ip_valid,connected,has_ip;int last_status;
 char ssid[33];uint8_t ap_mac[6],ip_address[4],gateway_address[4],netmask_address[4];unsigned channel,rssi;} status;} context;
static struct {struct {unsigned wifi_event_generation,wifi_last_probe_tick,wifi_last_probe_status;} work;
 struct {unsigned wifi_state_confirmed,wifi_connected,wifi_has_ip;} shadow;
 struct {struct {unsigned wifi_state_queries,wifi_query_failures;} faults;} counters;
 struct {typeof(context)*wifi_control_context;} queues;} radio_manager;
static W61_Object_t driver;static unsigned calls,fail,race;
static unsigned HAL_GetTick(void){return 1234;}
static W61_Object_t *W61_ObjGet(void){return &driver;}
static unsigned W6X_WiFi_Station_GetState(unsigned *s,W6X_WiFi_Connect_t *c){
 ++calls;*s=W6X_WIFI_STATE_STA_GOT_IP;c->SSID[0]='X';
 if(race)++radio_manager.work.wifi_event_generation;
 return fail ? W6X_STATUS_ERROR : W6X_STATUS_OK;
}
static unsigned wifi_get_station_ip(uint8_t *a,uint8_t *g,uint8_t *m){a[0]=192;g[0]=192;m[0]=255;return W6X_STATUS_OK;}
'''
WIFI_TESTS = r'''
int main(void){
 radio_manager.queues.wifi_control_context=&context;
 radio_manager.shadow.wifi_connected=radio_manager.shadow.wifi_has_ip=1;
 driver.Modem.handler_data.dns_drain_active=1;wifi_refresh_status();
 assert(!calls && !radio_manager.counters.faults.wifi_query_failures && radio_manager.shadow.wifi_has_ip);
 assert(radio_manager.work.wifi_last_probe_status==W6X_STATUS_BUSY);
 driver.Modem.handler_data.dns_drain_active=0;wifi_refresh_status();
 assert(calls==1 && radio_manager.shadow.wifi_state_confirmed && context.status.station_state==W6X_WIFI_STATE_STA_GOT_IP && context.status.ip_valid);
 fail=1;wifi_refresh_status();assert(!radio_manager.shadow.wifi_state_confirmed && context.status.station_state==W6X_WIFI_STATE_STA_GOT_IP);
 fail=0;race=1;wifi_refresh_status();assert(!radio_manager.shadow.wifi_state_confirmed);
 puts("PASS deferred DNS skips Wi-Fi query; later refresh restores IP without stale-generation overwrite");
 return 0;
}
'''
def main():
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c').read_text(encoding='utf-8')
    run_native(PREFIX+extract(source,'on_cmd_query',True)+extract(source,'on_cmd_dns_query',True)+TESTS)
    query=extract_function(source,'W61_AT_Common_Query_Parse')
    assert 'static const struct modem_cmd dns_handler' in query
    retire=query.split('TickType_t held_ticks =',1)[1]
    assert all(x in retire for x in ['mdm->dns_query_live = false','mdm->rx_data = NULL','mdm->argv = NULL','mdm->argc = NULL','taskENTER_CRITICAL()'])
    print('PASS DNS descriptor persists and all borrowed query pointers retire before return')
    wifi=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text(encoding='utf-8')
    # MSVC native fixture uses a named equivalent for GNU typeof.
    prefix=WIFI_PREFIX.replace('static struct {struct {unsigned station_state', 'typedef struct {struct {unsigned station_state').replace(';} status;} context;', ';} status;} Context;static Context context;').replace('typeof(context)*','Context*')
    run_native(prefix+extract_function(wifi,'wifi_refresh_status')+WIFI_TESTS)
    worker=extract_function(wifi,'WIFI_BLE_App_WifiControlRun')
    assert worker.index('wifi_state_confirmed == 0U') < worker.index('status == TX_NO_EVENTS')
    assert '>= 1000U' in worker
    print('PASS refresh retry is paced in the existing worker even when BLE work prevents idle timeout')
if __name__=='__main__':main()
