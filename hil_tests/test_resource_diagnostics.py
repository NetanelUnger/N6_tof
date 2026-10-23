"""Actual scalar capture, ThreadX wrappers and reporter with injected failures."""
from pathlib import Path
from test_xip_boot import run_native

STUB=r'''
#include <stdint.h>
typedef unsigned UINT;typedef uint32_t ULONG;typedef void VOID;typedef char CHAR;
typedef struct {uint32_t tx_queue_capacity,tx_queue_enqueued;} TX_QUEUE;
typedef struct {uint32_t tx_byte_pool_size,tx_byte_pool_available;} TX_BYTE_POOL;
typedef struct {int unused;} TX_BLOCK_POOL;typedef struct {int unused;} TX_THREAD;
typedef struct {int unused;} TX_MUTEX;typedef struct {int unused;} TX_SEMAPHORE;typedef struct {int unused;} TX_EVENT_FLAGS_GROUP;
#define TX_SUCCESS 0
#define TX_QUEUE_EMPTY 3
#define TX_NO_WAIT 0
static unsigned injected;
static UINT tx_queue_send(TX_QUEUE*q,void*p,ULONG w){if(!injected)q->tx_queue_enqueued++;return injected;}
static UINT tx_queue_receive(TX_QUEUE*q,void*p,ULONG w){return injected;}
static UINT tx_byte_allocate(TX_BYTE_POOL*p,void**o,ULONG n,ULONG w){if(!injected){p->tx_byte_pool_available-=n;*o=p;}return injected;}
static UINT tx_block_allocate(TX_BLOCK_POOL*p,void**o,ULONG w){return injected;}
static UINT tx_byte_release(void*p){return injected;}
static UINT tx_block_release(void*p){return injected;}
static UINT tx_queue_create(TX_QUEUE*q,char*n,UINT w,void*p,ULONG s){return injected;}
static UINT tx_thread_create(TX_THREAD*t,char*n,void(*e)(ULONG),ULONG a,void*s,ULONG z,UINT p,UINT h,ULONG l,UINT b){return injected;}
static UINT tx_mutex_create(TX_MUTEX*p,char*n,UINT i){return injected;}
static UINT tx_semaphore_create(TX_SEMAPHORE*p,char*n,ULONG i){return injected;}
static UINT tx_event_flags_create(TX_EVENT_FLAGS_GROUP*p,char*n){return injected;}
static UINT tx_event_flags_set(TX_EVENT_FLAGS_GROUP*p,ULONG f,UINT o){return injected;}
static UINT tx_byte_pool_create(TX_BYTE_POOL*p,char*n,void*m,ULONG s){return injected;}
static UINT tx_block_pool_create(TX_BLOCK_POOL*p,char*n,ULONG b,void*m,ULONG s){return injected;}
'''
HARNESS=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static void *failed_malloc(size_t n){return NULL;}
static void *failed_calloc(size_t n,size_t s){return NULL;}
static void *failed_realloc(void*p,size_t n){return NULL;}
#define malloc failed_malloc
#define calloc failed_calloc
#define realloc failed_realloc
#define N6_RESOURCE_DIAGNOSTICS 1
#define N6_RESOURCE_SOURCE N6R_USB
#include "resource_diag.h"
static uint32_t mask,tick,ipsr,sinks;static int sink_fails;static size_t last_length;
static int32_t sink(const void*p,size_t n){sinks++;last_length=n;assert(n<=96);if(sink_fails){N6R_Record(N6R_LOG,N6R_ENQUEUE,7,1,n,0);N6R_ReportDeferred();return -1;}return 0;}
#define N6R_HOST 1
#define N6R_STORAGE
#define N6R_LOCK() mask
#define N6R_DISABLE() (mask=1)
#define N6R_UNLOCK(p) (mask=(p))
#define N6R_ISR() ipsr
#define N6R_NOW() tick
#define N6R_SINK(p,n) N6R_QueuedBytes(sink(p,n),n)
#include "resource_diag_impl.inc"
int main(void){
assert(N6R_QueuedBytes(0,94)==94&&N6R_QueuedBytes(-1,94)==-1&&N6R_QueuedBytes(-6,94)==-1);
/* Model cold/retained NOLOAD SRAM, not host-C static zero initialization. */
memset((void*)n6r_failures,0xA5,sizeof(n6r_failures));
memset(n6r_reported,0xC3,sizeof(n6r_reported));
memset(n6r_pools,0x5A,sizeof(n6r_pools));memset(n6r_queues,0x5A,sizeof(n6r_queues));memset(n6r_stacks,0x5A,sizeof(n6r_stacks));
N6R_ReportDeferred();assert(sinks==0);N6R_Init();
for(unsigned m=0;m<N6R_MODULES;m++)for(unsigned k=0;k<N6R_KINDS;k++)assert(n6r_failures[m][k].count==0&&n6r_failures[m][k].flags==0&&n6r_reported[m][k]==0);
for(unsigned i=0;i<8;i++)assert(n6r_pools[i].object==0);
for(unsigned i=0;i<32;i++)assert(n6r_queues[i].object==0);
for(unsigned i=0;i<24;i++)assert(n6r_stacks[i].object==0);
size_t n;uint32_t stack;
assert(N6_CheckedMultiply(20,4,&n)&&n==80);assert(!N6_CheckedMultiply(SIZE_MAX,2,&n));
assert(N6_CheckedStackBytes(1024,&stack)&&stack==1536);assert(!N6_CheckedStackBytes(SIZE_MAX,&stack));
assert(N6_STACK_BYTES(776)>=((776+208+128)*110+99)/100);
uintptr_t next;
assert(N6_CheckedHeapMove(110,100,200,20,&next)&&next==130);
assert(N6_CheckedHeapMove(110,100,200,-10,&next)&&next==100);
assert(!N6_CheckedHeapMove(110,100,200,-11,&next));
assert(!N6_CheckedHeapMove(110,100,200,PTRDIFF_MIN,&next));
assert(!N6_CheckedHeapMove(UINTPTR_MAX-1,100,UINTPTR_MAX,2,&next));
TX_QUEUE q={4,0};TX_BYTE_POOL pool={100,100};void *p=0;
injected=7;assert(tx_queue_send(&q,&p,0)==7);N6R_Failure f;N6R_Get(N6R_USB,N6R_ENQUEUE,&f);
assert(f.count==1&&f.status==7&&sinks==0);assert(tx_byte_allocate(&pool,&p,10,0)==7);
N6R_Get(N6R_USB,N6R_ALLOC,&f);assert(f.count==1&&f.argument==10);
assert(tx_queue_create(&q,"x",1,&p,4)==7);assert(tx_byte_release(&p)==7);
TX_MUTEX mutex;TX_SEMAPHORE sem;TX_EVENT_FLAGS_GROUP event;
assert(tx_mutex_create(&mutex,"m",0)==7&&tx_semaphore_create(&sem,"s",0)==7&&tx_event_flags_create(&event,"e")==7);
TX_BLOCK_POOL block;TX_THREAD thread;
assert(tx_byte_pool_create(&pool,"p",&p,100)==7&&tx_block_pool_create(&block,"b",4,&p,100)==7);
assert(tx_thread_create(&thread,"t",0,0,&p,64,1,1,0,1)==7&&tx_event_flags_set(&event,1,0)==7);
injected=0;assert(tx_queue_send(&q,&p,0)==0);assert(tx_byte_allocate(&pool,&p,80,0)==0);
N6R_Usage u;N6R_GetUsage(1,0,&u);assert(u.peak==80&&u.minimum==20);
N6R_GetUsage(0,0,&u);assert(u.peak==1&&u.capacity==4);
pool.tx_byte_pool_available=5;N6R_ObservePool(&pool);N6R_Get(N6R_CORE,N6R_MARGIN,&f);assert(f.count==1);
ipsr=4;mask=1;N6R_Record(N6R_TOF,N6R_OVERFLOW,9,99,33,&q);assert(mask==1&&sinks==0);ipsr=0;mask=0;
N6R_Get(N6R_TOF,N6R_OVERFLOW,&f);assert((f.flags&1)&&f.site==99);
sink_fails=1;tick=1000;N6R_ReportDeferred();assert(sinks==1);
uint32_t seen=0;for(unsigned m=0;m<N6R_MODULES;m++)for(unsigned k=0;k<N6R_KINDS;k++)seen+=n6r_reported[m][k];assert(seen==0);
N6R_ReportDeferred();assert(sinks==1);sink_fails=0;tick=2000;N6R_ReportDeferred();assert(sinks==2&&last_length<96);
for(unsigned m=0;m<N6R_MODULES;m++)for(unsigned k=0;k<N6R_KINDS;k++)seen+=n6r_reported[m][k];assert(seen>0);
uint32_t before=sinks;ipsr=3;tick=4000;N6R_ReportDeferred();assert(sinks==before);ipsr=0;
N6R_RequestUsage();tick=5000;N6R_ReportDeferred();assert(sinks==before+1); /* failure+usage never2attempts */
n6r_failures[N6R_TOF][N6R_OVERFLOW].count=UINT32_MAX;N6R_Record(N6R_TOF,N6R_OVERFLOW,1,1,1,0);
N6R_Get(N6R_TOF,N6R_OVERFLOW,&f);assert(f.count==UINT32_MAX&&(f.flags&2));
TX_QUEUE queues[33];for(unsigned i=0;i<33;i++){queues[i].tx_queue_capacity=4;queues[i].tx_queue_enqueued=2;N6R_ObserveQueue(&queues[i]);}
N6R_Get(N6R_CORE,N6R_OVERFLOW,&f);assert(f.count>=1);
assert(N6R_Calloc(SIZE_MAX,2)==NULL);N6R_Get(N6R_USB,N6R_OVERFLOW,&f);assert(f.count==1);
char old[2]={0x55,0};assert(N6R_Malloc(3)==NULL&&N6R_Calloc(2,3)==NULL&&N6R_Realloc(old,4)==NULL&&old[0]==0x55);
N6R_Get(N6R_USB,N6R_ALLOC,&f);assert(f.count==4);
n6r_stack_sample(&q,0x1000,2048,0x1400);N6R_GetUsage(2,0,&u);assert(u.peak==1024&&u.minimum==1024);
n6r_stack_sample(&q,0x1000,2048,0x1080);N6R_GetUsage(2,0,&u);assert(u.peak==1920);
n6r_stack_sample(&q,0x1000,2048,0xFFF);N6R_Get(N6R_CORE,N6R_OVERFLOW,&f);assert(f.status==0x106U);
N6R_ObserveHeap((void*)0x10000,1000,100);N6R_GetUsage(1,1,&u);assert(u.peak==100&&(u.flags&8));
puts("PASS capture independent of sink; enqueue/alloc/create/release/overflow injection; ISR posture; saturation; highwater; one attempt/sec; log-full retry; checked10percent alignment");
uint32_t saved=n6r_failures[N6R_USB][N6R_ALLOC].count;N6R_Init();assert(n6r_failures[N6R_USB][N6R_ALLOC].count==saved);
puts("PASS dirty NOLOAD tables explicitly initialized before use; repeat init preserves counters");
}
'''
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    startup=(root/'AppliNonSecure/Core/Src/main.c').read_text()
    assert startup.index('N6R_Init();')<startup.index('(void)Debug_UART_Init();')<startup.index('  MX_ThreadX_Init();')
    run_native(HARNESS,extra_stubs={'tx_api.h':STUB},extra_includes=[root/'AppliNonSecure/Core/Inc',root/'AppliNonSecure/Core/Src'],retain_artifacts=True)
