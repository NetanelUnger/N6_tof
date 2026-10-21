#ifndef SPATIAL_DEPTH_PROFILE_H
#define SPATIAL_DEPTH_PROFILE_H
#include <stdint.h>
#include <stddef.h>

/* Integer nearest-neighbour full-field sampling. Zero is invalid; valid depth
 * clips into 1..255. No component selection, crop, dilation or allocation. */
static inline void N6_SpatialDepthProfile(const float *source, uint32_t width,
    uint32_t height, uint8_t *output, uint32_t out_width, uint32_t out_height,
    uint32_t near_mm, uint32_t far_mm, uint32_t invalid_mm)
{
  for (uint32_t y = 0U; y < out_height; ++y)
  {
    uint32_t sy = ((2U * y + 1U) * height) / (2U * out_height);
    for (uint32_t x = 0U; x < out_width; ++x)
    {
      uint32_t sx = ((2U * x + 1U) * width) / (2U * out_width);
      float value = source[sy * width + sx];
      uint32_t mm = (value > 0.0f && value < (float)invalid_mm) ?
                    (uint32_t)(value + 0.5f) : 0U;
      uint32_t pixel = 0U;
      if (mm != 0U && mm != invalid_mm)
      {
        if (mm < near_mm) mm = near_mm;
        if (mm > far_mm) mm = far_mm;
        pixel = 1U + ((far_mm - mm) * 254U + (far_mm - near_mm) / 2U) /
                      (far_mm - near_mm);
      }
      output[y * out_width + x] = (uint8_t)pixel;
    }
  }
}
#endif
