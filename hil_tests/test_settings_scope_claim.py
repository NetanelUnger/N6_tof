"""Actual Cloud NCP-scope claims versus a settings owner, no HTTP/server traffic."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native

MOCK=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned UINT;typedef int ssize_t;typedef unsigned CloudHttpKind_t;
#define TX_INT_DISABLE 1
#define CLOUD_HTTP_TIMEOUT_MS 4500
#define CLOUD_RESPONSE_SIZE 32
#define CLOUD_HTTP_NONE 0
#define Debug_UART_Log(...) ((void)0)
static struct {int socket;uint32_t http_deadline,close_retry_tick,http_kind,response_length,network_epoch;
 char response[33];struct{int last_transport_status;}status;}context,*cloud=&context;
static uint32_t cloud_network_epoch,now;static unsigned busy,irq,begins,ends,wire,backoffs;
static UINT tx_interrupt_control(UINT p){UINT old=irq;irq=p;return old;}
static unsigned AppSettings_IsBusy(void){assert(irq);return busy;}
static uint32_t HAL_GetTick(void){return now;}
static void W6X_Net_RequestScopeBegin(unsigned n,const volatile uint32_t*p,unsigned g){
 assert(irq && !busy && begins==ends);assert(n==500 || n==4500 || n==1000);(void)p;(void)g;++begins;}
static void W6X_Net_RequestScopeEnd(void){assert(!irq && begins==ends+1);++ends;}
static int W6X_Net_Close(int s){assert(!irq&&s==4);++wire;return 0;}
static ssize_t W6X_Net_Recv(int s,void*p,size_t n,int flags){assert(!irq&&s==4&&n==32&&!flags);(void)p;++wire;return 0;}
static int cloud_begin_request_inner(CloudHttpKind_t k,const char*m,const char*p,const char*c,const void*b,size_t n,const void*b2,size_t n2,unsigned a){
 (void)k;(void)m;(void)p;(void)c;(void)b;(void)n;(void)b2;(void)n2;(void)a;assert(!irq);++wire;return 0;}
static void cloud_close_socket(void);
static int cloud_response_ready(void){return 0;}static void cloud_finish_request(void){}
static void cloud_backoff(void){++backoffs;}
'''
TESTS=r'''
int main(void){
 busy=1;cloud->socket=-1;assert(cloud_begin_request(1,"G","p","c",0,0,0,0,0)==-1);
 assert(!wire&&!begins&&!irq);
 cloud->socket=4;cloud->http_kind=2;cloud->http_deadline=1000;
 cloud_receive_step();cloud_close_socket();assert(!wire&&!begins&&!irq&&cloud->socket==4&&cloud->http_kind==2);
 busy=0;cloud_receive_step();assert(wire==1&&begins==ends&&!irq);
 cloud_close_socket();assert(wire==2&&cloud->socket==-1&&begins==ends&&!irq);
 assert(cloud_begin_request(1,"G","p","c",0,0,0,0,0)==0);
 assert(wire==3&&begins==ends&&!irq&&cloud->http_deadline==4500);
 busy=1;cloud->socket=4;cloud->http_deadline=50;now=51;cloud_receive_step();
 assert(backoffs==1&&wire==3); /* waiting never extends a preexisting network deadline */
 puts("PASS atomic settings/Cloud scope admission, original network deadlines, no wire/retirement on busy, normal resume");return 0;}
'''
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    run_native(MOCK+'\n'.join(function(source,n) for n in ('cloud_begin_request','cloud_receive_step','cloud_close_socket'))+TESTS)
if __name__=='__main__':main()
