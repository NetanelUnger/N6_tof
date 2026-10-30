"""Execute production CR/LF framing against fragmented and bounded buffers."""
from test_wifi_scan_lifetime import ROOT, run_native

TESTS = r'''
#include <assert.h>
#include <stdio.h>
int main(void) {
  uint8_t slots[4][160] = {{0}};
  AppCliReply_t reply = {.active=1};
  assert(!AppCliReply_AppendText(&reply, slots[0], 160, 160, 4, "one\r", 4));
  assert(!AppCliReply_AppendText(&reply, slots[0], 160, 160, 4, "\ntwo\n\nthree\r\n", 13));
  assert(reply.bytes==15 && !memcmp(slots[0], "one\rtwo\r\rthree\r", 15));
  assert(!memchr(slots, '\n', reply.bytes));
  AppCliReply_TrimLineBreak(&reply, slots[0], 160, 160);
  assert(!AppCliReply_Append(&reply, slots[0],160,160,4,"\n",1,1));
  assert(!memcmp(slots[0], "one\rtwo\r\rthree\n", 15));
  puts("PASS CRLF split across calls, bare LF and blank lines normalize to CR; sole LF finishes reply");
  memset(slots,0,sizeof slots);reply=(AppCliReply_t){.active=1};
  char text[400];memset(text,'a',sizeof text);text[159]='\r';text[160]='\n';
  assert(!AppCliReply_AppendText(&reply,slots[0],160,160,4,text,sizeof text));
  assert(reply.bytes==399 && slots[0][159]=='\r' && slots[1][0]=='a');
  uint32_t kept=reply.bytes;
  assert(AppCliReply_AppendText(&reply,slots[0],160,160,4,text,sizeof text)<0);
  assert(reply.overflow && reply.bytes==kept && !memchr(slots,'\n',sizeof slots));
  assert(!AppCliReply_Append(&reply,slots[0],160,160,4,"\rFAIL\r\n",7,1));
  assert(!memcmp(&slots[2][79],"\rFAIL\r\n",7));
  puts("PASS slot-boundary conversion, atomic overflow and reserved visible FAIL/CRLF suffix");
  memset(slots,0,sizeof slots);reply=(AppCliReply_t){.active=1};
  const uint8_t raw[]={0x43,0x06,0x15,0x18,0x0d,0x0a};
  assert(!AppCliReply_Append(&reply,slots[0],160,160,4,raw,sizeof raw,0));
  assert(reply.bytes==sizeof raw && !memcmp(slots,raw,sizeof raw));
  puts("PASS raw append remains byte-exact for XMODEM; normalization is text-only");
  return 0;
}
'''

if __name__ == '__main__':
    run_native((ROOT/'AppliNonSecure/Core/Inc/app_cli_reply.h').read_text()+TESTS)
