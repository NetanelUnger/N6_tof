#ifndef N6_RESOURCE_DIAG_H
#define N6_RESOURCE_DIAG_H
#include <stdint.h>
#include <stdlib.h>
#include "app_features.h"
#include "tx_api.h"
#include "resource_memory_policy.h"
enum {N6R_CORE,N6R_RTOS,N6R_USB,N6R_TOF,N6R_CLOUD,N6R_RADIO,N6R_LOG,N6R_INIT,N6R_MODULES};
enum {N6R_ALLOC,N6R_ENQUEUE,N6R_CREATE,N6R_INVALID,N6R_OVERFLOW,N6R_RELEASE,N6R_MARGIN,N6R_WAIT,N6R_POLL,N6R_KINDS};
typedef struct {uint32_t count,status,site,argument,object,tick,flags;} N6R_Failure;
typedef struct {uintptr_t object;uint32_t capacity,peak,minimum,observations,flags;} N6R_Usage;
/* Debug_UART_Write returns0 on successful queueing, not accepted byte count. */
static inline int32_t N6R_QueuedBytes(int32_t status,size_t length)
{return status==0?(int32_t)length:-1;}
void N6R_Init(void); /* Once in main before any UART/pool/RTOS operation. */
void N6R_Record(uint32_t module,uint32_t kind,uint32_t status,uint32_t site,size_t argument,const void *object);
void N6R_Get(uint32_t module,uint32_t kind,N6R_Failure *out);
void N6R_ReportDeferred(void); /* Only UART consumer. Never ISR/SPI/fault. */
void N6R_ObservePool(TX_BYTE_POOL *pool);
void N6R_ObserveQueue(TX_QUEUE *queue);
void N6R_GetUsage(uint32_t pool,uint32_t index,N6R_Usage *out);
void N6R_ObserveCurrentStack(void); /* Instantaneous sample, NOT proven peak. */
void N6R_RequestUsage(void);
void N6R_ObserveHeap(void *bottom,uint32_t capacity,uint32_t frontier);

/* Inline calls below are expanded before interception macros: no recursion. */
static inline UINT N6R_QueueSend(TX_QUEUE *q,VOID *p,ULONG wait,uint32_t m,uint32_t line)
{UINT s=tx_queue_send(q,p,wait);if(s!=TX_SUCCESS)N6R_Record(m,N6R_ENQUEUE,s,line,wait,q);else N6R_ObserveQueue(q);return s;}
static inline UINT N6R_QueueReceive(TX_QUEUE *q,VOID *p,ULONG wait,uint32_t m,uint32_t line)
{N6R_ObserveCurrentStack();UINT s=tx_queue_receive(q,p,wait);if(s!=TX_SUCCESS)N6R_Record(m,(s==TX_QUEUE_EMPTY&&wait!=TX_WAIT_FOREVER)?N6R_POLL:N6R_WAIT,s,line,wait,q);return s;}
static inline UINT N6R_ByteAllocate(TX_BYTE_POOL *p,VOID **out,ULONG n,ULONG wait,uint32_t m,uint32_t line)
{UINT s=tx_byte_allocate(p,out,n,wait);if(s!=TX_SUCCESS)N6R_Record(m,N6R_ALLOC,s,line,n,p);else N6R_ObservePool(p);return s;}
static inline UINT N6R_BlockAllocate(TX_BLOCK_POOL *p,VOID **out,ULONG wait,uint32_t m,uint32_t line)
{UINT s=tx_block_allocate(p,out,wait);if(s!=TX_SUCCESS)N6R_Record(m,N6R_ALLOC,s,line,wait,p);return s;}
static inline UINT N6R_ByteRelease(VOID *p,uint32_t m,uint32_t line)
{UINT s=tx_byte_release(p);if(s!=TX_SUCCESS)N6R_Record(m,N6R_RELEASE,s,line,0,p);return s;}
static inline UINT N6R_BlockRelease(VOID *p,uint32_t m,uint32_t line)
{UINT s=tx_block_release(p);if(s!=TX_SUCCESS)N6R_Record(m,N6R_RELEASE,s,line,0,p);return s;}
static inline UINT N6R_QueueCreate(TX_QUEUE *q,CHAR *name,UINT words,VOID *p,ULONG n,uint32_t m,uint32_t line)
{UINT s=tx_queue_create(q,name,words,p,n);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,n,q);return s;}
static inline UINT N6R_ThreadCreate(TX_THREAD *t,CHAR *name,VOID (*entry)(ULONG),ULONG arg,VOID *stack,ULONG size,UINT priority,UINT threshold,ULONG slice,UINT start,uint32_t m,uint32_t line)
{UINT s=tx_thread_create(t,name,entry,arg,stack,size,priority,threshold,slice,start);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,size,t);return s;}
static inline UINT N6R_MutexCreate(TX_MUTEX*p,CHAR*n,UINT inherit,uint32_t m,uint32_t line)
{UINT s=tx_mutex_create(p,n,inherit);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,0,p);return s;}
static inline UINT N6R_SemCreate(TX_SEMAPHORE*p,CHAR*n,ULONG count,uint32_t m,uint32_t line)
{UINT s=tx_semaphore_create(p,n,count);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,count,p);return s;}
static inline UINT N6R_EventCreate(TX_EVENT_FLAGS_GROUP*p,CHAR*n,uint32_t m,uint32_t line)
{UINT s=tx_event_flags_create(p,n);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,0,p);return s;}
static inline UINT N6R_EventSet(TX_EVENT_FLAGS_GROUP*p,ULONG flags,UINT op,uint32_t m,uint32_t line)
{UINT s=tx_event_flags_set(p,flags,op);if(s!=TX_SUCCESS)N6R_Record(m,N6R_ENQUEUE,s,line,flags,p);return s;}
static inline UINT N6R_BytePoolCreate(TX_BYTE_POOL*p,CHAR*n,VOID*memory,ULONG size,uint32_t m,uint32_t line)
{UINT s=tx_byte_pool_create(p,n,memory,size);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,size,p);else N6R_ObservePool(p);return s;}
static inline UINT N6R_BlockPoolCreate(TX_BLOCK_POOL*p,CHAR*n,ULONG block,VOID*memory,ULONG size,uint32_t m,uint32_t line)
{UINT s=tx_block_pool_create(p,n,block,memory,size);if(s!=TX_SUCCESS)N6R_Record(m,N6R_CREATE,s,line,size,p);return s;}
static inline void *N6R_MallocAt(size_t n,uint32_t m,uint32_t line)
{void *p=malloc(n);if(!p&&n)N6R_Record(m,N6R_ALLOC,0x100U,line,n,0);return p;}
static inline void *N6R_CallocAt(size_t n,size_t width,uint32_t m,uint32_t line)
{size_t total;if(!N6_CheckedMultiply(n,width,&total)){N6R_Record(m,N6R_OVERFLOW,0x101U,line,n,0);return NULL;}void *p=calloc(n,width);if(!p&&total)N6R_Record(m,N6R_ALLOC,0x100U,line,total,0);return p;}
static inline void *N6R_ReallocAt(void *old,size_t n,uint32_t m,uint32_t line)
{void *p=realloc(old,n);if(!p&&n)N6R_Record(m,N6R_ALLOC,0x100U,line,n,old);return p;}

