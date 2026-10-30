"""Run the actual firmware log normalizer with bounded-buffer guards."""
from test_wifi_scan_lifetime import ROOT,run_native
from test_tof_recovery import function

def main():
 source=(ROOT/'AppliNonSecure/Core/Src/st67w6x_logging.c').read_text()
 run_native(r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
'''+function(source,'logging_normalize')+r'''
static void check(const char *input,const char *expected){
 char buffer[512];strcpy(buffer,input);unsigned n=logging_normalize(buffer,sizeof buffer);
 assert(n==strlen(buffer));assert(!strcmp(buffer,expected));
}
int main(void){
 check("\r\n\r\nOK\r\n\r\n","OK\r\n");
 check("AT< \r\n\r\n>\r\n","AT<\r\n>\r\n");
 check("match cmd [OK] (len:2)\n","match cmd [OK] (len:2)\r\n");
 check("\t \r\n \t\n","");check("","");
 check("  one\t\r\n\r  two\n","  one\r\n  two\r\n");
 check("\033[31mERROR\033[0m\n","\033[31mERROR\033[0m\r\n");
 for(unsigned cap=3;cap<=512;++cap){
  unsigned char data[514];memset(data,0xA5,sizeof data);
  for(unsigned i=0;i<cap-1;++i)data[i]=(i%3==1)?'\n':'x';data[cap-1]=0;
  unsigned n=logging_normalize((char*)data,cap);
  assert(n<cap&&data[n]==0&&data[cap]==0xA5&&data[513]==0xA5);
  if(n){assert(n>=2&&data[n-2]=='\r'&&data[n-1]=='\n');}
  for(unsigned i=0;i<n;++i){
   if(data[i]=='\n')assert(i&&data[i-1]=='\r');
   if(data[i]=='\r')assert(i+1<n&&data[i+1]=='\n');
  }
  assert(!strstr((char*)data,"\r\n\r\n"));
 }
 puts("PASS actual C: blank/whitespace lines, CR/LF/CRLF, ANSI preservation and510 bounded capacities");return 0;
}
''')
if __name__=='__main__':main()
