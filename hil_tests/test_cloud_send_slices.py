"""Execute Cloud's actual send loop with partial writes and receive headroom.

The send boundary models allocation admission, not the ThreadX allocator or RF.
Live HIL remains required to establish actual simultaneous SPI TX/RX headroom.
"""
import re
from test_wifi_scan_lifetime import ROOT, run_native
from test_wifi_assoc_admission import extract_function

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef long ssize_t;
static uint8_t input[9092], received[9092];
static size_t offset, calls, partial, fail_after;
static int failure;
static ssize_t W6X_Net_Send(int socket,const void *data,size_t length,int flags) {
 assert(socket==5 && flags==0 && length>0 && length<=512);
 /* A MTU-sized TX used to consume the contiguous space needed by RX. */
 assert(length+64+1560<=2304);
 assert(data==input+offset); ++calls;
 if (failure && offset>=fail_after) return failure;
 size_t accepted=partial && length>partial ? partial : length;
 assert(offset+accepted<=sizeof received);
 memcpy(received+offset,data,accepted);offset+=accepted;
 return (ssize_t)accepted;
}
static void reset(void) {offset=calls=partial=fail_after=0;failure=0;memset(received,0,sizeof received);}
'''
TESTS = r'''
int main(void) {
 for(size_t i=0;i<sizeof input;i++)input[i]=(uint8_t)(i*37);
 reset();assert(cloud_send_all(5,input,sizeof input)==0);
 assert(offset==sizeof input && calls==18 && !memcmp(input,received,sizeof input));
 puts("PASS image body preserves exact bytes while each TX leaves modeled RX headroom");
 reset();partial=73;assert(cloud_send_all(5,input,sizeof input)==0);
 assert(offset==sizeof input && !memcmp(input,received,sizeof input));
 puts("PASS partial sends retain exact cursor and final short slice");
 reset();assert(cloud_send_all(5,input,0)==0 && calls==0);
 assert(cloud_send_all(5,input,7)==0 && calls==1 && offset==7);
 puts("PASS empty and short HTTP components need no padding or extra send");
 reset();failure=-1;fail_after=512;assert(cloud_send_all(5,input,sizeof input)==-1);
 assert(calls==2 && offset==512);
 puts("PASS failed send stops without replaying already accepted bytes");
 reset();failure=513;assert(cloud_send_all(5,input,sizeof input)==-1 && calls==1);
 puts("PASS invalid oversized driver acceptance cannot overrun the byte cursor");
 return 0;
}
'''
def main():
    source=(ROOT/'AppliNonSecure/Core/Src/cloud_relay.c').read_text()
    bound=re.search(r'^#define CLOUD_SEND_SLICE_BYTES\s+\([^\n]+\)',source,re.M).group()
    run_native(PREFIX+bound+'\n'+extract_function(source,'cloud_send_all')+TESTS)

if __name__=='__main__':main()