#if (N6_RESOURCE_DIAGNOSTICS == 1U) && defined(N6_RESOURCE_SOURCE) && !defined(N6_RESOURCE_IMPLEMENTATION)
#undef tx_queue_send
#undef tx_queue_receive
#undef tx_byte_allocate
#undef tx_block_allocate
#undef tx_byte_release
#undef tx_block_release
#undef tx_queue_create
#undef tx_thread_create
#undef tx_mutex_create
#undef tx_semaphore_create
#undef tx_event_flags_create
#undef tx_event_flags_set
#undef tx_byte_pool_create
#undef tx_block_pool_create
#define tx_queue_send(q,p,w) N6R_QueueSend(q,p,w,N6_RESOURCE_SOURCE,__LINE__)
#define tx_queue_receive(q,p,w) N6R_QueueReceive(q,p,w,N6_RESOURCE_SOURCE,__LINE__)
#define tx_byte_allocate(p,o,n,w) N6R_ByteAllocate(p,o,n,w,N6_RESOURCE_SOURCE,__LINE__)
#define tx_block_allocate(p,o,w) N6R_BlockAllocate(p,o,w,N6_RESOURCE_SOURCE,__LINE__)
#define tx_byte_release(p) N6R_ByteRelease(p,N6_RESOURCE_SOURCE,__LINE__)
#define tx_block_release(p) N6R_BlockRelease(p,N6_RESOURCE_SOURCE,__LINE__)
#define tx_queue_create(q,s,n,p,z) N6R_QueueCreate(q,s,n,p,z,N6_RESOURCE_SOURCE,__LINE__)
#define tx_thread_create(t,n,e,a,s,z,p,h,l,b) N6R_ThreadCreate(t,n,e,a,s,z,p,h,l,b,N6_RESOURCE_SOURCE,__LINE__)
#define tx_mutex_create(p,n,i) N6R_MutexCreate(p,n,i,N6_RESOURCE_SOURCE,__LINE__)
#define tx_semaphore_create(p,n,i) N6R_SemCreate(p,n,i,N6_RESOURCE_SOURCE,__LINE__)
#define tx_event_flags_create(p,n) N6R_EventCreate(p,n,N6_RESOURCE_SOURCE,__LINE__)
#define tx_event_flags_set(p,f,o) N6R_EventSet(p,f,o,N6_RESOURCE_SOURCE,__LINE__)
#define tx_byte_pool_create(p,n,m,s) N6R_BytePoolCreate(p,n,m,s,N6_RESOURCE_SOURCE,__LINE__)
#define tx_block_pool_create(p,n,b,m,s) N6R_BlockPoolCreate(p,n,b,m,s,N6_RESOURCE_SOURCE,__LINE__)
#define N6R_Malloc(n) N6R_MallocAt(n,N6_RESOURCE_SOURCE,__LINE__)
#define N6R_Calloc(n,w) N6R_CallocAt(n,w,N6_RESOURCE_SOURCE,__LINE__)
#define N6R_Realloc(p,n) N6R_ReallocAt(p,n,N6_RESOURCE_SOURCE,__LINE__)
#endif
#if (N6_RESOURCE_DIAGNOSTICS == 0U)
#define N6R_Init() ((void)0)
#define N6R_Record(...) ((void)0)
#define N6R_ObservePool(...) ((void)0)
#define N6R_ObserveQueue(...) ((void)0)
#define N6R_ObserveHeap(...) ((void)0)
#define N6R_ReportDeferred() ((void)0)
#define N6R_ObserveCurrentStack() ((void)0)
#define N6R_RequestUsage() ((void)0)
#define N6R_Malloc malloc
#define N6R_Calloc calloc
#define N6R_Realloc realloc
#endif
#endif
