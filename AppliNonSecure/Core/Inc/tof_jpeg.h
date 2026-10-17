#ifndef TOF_JPEG_H
#define TOF_JPEG_H
#include <stddef.h>
int TofJpeg_Encode(const unsigned char *pixels,unsigned width,unsigned height,unsigned char *out,size_t capacity);
#endif
