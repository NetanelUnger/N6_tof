"""Production receive configuration and socket retirement, mocked NCP replies."""
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t W61_Status_t;
enum {W61_STATUS_OK,W61_STATUS_ERROR,W61_STATUS_BUSY,W61_STATUS_TIMEOUT};
#define W61_NET_MAX_CONNECTIONS 5
enum {W6X_NET_SOCKET_RESET,W6X_NET_SOCKET_ALLOCATED,W6X_NET_SOCKET_BIND,
 W6X_NET_SOCKET_LISTENING,W6X_NET_SOCKET_CONNECTED,W6X_NET_SOCKET_CLOSING};
typedef struct {unsigned Status,Number,OpenAttempted,RecvBuffSize;
 void *Ca_Cert,*Private_Key,*Certificate,*PSK,*PSK_Identity;} W6X_Net_Socket_t;
typedef struct {uint8_t Number;char RemoteIP[64];} W61_Net_Connection_t;
static struct {W6X_Net_Socket_t Sockets[6];
 struct {unsigned SocketConnected,DataAvailableSize,DataAvailable;} Connection[5];} ctx,*p_net_ctx=&ctx;
static void *W6X_Net_drv_obj=(void*)1;
#define NULL_ASSERT(p,m) do {assert(p);}while(0)
#define taskENTER_CRITICAL() ((void)0)
#define taskEXIT_CRITICAL() ((void)0)
typedef unsigned TickType_t;
static unsigned frees,stops,queries,sets,sem_used,remote_exists,close_response,query_response,close_event;
static unsigned receive_size,receive_response,set_response;
static void vPortFree(void *p) {assert(p);++frees;}
static int xSemaphoreTake(unsigned sem,TickType_t wait) {assert(!wait);sem_used=sem;return 1;}
static int W6X_Net_TranslateErrorStatus(unsigned status) {return status ? -(int)status : 0;}
static void W6X_Net_Clean_Socket(int32_t);
static unsigned W61_Net_StopClientConnection(void *o,W61_Net_Connection_t *conn) {
 (void)o;++stops;if(close_event){ctx.Connection[conn->Number].SocketConnected=0;W6X_Net_Clean_Socket(conn->Number);}
 return close_response;
}
static unsigned W61_Net_GetSocketInformation(void *o,unsigned number,W61_Net_Connection_t *conn) {
 (void)o;++queries;memset(conn,0,sizeof *conn);conn->Number=(uint8_t)number;
 if(remote_exists)strcpy(conn->RemoteIP,"192.0.2.1");return query_response;
}
static unsigned W61_Net_GetReceiveBufferLen(void *o,unsigned number,unsigned *size) {
 (void)o;assert(number==2);++queries;*size=receive_size;return receive_response;
}
static unsigned W61_Net_SetReceiveBufferLen(void *o,unsigned number,unsigned size) {
 (void)o;assert(number==2 && size==2048);++sets;return set_response;
}
#define Debug_UART_Log(...) ((void)0)
'''

TESTS = r'''
static void reset(void) {
 memset(&ctx,0,sizeof ctx);for(unsigned i=0;i<6;++i)ctx.Sockets[i].Number=6;
 frees=stops=queries=sets=sem_used=remote_exists=close_response=query_response=close_event=0;
 receive_size=2048;receive_response=set_response=0;
 ctx.Sockets[4].Status=W6X_NET_SOCKET_ALLOCATED;ctx.Sockets[4].Number=2;ctx.Sockets[4].RecvBuffSize=2048;
}
int main(void) {
 reset();assert(W6X_Net_ConfigureReceiveBuffer(4)==0 && queries==1 && !sets);
 puts("PASS confirmed matching NCP receive size never reallocates the buffer");
 reset();receive_size=128;assert(W6X_Net_ConfigureReceiveBuffer(4)==0 && sets==1);
 puts("PASS mismatched confirmed receive size is explicitly configured");
 reset();receive_response=W61_STATUS_ERROR;assert(W6X_Net_ConfigureReceiveBuffer(4)==0 && sets==1);
 reset();receive_response=set_response=W61_STATUS_ERROR;
 assert(W6X_Net_ConfigureReceiveBuffer(4)!=0 && sets==1);
 puts("PASS unsupported query may configure; real configuration rejection is never ignored");
 reset();receive_response=W61_STATUS_BUSY;assert(W6X_Net_ConfigureReceiveBuffer(4)==-2 && !sets);
 reset();receive_response=W61_STATUS_TIMEOUT;assert(W6X_Net_ConfigureReceiveBuffer(4)==-3 && !sets);
 puts("PASS uncertain timed-out query and BUSY cannot trigger a new configuration command");
 reset();ctx.Sockets[4].Ca_Cert=(void*)1;ctx.Sockets[4].PSK=(void*)2;
 assert(W6X_Net_Close(4)==0 && frees==2 && !stops && !queries && ctx.Sockets[4].Status==0);
 assert(W6X_Net_Close(4)==0 && frees==2);
 puts("PASS pre-open local failure returns its descriptor/credentials exactly once");
 reset();ctx.Sockets[4].Status=W6X_NET_SOCKET_CONNECTED;ctx.Sockets[4].OpenAttempted=1;
 ctx.Connection[2].SocketConnected=1;ctx.Sockets[4].Ca_Cert=(void*)1;
 remote_exists=1;close_response=W61_STATUS_ERROR;
 assert(W6X_Net_Close(4)!=0 && ctx.Sockets[4].Status==W6X_NET_SOCKET_CLOSING && !frees);
 remote_exists=0;ctx.Connection[2].DataAvailable=77;
 assert(W6X_Net_Close(4)==0 && stops==2 && frees==1 && sem_used==77);
 assert(ctx.Sockets[4].Status==0 && !ctx.Connection[2].SocketConnected);
 puts("PASS CLOSING retry retains identity until remote absence is proven, then frees once");
 reset();ctx.Sockets[4].OpenAttempted=1;remote_exists=1;
 assert(W6X_Net_Close(4)!=0 && stops==1 && ctx.Sockets[4].Status==W6X_NET_SOCKET_CLOSING);
 puts("PASS ambiguous CIPSTART cannot be discarded as merely ALLOCATED");
 reset();ctx.Sockets[4].Status=W6X_NET_SOCKET_CONNECTED;ctx.Sockets[4].OpenAttempted=1;
 ctx.Connection[2].SocketConnected=1;close_event=1;
 assert(W6X_Net_Close(4)==0 && stops==1 && !queries);
 puts("PASS CLOSED callback is sufficient proof; no stale close query or duplicate retirement");
 reset();ctx.Sockets[4].Status=W6X_NET_SOCKET_CONNECTED;ctx.Sockets[4].Number=6;
 assert(W6X_Net_Close(4)!=0 && !stops);
 assert(W6X_Net_Close(-1)!=0 && W6X_Net_Close(6)!=0);
 puts("PASS invalid connection/descriptor never indexes connection storage");
 return 0;
}
'''

def main():
    source = (ROOT / 'ThirdParty/ST67W6X_Network_Driver/Core/w6x_net.c').read_text(encoding='utf-8')
    code = '\n'.join(extract_function(source, name) for name in
                     ['W6X_Net_Clean_Socket', 'W6X_Net_Close', 'W6X_Net_ConfigureReceiveBuffer'])
    run_native(PREFIX + code + TESTS)

if __name__ == '__main__':
    main()
