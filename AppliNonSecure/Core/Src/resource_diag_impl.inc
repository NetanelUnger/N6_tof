/* Compiled once in debug_uart.c. No formatter, allocation, queue or I/O in
 * capture. Reporter uses a fixed hex encoder and retries only after1second.
 * Counters survive logger backpressure and NCP recovery; not power loss.
 */
_Static_assert(11U+9U*9U+2U<=96U,"resource report must fit fixed line");
#ifndef N6R_HOST
#define N6R_STORAGE __attribute__((section(".app_shared_bss"),aligned(64)))
#define N6R_LOCK() __get_PRIMASK()
#define N6R_DISABLE() __disable_irq()
#define N6R_UNLOCK(p) __set_PRIMASK(p)
#define N6R_ISR() __get_IPSR()
#define N6R_NOW() HAL_GetTick()
#define N6R_SINK(p,n) Debug_UART_Write(p,n)
#endif
static volatile N6R_Failure n6r_failures[N6R_MODULES][N6R_KINDS] N6R_STORAGE;
static uint32_t n6r_reported[N6R_MODULES][N6R_KINDS] N6R_STORAGE;
static N6R_Usage n6r_pools[8] N6R_STORAGE;
static N6R_Usage n6r_queues[32] N6R_STORAGE;
static N6R_Usage n6r_stacks[24] N6R_STORAGE;
static uint32_t n6r_report_tick,n6r_report_cursor,n6r_reporting;
static volatile uint32_t n6r_usage_generation;
static uint32_t n6r_usage_seen,n6r_usage_request,n6r_usage_cursor;
void N6R_Record(uint32_t m,uint32_t k,uint32_t status,uint32_t site,size_t argument,const void *object)
{
  uint32_t posture=N6R_LOCK();N6R_DISABLE();
  if(m>=N6R_MODULES||k>=N6R_KINDS){m=N6R_CORE;k=N6R_INVALID;}
  volatile N6R_Failure *f=&n6r_failures[m][k];
  if(f->count!=UINT32_MAX)++f->count;else if(!(f->flags&2U)){f->flags|=2U;n6r_reported[m][k]=UINT32_MAX-1U;}
  f->status=status;f->site=site;f->argument=(uint32_t)argument;f->object=(uint32_t)(uintptr_t)object;
  f->tick=N6R_NOW();if(N6R_ISR())f->flags|=1U;
  N6R_UNLOCK(posture);
}
void N6R_Get(uint32_t m,uint32_t k,N6R_Failure *out)
{
  if(!out||m>=N6R_MODULES||k>=N6R_KINDS)return;
  uint32_t posture=N6R_LOCK();N6R_DISABLE();*out=n6r_failures[m][k];N6R_UNLOCK(posture);
}
static void n6r_observe(N6R_Usage *rows,uint32_t length,void *object,uint32_t capacity,uint32_t used)
{
  uint32_t posture=N6R_LOCK();N6R_DISABLE();
  for(uint32_t i=0;i<length;++i)if(rows[i].object==(uintptr_t)object||rows[i].object==0){
    N6R_Usage *p=&rows[i];if(!p->object){p->object=(uintptr_t)object;p->minimum=capacity;}
    p->capacity=capacity;if(used>p->peak)p->peak=used;
    uint32_t free=used<=capacity?capacity-used:0;if(free<p->minimum)p->minimum=free;
    if(p->observations!=UINT32_MAX)++p->observations;N6R_UNLOCK(posture);return;
  }
  N6R_UNLOCK(posture);N6R_Record(N6R_CORE,N6R_OVERFLOW,0x102U,0,length,object);
}
void N6R_ObservePool(TX_BYTE_POOL *p)
{if(p){
  uint32_t size=p->tx_byte_pool_size,available=p->tx_byte_pool_available;
  if(available>size){N6R_Record(N6R_CORE,N6R_OVERFLOW,0x104U,0,available,p);return;}
  n6r_observe(n6r_pools,8,p,size,size-available);
  if((uint64_t)available*10ULL<(size-available))N6R_Record(N6R_CORE,N6R_MARGIN,0x105U,0,available,p);
}}
void N6R_ObserveQueue(TX_QUEUE *p)
{if(p)n6r_observe(n6r_queues,32,p,p->tx_queue_capacity,p->tx_queue_enqueued);}
void N6R_ObserveHeap(void *bottom,uint32_t capacity,uint32_t frontier)
{
  n6r_observe(n6r_pools,8,bottom,capacity,frontier);
  uint32_t posture=N6R_LOCK();N6R_DISABLE();
  for(uint32_t i=0;i<8;++i)if(n6r_pools[i].object==(uintptr_t)bottom)n6r_pools[i].flags|=8U;
  N6R_UNLOCK(posture);
  if(frontier>capacity||(uint64_t)(capacity-frontier)*10ULL<frontier)
    N6R_Record(N6R_CORE,N6R_MARGIN,0x108U,0,frontier,bottom);
}
void N6R_GetUsage(uint32_t pool,uint32_t index,N6R_Usage *out)
{
  if(!out||pool>2U||index>=(pool==2U?24U:pool?8U:32U))return;
  uint32_t posture=N6R_LOCK();N6R_DISABLE();*out=pool==2U?n6r_stacks[index]:pool?n6r_pools[index]:n6r_queues[index];N6R_UNLOCK(posture);
}
static void n6r_stack_sample(void *t,uintptr_t bottom,uint32_t size,uintptr_t sp)
{
  if(sp<bottom||sp-bottom>size){N6R_Record(N6R_CORE,N6R_OVERFLOW,0x106U,0,size,t);return;}
  uint32_t used=size-(uint32_t)(sp-bottom);
  n6r_observe(n6r_stacks,24,t,size,used);
  uint32_t required;if(!N6_CheckedStackBytes(used,&required)||required>size)
    N6R_Record(N6R_CORE,N6R_MARGIN,0x107U,0,used,t);
}
void N6R_ObserveCurrentStack(void)
{
#ifndef N6R_HOST
  if(N6R_ISR())return;
  TX_THREAD *t=tx_thread_identify();if(!t)return;
  n6r_stack_sample(t,(uintptr_t)t->tx_thread_stack_start,t->tx_thread_stack_size,__get_PSP());
#endif
}
void N6R_RequestUsage(void){uint32_t p=N6R_LOCK();N6R_DISABLE();++n6r_usage_generation;N6R_UNLOCK(p);}
static char *n6r_hex(char *out,uint32_t value)
{static const char hex[]="0123456789ABCDEF";for(int bit=28;bit>=0;bit-=4)*out++=hex[(value>>bit)&15U];*out++=' ';return out;}
void N6R_ReportDeferred(void)
{
  uint32_t now=N6R_NOW();if(N6R_ISR()||n6r_reporting||now-n6r_report_tick<1000U)return;
  n6r_reporting=1;n6r_report_tick=now;
  uint32_t attempted=0;
  if(n6r_usage_seen!=n6r_usage_generation){n6r_usage_seen=n6r_usage_generation;n6r_usage_cursor=0;n6r_usage_request=1;}
  for(uint32_t scan=0;scan<N6R_MODULES*N6R_KINDS;++scan){
    uint32_t index=n6r_report_cursor++%(N6R_MODULES*N6R_KINDS),m=index/N6R_KINDS,k=index%N6R_KINDS;
    if(k==N6R_POLL)continue; /* Expected empty polls are counted, not spammed. */
    N6R_Failure f;N6R_Get(m,k,&f);if(f.count==n6r_reported[m][k])continue;
    char line[96]="[RESOURCE] ";char *p=line+11;
    p=n6r_hex(p,m);p=n6r_hex(p,k);p=n6r_hex(p,f.count);p=n6r_hex(p,f.status);
    p=n6r_hex(p,f.site);p=n6r_hex(p,f.argument);p=n6r_hex(p,f.object);p=n6r_hex(p,f.tick);p=n6r_hex(p,f.flags);
    *p++='\r';*p++='\n';
    attempted=1;if(N6R_SINK(line,(size_t)(p-line))==(int32_t)(p-line))n6r_reported[m][k]=f.count;
    break; /* One attempt/second including failures, never recursive. */
  }
  if(n6r_usage_request&&!attempted){
    /* One usage row only if no failure row was attempted this interval. */
    for(uint32_t scan=0;scan<64;++scan){
      if(n6r_usage_cursor>=64){n6r_usage_request=0;break;}
      uint32_t i=n6r_usage_cursor,kind=i<8?1U:i<40?0U:2U,index=i<8?i:i<40?i-8:i-40;
      N6R_Usage u={0};N6R_GetUsage(kind,index,&u);if(!u.object){++n6r_usage_cursor;continue;}
      char line[96]="[RESOURCE] ";char *p=line+11;
      p=n6r_hex(p,255);p=n6r_hex(p,256+kind);p=n6r_hex(p,u.observations);p=n6r_hex(p,u.capacity);
      p=n6r_hex(p,u.peak);p=n6r_hex(p,u.minimum);p=n6r_hex(p,(uint32_t)u.object);p=n6r_hex(p,kind==2U?4U:u.flags);
      *p++='\r';*p++='\n';if(N6R_SINK(line,(size_t)(p-line))==(int32_t)(p-line))++n6r_usage_cursor;
      break;
    }
  }
  n6r_reporting=0;
}
