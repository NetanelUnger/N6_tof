"""Actual SDK/application boot and repeat-init paths in preserve/default modes."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native
PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
typedef int W6X_Status_t;typedef int W61_Status_t;typedef unsigned W61_Net_DhcpType_e;typedef unsigned W61_WiFi_AntennaMode_e;
#define W61_NULL_ASSERT_STR(p,n) assert(p)
#define W61_Obj_Null_str 0
#define W61_CMDRSP_STRING_SIZE 192
#define W61_READY_DEFAULT_TIMEOUT_MS 2000
#define SYS_LOG_ERROR(...) ((void)0)
#define W6X_STATUS_OK 0
#define W6X_STATUS_ERROR 2
#define W61_STATUS_OK 0
#define W61_STATUS_ERROR 2
#define W61_MODULE_STATE_INIT 1
#define W61_MODULE_STATE_NOT_INIT 0
#define W61_WIFI_ANTENNA_DISABLED 0
#define W61_MODULE_ID_B 1
#define W6X_WIFI_AUTOCONNECT 0U
#define W6X_WIFI_ADAPTIVE_COUNTRY_CODE 0U
#define W6X_WIFI_COUNTRY_CODE "00"
#define W6X_NET_DHCP 1U
#define W61_NET_DHCP_STA_ENABLED 1U
#define W61_NET_DHCP_STA_AP_ENABLED 3U
#define W6X_NET_HOSTNAME "N6-ToF"
#define W6X_NET_SAP_IP_SUBNET {10,19,96}
#define W61_NET_MAX_CONNECTIONS 2
#define W6X_NET_RECV_BUFFER_SIZE 9216
#define W6X_NET_SEND_TIMEOUT 10000
#define W6X_NET_RECV_TIMEOUT 10000
#define NULL_ASSERT(p,n) assert(p)
#define WIFI_LOG_ERROR(...) ((void)0)
#define WIFI_LOG_DEBUG(...) ((void)0)
#define NET_LOG_ERROR(...) ((void)0)
#define NET_LOG_DEBUG(...) ((void)0)
#define NET_LOG_WARN(...) ((void)0)
#define HAL_SYS_RESET() assert(0)
#define W6X_WiFi_Station_cb 0
#define W6X_WiFi_AP_cb 0
#define W6X_Net_cb 0
static unsigned persistent,queries,ap_queries,allocs,auto_value,mode_value,dhcp_value,antenna_value,ap_missing,query_error,volatile_calls;
typedef struct {struct {struct {unsigned ModuleID;}ModuleID;}ModuleInfo;struct {unsigned WiFi_status,Net_status;}ResetCfg;
 struct {struct {unsigned AutoConnect;}STASettings;}WifiCtx;
 struct {unsigned WiFi_DTIM_Factor,WiFi_DTIM_Interval;}LowPowerCfg;
 struct {unsigned Supported,DHCP_STA_IsEnabled;struct {uint8_t IP_Addr[4],IP_Mask[4];}Net_ap_info;}NetCtx;}W61_Object_t;
static W61_Object_t obj,*W6X_WiFi_drv_obj,*W6X_Net_drv_obj;
typedef struct {void*Wifi_event;}W6X_WiFiCtx_t;static W6X_WiFiCtx_t*p_wifi_ctx;
typedef struct {unsigned Number,SoSndTimeo,RecvTimeout;}W6X_Net_Socket_t;
typedef struct {void*DataAvailable;}W6X_Net_Connection_t;
typedef struct {W6X_Net_Connection_t Connection[2];W6X_Net_Socket_t Sockets[3];struct {unsigned is_valid;char*name;}Credentials[6];unsigned NextSocketToUse;}W6X_NetCtx_t;
static W6X_NetCtx_t*p_net_ctx;
typedef struct {void*APP_wifi_cb,*APP_net_cb;}W6X_App_Cb_t;static W6X_App_Cb_t cb={(void*)1,(void*)1};
static W61_Object_t*W61_ObjGet(void){return &obj;}
static W6X_App_Cb_t*W6X_GetCbHandler(void){return &cb;}
static int TranslateErrorStatus(int n){return n;}
static void*pvPortMalloc(size_t n){++allocs;return malloc(n);}
static void vPortFree(void*p){if(p){assert(allocs);--allocs;free(p);}}
static void*xEventGroupCreate(void){return pvPortMalloc(4);}
static void vEventGroupDelete(void*p){vPortFree(p);}
static void*xSemaphoreCreateBinary(void){return pvPortMalloc(4);}
static void vSemaphoreDelete(void*p){vPortFree(p);}
static int W61_RegisterULcb(W61_Object_t*p,...){assert(p==&obj);return 0;}
static int W61_WiFi_Init(W61_Object_t*p){assert(p==&obj);return 0;}
static int W61_WiFi_DeInit(W61_Object_t*p){assert(p==&obj);return 0;}
static int W61_WiFi_GetAntennaEnable(W61_Object_t*p,W61_WiFi_AntennaMode_e*v){(void)p;*v=antenna_value;return 0;}
static int W61_WiFi_SetAntennaEnable(W61_Object_t*p,unsigned v){(void)p;(void)v;++persistent;return 0;}
static int W6X_WiFi_Station_Start(void){++persistent;return 0;}
static int W61_WiFi_SetAutoConnect(W61_Object_t*p,unsigned v){(void)p;auto_value=v;++persistent;return 0;}
static int W61_WiFi_SetCountryCode(W61_Object_t*p,unsigned*v,char*c){(void)p;(void)v;(void)c;++volatile_calls;return 0;}
static int W61_WiFi_SetDTIM(W61_Object_t*p,unsigned v){(void)p;assert(v==1);++volatile_calls;return 0;}
static int W61_WiFi_Stop(W61_Object_t*p){(void)p;++persistent;return 0;}
static int W61_Net_Init(W61_Object_t*p){(void)p;++volatile_calls;return 0;}
static int W61_Net_DeInit(W61_Object_t*p){(void)p;return 0;}
static int W61_Net_SetDhcpConfig(W61_Object_t*p,unsigned*state,unsigned*op){assert(p==&obj);++persistent;if(*op)dhcp_value|=*state;else dhcp_value&=~*state;return 0;}
static int W61_Net_SetHostname(W61_Object_t*p,uint8_t*h){(void)p;(void)h;++volatile_calls;return 0;}
static int W61_Net_AP_SetIPAddress(W61_Object_t*p,uint8_t*ip,uint8_t*mask){(void)p;(void)ip;(void)mask;++persistent;return 0;}
static int W61_Net_AP_GetIPAddress(W61_Object_t*p){++ap_queries;if(!ap_missing){uint8_t ip[]={10,19,96,1},mask[]={255,255,255,0};memcpy(p->NetCtx.Net_ap_info.IP_Addr,ip,4);memcpy(p->NetCtx.Net_ap_info.IP_Mask,mask,4);}return query_error;}
static int W61_Net_SetReceiveBufferLen(W61_Object_t*p,unsigned i,unsigned n){(void)p;(void)i;assert(n==9216);++volatile_calls;return 0;}
static int W61_Net_GetReceiveBufferLen(W61_Object_t*p,unsigned i,uint32_t*n){(void)p;(void)i;*n=9216;return 0;}
static unsigned clock_value;
static int W61_GetClockSource(W61_Object_t*p,uint32_t*v){(void)p;*v=clock_value;return query_error;}
static int W61_WaitForReady(W61_Object_t*p,unsigned t){(void)p;assert(t==2000);++volatile_calls;return 0;}
static int W61_AT_Common_SetExecute(W61_Object_t*p,uint8_t*c,unsigned t){(void)p;assert(strstr((char*)c,"AT+SET_CLOCK=") && t==0);++persistent;return 0;}
static int W61_AT_Common_VerifyConfig(W61_Object_t*p,const char*q,const char*r,uint32_t expected){(void)r;assert(p==&obj && strchr(q,'?') && !strchr(q,'='));++queries;if(query_error)return query_error;
 unsigned value=strstr(q,"CWAUTOCONN")?auto_value:strstr(q,"CWMODE")?mode_value:dhcp_value;return value==expected?0:2;}
void W6X_WiFi_DeInit(void);void W6X_Net_DeInit(void);
static void reset(void){assert(!allocs);memset(&obj,0,sizeof obj);obj.ModuleInfo.ModuleID.ModuleID=1;obj.NetCtx.Supported=1;W6X_WiFi_drv_obj=W6X_Net_drv_obj=NULL;
 persistent=queries=ap_queries=volatile_calls=auto_value=antenna_value=ap_missing=query_error=0;mode_value=dhcp_value=1;}
'''
TESTS=r'''
int main(void){reset();assert(!W6X_WiFi_Init());assert(!W6X_Net_Init());assert(!wifi_enable_station_dhcp());
#if W61_CONFIG_PRESERVE
 assert(!persistent && queries==4 && ap_queries==1 && obj.NetCtx.DHCP_STA_IsEnabled);
#else
 assert(persistent==6 && !queries && !ap_queries);
#endif
 W6X_Net_DeInit();W6X_WiFi_DeInit();assert(!allocs);
#if W61_CONFIG_PRESERVE
 assert(!persistent);assert(!W6X_WiFi_Init());assert(!W6X_Net_Init());W6X_Net_DeInit();W6X_WiFi_DeInit();assert(!persistent && !allocs);
 reset();auto_value=1;assert(W6X_WiFi_Init()==2 && !persistent && !allocs && queries==1);
 reset();mode_value=0;assert(W6X_WiFi_Init()==2 && !persistent && !allocs && queries==2);
 reset();antenna_value=1;assert(W6X_WiFi_Init()==2 && !persistent && !allocs && !queries);
 reset();dhcp_value=0;assert(W6X_Net_Init()==2 && !persistent && !allocs);assert(wifi_enable_station_dhcp()==2 && !persistent && !obj.NetCtx.DHCP_STA_IsEnabled);
 reset();ap_missing=1;uint8_t stale[]={10,19,96,1};memcpy(obj.NetCtx.Net_ap_info.IP_Addr,stale,4);assert(W6X_Net_Init()==2 && !persistent && !allocs);
 reset();query_error=3;assert(W6X_WiFi_Init()==3 && !persistent && !allocs);
 puts("PASS actual startup/repeated init/cleanup retain no SET; autoconnect/mode/antenna/DHCP/missing AP/error fail closed and release existing resources");
#else
 puts("PASS default vendor initialization/cleanup unchanged; preserve mode is explicit opt-in");
#endif
 reset();clock_value=1;assert(!W61_SetClockSource(&obj,1) && !persistent);
 clock_value=2;
#if W61_CONFIG_PRESERVE
 assert(W61_SetClockSource(&obj,1)==2 && !persistent && !volatile_calls);
#else
 assert(!W61_SetClockSource(&obj,1) && persistent==1 && volatile_calls==1);
#endif
 assert(W61_SetClockSource(&obj,0)==2 && W61_SetClockSource(&obj,4)==2);
 puts("PASS actual clock change guard: equal skips SET; preserve mismatch never writes or waits for reset");
 return 0;}
'''
def main():
    wifi=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Core/w6x_wifi.c').read_text()
    net=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Core/w6x_net.c').read_text()
    app=(ROOT/'AppliNonSecure/Core/Src/wifi_ble_app.c').read_text()
    sys=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_sys.c').read_text()
    actual='\n'.join([function(sys,'W61_SetClockSource'),function(wifi,'W6X_WiFi_Init'),function(wifi,'W6X_WiFi_DeInit'),function(net,'W6X_Net_Init'),function(net,'W6X_Net_DeInit'),function(app,'wifi_enable_station_dhcp')])
    for mode in (0,1):run_native(f'#define W61_CONFIG_PRESERVE {mode}\n'+PREFIX+actual+TESTS)
if __name__=='__main__':main()
