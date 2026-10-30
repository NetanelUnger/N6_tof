"""Actual compatibility queue constructor: reject wrap before backing allocation."""
from pathlib import Path
from test_xip_boot import run_native
from test_resource_diagnostics import STUB

def main():
    root=Path(__file__).resolve().parents[1]
    source=(root/'AppliNonSecure/Core/Src/freertos_compat.c').read_text()
    start=source.index('QueueHandle_t xQueueCreate(')
    body=source[start:source.index('BaseType_t xQueueSend(',start)]
    prefix=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define N6_RESOURCE_DIAGNOSTICS 1
#define N6_RESOURCE_SOURCE N6R_RTOS
#include "resource_diag.h"
typedef uint32_t UBaseType_t;
#define TX_16_ULONG 16
#define TX_PTR_ERROR 4
struct freertos_compat_queue {TX_QUEUE queue;void *storage;UINT message_words;};
typedef struct freertos_compat_queue *QueueHandle_t;
static struct freertos_compat_queue control;static char storage[128];static unsigned allocated,freed,overflow;
static size_t last_allocation;
static void *pvPortMalloc(size_t n){last_allocation=n;return allocated++?(void*)storage:(void*)&control;}
static void vPortFree(void*p){freed++;}
void N6R_Record(uint32_t m,uint32_t k,uint32_t s,uint32_t l,size_t n,const void*p){if(k==N6R_OVERFLOW)overflow++;}
void N6R_ObserveQueue(TX_QUEUE*p){}
void N6R_ObservePool(TX_BYTE_POOL*p){}
void N6R_ObserveCurrentStack(void){}
'''
    test=r'''
int main(void){
assert(xQueueCreate(1,UINT32_MAX)==NULL&&allocated==0&&overflow==1);
assert(xQueueCreate(UINT32_MAX,4)==NULL&&allocated==1&&freed==1&&overflow==2);
allocated=freed=0;injected=0;QueueHandle_t q=xQueueCreate(8,4);
assert(q==&control&&allocated==2&&last_allocation==32&&q->message_words==1);
puts("PASS actual queue size overflow before backing allocation; control cleanup; valid queue exact size");}
'''
    run_native(prefix+body+test,extra_stubs={'tx_api.h':STUB},extra_includes=[root/'AppliNonSecure/Core/Inc'],retain_artifacts=True)
if __name__=='__main__':main()
