#if defined(__GNUC__)
#pragma GCC optimize ("Os")
#endif
/* Experimental baseline grayscale JPEG. Fixed uniform quantizer (12),
 * canonical fixed-length Huffman tables, no allocation or mutable globals.
 * Input and output must not overlap. Edge blocks replicate the last pixel. */
#include "tof_jpeg.h"
#include <math.h>
static const unsigned char zig[64]={0,1,8,16,9,2,3,10,17,24,32,25,18,11,4,5,12,19,26,33,40,48,41,34,27,20,13,6,7,14,21,28,35,42,49,56,57,50,43,36,29,22,15,23,30,37,44,51,58,59,52,45,38,31,39,46,53,60,61,54,47,55,62,63};
static const float basis[8][8]={{0.353553391f,0.353553391f,0.353553391f,0.353553391f,0.353553391f,0.353553391f,0.353553391f,0.353553391f},{0.490392640f,0.415734806f,0.277785117f,0.097545161f,-0.097545161f,-0.277785117f,-0.415734806f,-0.490392640f},{0.461939766f,0.191341716f,-0.191341716f,-0.461939766f,-0.461939766f,-0.191341716f,0.191341716f,0.461939766f},{0.415734806f,-0.097545161f,-0.490392640f,-0.277785117f,0.277785117f,0.490392640f,0.097545161f,-0.415734806f},{0.353553391f,-0.353553391f,-0.353553391f,0.353553391f,0.353553391f,-0.353553391f,-0.353553391f,0.353553391f},{0.277785117f,-0.490392640f,0.097545161f,0.415734806f,-0.415734806f,-0.097545161f,0.490392640f,-0.277785117f},{0.191341716f,-0.461939766f,0.461939766f,-0.191341716f,-0.191341716f,0.461939766f,-0.461939766f,0.191341716f},{0.097545161f,-0.277785117f,0.415734806f,-0.490392640f,0.490392640f,-0.415734806f,0.277785117f,-0.097545161f}};
typedef struct { unsigned char *out; size_t cap,n; unsigned bits,nb; int failed; } Writer;
static void byte(Writer *w,unsigned v) { if(w->n<w->cap)w->out[w->n++]=(unsigned char)v;else w->failed=1; }
static void word(Writer *w,unsigned v) { byte(w,v>>8);byte(w,v); }
static void marker(Writer *w,unsigned v) { byte(w,255);byte(w,v); }
static void bits(Writer *w,unsigned v,unsigned n) {
 for(unsigned i=n;i>0;--i) { w->bits=(w->bits<<1)|((v>>(i-1))&1U); if(++w->nb==8) { unsigned b=w->bits&255U;byte(w,b);if(b==255)byte(w,0);w->nb=0;w->bits=0; } }
}
static unsigned magnitude(int value) { unsigned a=(unsigned)(value<0?-value:value),n=0;while(a){n++;a>>=1;}return n; }
static void amplitude(Writer *w,int value,unsigned n) { if(n)bits(w,(unsigned)(value<0?value-1:value)&((1U<<n)-1U),n); }
int TofJpeg_Encode(const unsigned char *pixels,unsigned width,unsigned height,unsigned char *out,size_t capacity) {
 Writer w={out,capacity,0,0,0,0}; int previous=0;
 if(!pixels||!out||!width||!height||width>54||height>42)return -1;
 marker(&w,0xd8);
 marker(&w,0xdb);word(&w,67);byte(&w,0);for(unsigned i=0;i<64;i++)byte(&w,12);
 marker(&w,0xc0);word(&w,11);byte(&w,8);word(&w,height);word(&w,width);byte(&w,1);byte(&w,1);byte(&w,0x11);byte(&w,0);
 /* DC categories 0..11: four-bit codes. AC EOB,ZRL,run/size: eight-bit codes. */
 marker(&w,0xc4);word(&w,31);byte(&w,0);for(unsigned i=1;i<=16;i++)byte(&w,i==4?12:0);for(unsigned i=0;i<12;i++)byte(&w,i);
 marker(&w,0xc4);word(&w,181);byte(&w,0x10);for(unsigned i=1;i<=16;i++)byte(&w,i==8?162:0);byte(&w,0);byte(&w,0xf0);
 for(unsigned run=0;run<16;run++)for(unsigned size=1;size<=10;size++)byte(&w,(run<<4)|size);
 marker(&w,0xda);word(&w,8);byte(&w,1);byte(&w,1);byte(&w,0);byte(&w,0);byte(&w,63);byte(&w,0);
 for(unsigned by=0;by<height;by+=8)for(unsigned bx=0;bx<width;bx+=8) {
  float tmp[64]; int coeff[64];
  for(unsigned y=0;y<8;y++)for(unsigned u=0;u<8;u++) {
   float sum=0;unsigned iy=by+y<height?by+y:height-1;
   for(unsigned x=0;x<8;x++){unsigned ix=bx+x<width?bx+x:width-1;sum+=((float)pixels[iy*width+ix]-128)*basis[u][x];}
   tmp[y*8+u]=sum;
  }
  for(unsigned v=0;v<8;v++)for(unsigned u=0;u<8;u++) {
   float sum=0;for(unsigned y=0;y<8;y++)sum+=tmp[y*8+u]*basis[v][y];
   coeff[v*8+u]=(int)roundf(sum/12.0f);
  }
  int delta=coeff[0]-previous;previous=coeff[0];unsigned n=magnitude(delta);if(n>11)return -1;bits(&w,n,4);amplitude(&w,delta,n);
  unsigned run=0;
  for(unsigned k=1;k<64;k++) { int value=coeff[zig[k]];if(!value){run++;continue;}
   while(run>=16){bits(&w,1,8);run-=16;}n=magnitude(value);if(n>10)return -1;
   bits(&w,2+run*10+n-1,8);amplitude(&w,value,n);run=0;
  }
  if(run)bits(&w,0,8);
  if(w.failed)return -1;
 }
 if(w.nb)bits(&w,(1U<<(8-w.nb))-1U,8-w.nb);
 marker(&w,0xd9);return w.failed?-1:(int)w.n;
}
