"""Actual-C boot configuration gate: no SET on equal/mismatch/error readback."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT,run_native

PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef int W61_Status_t;
typedef unsigned TickType_t;
#define W61_STATUS_OK 0
#define W61_STATUS_ERROR 2
#define W61_STATUS_TIMEOUT 3
#define W61_NCP_TIMEOUT 2000U
#define MODEM_NO_TX_LOCK 1U
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define SYS_LOG_ERROR(...) ((void)0)
#define SYS_LOG_INFO(...) ((void)0)
static unsigned critical,held,writes,queries,gives,admitted,remaining,duplicate,missing;
static const char*token="0";
static int answer;
#define taskENTER_CRITICAL() (++critical)
#define taskEXIT_CRITICAL() (--critical)
struct modem_cmd_handler_data {void*user_data;unsigned sem_tx_lock;bool fence;};
struct modem_cmd_handler {void*cmd_handler_data;};
struct modem {int iface;struct modem_cmd_handler handler;unsigned sem_response;void*rx_data;};
typedef struct {struct modem Modem;} W61_Object_t;
struct modem_cmd {const char*cmd;int(*func)(struct modem_cmd_handler_data*,size_t,char**,uint16_t);unsigned count;};
#define MODEM_CMD(cmd,func,count,delim) {cmd,func,count}
typedef struct {uint32_t value,seen;} W61_ConfigReadback_t;
static struct modem_cmd_handler_data d;
static W61_Object_t obj;
static W61_Status_t W61_Status(int x){return x;}
static unsigned W61_AT_Common_TakeTxLockBudget(unsigned sem,unsigned n,unsigned*s){assert(sem==1 && n==2000 && !held);*s=10;if(admitted)held=1;return admitted;}
static unsigned W61_AT_Common_RemainingTxBudget(unsigned s,unsigned n){assert(s==10 && n==2000 && held);return remaining;}
static int xSemaphoreGive(unsigned sem){assert(sem==1 && held && !obj.Modem.rx_data);held=0;++gives;return 1;}
static int modem_cmd_send_ext(int*,struct modem_cmd_handler*,const struct modem_cmd*,size_t,const uint8_t*,unsigned,unsigned,unsigned);
static int modem_cmd_send(int*i,struct modem_cmd_handler*h,void*c,unsigned n,const uint8_t*p,unsigned s,unsigned t){(void)i;(void)h;(void)c;(void)n;(void)p;(void)s;(void)t;++writes;return 0;}
'''
TESTS=r'''
static int modem_cmd_send_ext(int*i,struct modem_cmd_handler*h,const struct modem_cmd*c,size_t n,const uint8_t*p,unsigned sem,unsigned t,unsigned f){
 (void)i;(void)h;assert(n==1 && held && sem==2 && t==remaining && f==MODEM_NO_TX_LOCK);
 assert(strchr((char*)p,'?') && !strchr((char*)p,'='));++queries;
 if(!missing){char*argv[]={(char*)token};c->func(&d,0,argv,1);if(duplicate)c->func(&d,0,argv,1);}
 if(answer==3)d.fence=true;return answer;
}
static void reset(void){memset(&obj,0,sizeof obj);memset(&d,0,sizeof d);d.user_data=&obj.Modem;d.sem_tx_lock=1;obj.Modem.handler.cmd_handler_data=&d;obj.Modem.sem_response=2;
 critical=held=writes=queries=gives=duplicate=missing=0;admitted=remaining=1990;token="0";answer=0;}
int main(void){
 reset();assert(!W61_AT_Common_VerifyConfig(&obj,"AT+CWAUTOCONN?\r\n","+CWAUTOCONN:",0));assert(queries==1 && !writes && gives==1 && !held && !critical);
 token="1";assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWAUTOCONN?\r\n","+CWAUTOCONN:",0)==2);assert(!writes);
 puts("PASS matching zero skips setter; differing old/new value rejects without write");
 const char*bad[]={"","junk","0junk","-0","+0"," 0","4294967296","00000000000"};
 for(unsigned i=0;i<ARRAY_SIZE(bad);++i){reset();token=bad[i];assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWAUTOCONN?\r\n","+CWAUTOCONN:",0)==2);assert(!writes && !obj.Modem.rx_data);}
 reset();missing=1;assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWMODE?\r\n","+CWMODE:",1)==2);
 reset();token="1";duplicate=1;assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWMODE?\r\n","+CWMODE:",1)==2);
 puts("PASS malformed/overflow/empty/missing/duplicate scalar cannot be mistaken for an existing zero or valid mode");
 reset();answer=3;assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWDHCP?\r\n","+CWDHCP:",1)==3);assert(d.fence && !held && !obj.Modem.rx_data && queries==1);
 char*late[]={"1"};on_cmd_config_scalar(&d,0,late,1);assert(d.fence && !obj.Modem.rx_data && !writes);
 reset();admitted=0;assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWDHCP?\r\n","+CWDHCP:",1)==3 && !queries && !gives);
 reset();remaining=0;assert(W61_AT_Common_VerifyConfig(&obj,"AT+CWDHCP?\r\n","+CWDHCP:",1)==3 && !queries && gives==1);
 puts("PASS original 2s budget, timeout fence retained, late callback has no borrowed stack pointer, no retries");
 reset();assert(W61_AT_Common_VerifyConfig(&obj,"AT+SYSSTORE=0\r\n","+CWDHCP:",1)==2 && !queries);
 const char*blocked[]={"AT+CWAUTOCONN=0\r\n","AT+CWMODE=1,0\r\n","AT+CWDHCP=1,1\r\n","AT+CIPAP=1\r\n","AT+SET_CLOCK=1\r\n","AT+CWANTENABLE=0,0\r\n","AT+CWCREDADD=ignored\r\n","AT+RESTORE\r\n","AT+SYSSTORE=0\r\n"};
 for(unsigned i=0;i<ARRAY_SIZE(blocked);++i)assert(W61_AT_Common_SetExecute(&obj,(uint8_t*)blocked[i],2000)==2);
 assert(!writes);assert(!W61_AT_Common_SetExecute(&obj,(uint8_t*)"AT+CIPRECVMODE=1\r\n",2000));assert(writes==1);
 assert(!W61_AT_Common_SetExecute(&obj,(uint8_t*)"AT+FS=0,1,managed\r\n",2000));assert(writes==2);
 puts("PASS boot/cleanup persistent SET defense; volatile receive mode and separately owned file commit unchanged");
 return 0;
}
'''

def main():
    s=(ROOT/"ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c").read_text()
    callback=s.replace("MODEM_CMD_DEFINE(on_cmd_config_scalar)","static int on_cmd_config_scalar(struct modem_cmd_handler_data *data,size_t len,char **argv,uint16_t argc)")
    run_native("#define W61_CONFIG_PRESERVE 1\n"+PREFIX+function(callback,"on_cmd_config_scalar")+function(s,"W61_AT_Common_VerifyConfig")+function(s,"W61_AT_Common_SetExecute")+TESTS)
    for f in ("w6x_wifi.c","w6x_net.c"):
        source=(ROOT/"ThirdParty/ST67W6X_Network_Driver/Core"/f).read_text()
        assert "W61_CONFIG_PRESERVE" in source and "W61_AT_Common_VerifyConfig" in source
    print("PASS preserve-mode default is opt-in; same guarded init shared by startup and coordinated recovery")
if __name__=="__main__":main()
