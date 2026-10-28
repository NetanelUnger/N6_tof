"""Actual C demo scheduler: timing, skipped-slot accounting, wrap and pixels."""
from test_wifi_scan_lifetime import ROOT, run_native

def main():
    header=(ROOT/'AppliNonSecure/Core/Inc/demo_map.h').read_text(encoding='utf-8')
    run_native(header+r'''
#include <assert.h>
#include <stdio.h>
int main(void) {
 DemoMap_Status s={0};
 DemoMap_Start(&s,1,3,100);assert(!DemoMap_Due(&s,1099));
 assert(DemoMap_Due(&s,1100) && s.sequence==1 && s.last_ms==1100 && s.next_ms==2100);
 assert(!DemoMap_Due(&s,1100));assert(DemoMap_Due(&s,4600));
 assert(s.sequence==4 && s.skipped==2 && s.late_slots==2 && s.next_ms==5100 && s.last_ms==4100);
 assert(!DemoMap_Due(&s,4600));
 DemoMap_Start(&s,2,3,0xfffffff0U);assert(!DemoMap_Due(&s,483));
 assert(DemoMap_Due(&s,484) && s.sequence==1 && s.last_ms==484);
 assert(DemoMap_Due(&s,984) && s.sequence==2);
 DemoMap_Start(&s,0,0,100);assert(!DemoMap_Due(&s,0x7fffffff));
 uint8_t b[2268*4+4];memset(b,0xA5,sizeof b);
 for(unsigned seq=1;seq<=2269;++seq){
  DemoMap_Fill(b,2268,seq);unsigned high=0;
  for(unsigned i=0;i<2268;++i){float f;memcpy(&f,b+i*4,4);
   if(f==3500){++high;assert(i==(seq-1)%2268);}else assert(f==500);}
  assert(high==1);for(unsigned i=2268*4;i<sizeof b;++i)assert(b[i]==0xA5);
 }
 puts("PASS 1/2 FPS absolute deadlines, no catch-up burst, missed-slot sequence gaps, tick wrap, stop, all hot pixels and buffer guards");return 0;
}
''')
if __name__=='__main__':main()
