"""Actual Cloud reply publication, command hold and lease-return regressions."""
from test_cli_reply_ownership import function
from test_wifi_scan_lifetime import ROOT, run_native

PREFIX=r'''
#include <assert.h>
#include <stdio.h>
typedef unsigned UINT;typedef int TX_THREAD;typedef int TX_MUTEX;
#define TX_SUCCESS 0U
#define TX_NOT_AVAILABLE 1U
#define TX_QUEUE_FULL 2U
#define TX_PTR_ERROR 3U
#define TX_SIZE_ERROR 4U
#define TX_NO_WAIT 0U
#define TX_INT_DISABLE 1U
#define CLOUD_OUTPUT_SLOT_COUNT 8U
#define CLOUD_OUTPUT_SLOT_SIZE 384U
typedef struct {uint16_t length;uint32_t binary,input_sequence,completed;uint8_t data[384];} CloudOutputSlot_t;
typedef struct {char command_id[81];uint32_t sequence;} CloudRelay_Input_t;
static struct {TX_MUTEX gate;struct{unsigned generation;}status;
 char active_command_id[81],ack_command_id[81];
 unsigned output_count,output_head,output_tail,input_ready,input_delivered,hold_command,ack_pending,ack_sequence;
 CloudOutputSlot_t *output;AppCliReply_t reply;TX_THREAD *reply_owner;CloudRelay_Input_t input;
} context,*cloud=&context;
static CloudOutputSlot_t slots[8];static int busy,held,irq;static TX_THREAD task=1,other=2,*current=&task;
static TX_THREAD *tx_thread_identify(void){return current;}
static UINT tx_mutex_get(TX_MUTEX*m,unsigned wait){(void)m;assert(!wait);if(busy)return 1;assert(!held);held=1;return 0;}
static UINT tx_mutex_put(TX_MUTEX*m){(void)m;assert(held);held=0;return 0;}
static UINT tx_interrupt_control(UINT n){unsigned old=irq;irq=n;return old;}
static void reset(void){memset(&context,0,sizeof context);memset(slots,0,sizeof slots);context.output=slots;strcpy(context.active_command_id,"command-one");strcpy(context.input.command_id,"command-one");context.status.generation=4;context.input.sequence=2;context.input_ready=context.input_delivered=1;busy=held=irq=0;current=&task;}
'''
TESTS=r'''
int main(void){
 reset();assert(!CloudRelay_BeginReply() && context.hold_command);
 for(unsigned i=0;i<60;i++)assert(!CloudRelay_WriteOutput("line\r\n",6,0));
 assert(!context.output_count && context.reply.bytes==360);
 assert(CloudRelay_CompleteCommand()!=0 && !context.output_count);
 assert(!CloudRelay_EndReply(1) && context.output_count==2);
 assert(!CloudRelay_AcknowledgeInput(&context.input,1) && context.hold_command);
 assert(!CloudRelay_CompleteCommand() && slots[2].completed && context.output_count==3);
 puts("PASS unpublished packed reply cannot complete or release command identity before ACK/output ownership");
 reset();context.output_count=7;assert(CloudRelay_BeginReply()==TX_QUEUE_FULL);
 assert(!CloudRelay_ReturnInput(&context.input) && !context.input_delivered && context.input_ready);
 puts("PASS output contention returns the same unexecuted input lease for later admission");
 reset();assert(!CloudRelay_BeginReply());assert(!CloudRelay_WriteOutput("kept",4,0));busy=1;
 assert(CloudRelay_EndReply(1)!=0 && context.reply.active && !context.output_count);
 assert(!CloudRelay_AcknowledgeInput(&context.input,1));busy=0;
 assert(CloudRelay_CompleteCommand()!=0 && !context.output_count);
 assert(!CloudRelay_EndReply(1) && strstr((char*)slots[0].data,"state=complete"));
 puts("PASS busy publication retains bytes and hold after ACK; retry completes without duplicate trailer");
 reset();assert(!CloudRelay_BeginReply());char large[2944];memset(large,'x',sizeof large);
 assert(!CloudRelay_WriteOutput(large,sizeof large,0));assert(CloudRelay_WriteOutput("xx",2,0)==TX_SIZE_ERROR);
 assert(context.reply.bytes==sizeof large && !context.output_count);assert(!CloudRelay_EndReply(1));
 assert(context.output_count==8 && strstr((char*)slots[7].data,"state=failed reason=OUTPUT_LIMIT"));
 assert(CloudRelay_CompleteCommand()==TX_QUEUE_FULL);--context.output_count;
 assert(!CloudRelay_CompleteCommand());
 puts("PASS overflow has explicit failure and completion marker waits for existing slot rather than growing queue");
 reset();assert(!CloudRelay_BeginReply());assert(!CloudRelay_WriteOutput("old",3,0));context.status.generation++;
 assert(CloudRelay_EndReply(1)==TX_NOT_AVAILABLE && !context.output_count && !context.reply.active);
 puts("PASS logical capability replacement discards old reply before publishing to another command/session");
 reset();assert(!CloudRelay_BeginReply());current=&other;
 assert(CloudRelay_WriteOutput("wrong",5,0)==TX_NOT_AVAILABLE && context.reply.bytes==0);
 assert(CloudRelay_EndReply(1)==TX_NOT_AVAILABLE);current=&task;
 assert(CloudRelay_WriteOutput("binary",6,1)==TX_NOT_AVAILABLE);assert(!CloudRelay_EndReply(0));
 puts("PASS foreign producer and binary OTA cannot borrow an ordinary text reply lease");
 reset();CloudRelay_Input_t stale=context.input;stale.sequence++;
 assert(CloudRelay_ReturnInput(&stale)!=0 && context.input_delivered);
 strcpy(stale.command_id,"other");stale.sequence=context.input.sequence;
 assert(CloudRelay_ReturnInput(&stale)!=0 && context.input_delivered);
 puts("PASS return/ACK identity guards reject old sequence and old command");
 reset();assert(!CloudRelay_BeginReply());assert(!CloudRelay_WriteOutput("partial",7,0));
 busy=1;assert(CloudRelay_WriteOutput("lost",4,0)!=0);busy=0;
 assert(!CloudRelay_EndReply(3));assert(strstr((char*)slots[0].data,"state=failed reason=WRITE_ERROR"));
 puts("PASS busy handler write is reported as failure rather than successful truncated response");
 reset();assert(!CloudRelay_BeginReply());busy=1;
 assert(CloudRelay_CancelReply()!=0 && context.reply.active);busy=0;
 assert(!CloudRelay_CancelReply() && !context.reply.active && !context.output_count);
 assert(!CloudRelay_CancelReply());assert(!CloudRelay_BeginReply());
 puts("PASS cancellation retries mutex contention, is idempotent, and cannot strand the next generation");
 reset();assert(!CloudRelay_BeginReply());char controls[384];memset(controls,1,sizeof controls);
 assert(!CloudRelay_WriteOutput(controls,sizeof controls,0));assert(!CloudRelay_EndReply(1));
 assert(context.output_count==1 && strstr((char*)slots[0].data,"state=failed reason=ENCODING_LIMIT"));
 puts("PASS JSON escaping limit emits a bounded explicit failure instead of endless output backoff");
 return 0;
}
'''

def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    header=(ROOT/'AppliNonSecure/Core/Inc/app_cli_reply.h').read_text()
    code='\n'.join(function(source,name) for name in ['CloudRelay_ReturnInput','CloudRelay_AcknowledgeInput','CloudRelay_BeginReply','CloudRelay_CancelReply','CloudRelay_EndReply','CloudRelay_WriteOutput','CloudRelay_CompleteCommand'])
    run_native(header+PREFIX+code+TESTS)

if __name__=='__main__':main()
