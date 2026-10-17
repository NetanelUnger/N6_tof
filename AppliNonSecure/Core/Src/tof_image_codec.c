#if defined(__GNUC__)
#pragma GCC optimize ("Os")
#endif
#include "tof_image_codec.h"
#include "tof_jpeg.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(float) == 4, "IEEE float32 required");

static void write_u16(uint8_t *target, uint16_t value)
{
  target[0] = (uint8_t)value;
  target[1] = (uint8_t)(value >> 8U);
}

static void write_u32(uint8_t *target, uint32_t value)
{
  write_u16(target, (uint16_t)value);
  write_u16(target + 2, (uint16_t)(value >> 16U));
}

static void write_f32(uint8_t *target, float value)
{
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  write_u32(target, bits);
}

uint32_t TofImage_Crc32(const uint8_t *data, size_t length)
{
  uint32_t crc = 0xffffffffU;
  while (length-- != 0U)
  {
    crc ^= *data++;
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1U) ^ ((crc & 1U) ? 0xedb88320U : 0U);
  }
  return crc ^ 0xffffffffU;
}

static int sample_is_valid(float value, uint8_t channel)
{
  return isfinite(value) && ((channel == 1U) ? value > 0.0f : value >= 0.0f);
}

int TofImage_Encode(uint8_t *data, size_t capacity, TofImageInfo *info)
{
  if (!data || !info || !info->width || info->width > 54 ||
      !info->height || info->height > 42 || info->channel < 1 ||
      info->channel > 5 || info->mode < TOF_IMAGE_RAW || info->mode > TOF_IMAGE_JPEG)
    return -1;

  size_t count = (size_t)info->width * info->height;
  if (capacity < count * sizeof(float)) return -1;
  info->base = 0;
  info->step = 0;
  unsigned bytes_per_pixel = info->mode == TOF_IMAGE_RAW ? 4U :
                             info->mode == TOF_IMAGE_Q16 ? 2U : 1U;

  if (info->mode != TOF_IMAGE_RAW)
  {
    float minimum = FLT_MAX, maximum = -FLT_MAX;
    /* Find the range before overwriting any input bytes. */
    for (size_t index = 0; index < count; ++index)
    {
      float value;
      memcpy(&value, data + sizeof(float) * index, sizeof(value));
      if (sample_is_valid(value, info->channel))
      {
        if (value < minimum) minimum = value;
        if (value > maximum) maximum = value;
      }
    }

    /* Zero is invalid; the remaining codes span max_code - 1 intervals. */
    unsigned intervals = info->mode == TOF_IMAGE_Q16 ? 65534U : 254U;
    if (maximum >= minimum)
    {
      info->base = minimum;
      double exact_step = ((double)maximum - minimum) / intervals;
      info->step = (float)exact_step;
      if ((double)info->step < exact_step)
        info->step = nextafterf(info->step, INFINITY);
      if (!isfinite(info->step)) return -1;
    }

    for (size_t index = 0; index < count; ++index)
    {
      float value;
      unsigned code = 0;
      /* Read first, then write at a shrinking offset: unread floats survive. */
      memcpy(&value, data + sizeof(float) * index, sizeof(value));
      if (sample_is_valid(value, info->channel))
      {
        double level = info->step > 0 ? ((double)value - info->base) / info->step : 0;
        if (level < 0) level = 0;
        if (level > intervals) level = intervals;
        code = 1U + (unsigned)(level + 0.5);
      }
      if (bytes_per_pixel == 2U)
        write_u16(data + 2U * index, (uint16_t)code);
      else
        data[index] = (uint8_t)code;
    }
  }

  if (info->mode == TOF_IMAGE_JPEG)
  {
    /* Q8 is already in the front of the snapshot. Move it to the tail, leaving
     * a bounded output region. Mask is kept immediately before the source. */
    size_t mask_bytes = (count + 7U) / 8U;
    size_t source_offset = capacity - count;
    size_t mask_offset = source_offset - mask_bytes;
    memmove(data + source_offset, data, count);
    memset(data + mask_offset, 0, mask_bytes);
    for (size_t i = 0; i < count; ++i)
      if (data[source_offset + i]) data[mask_offset + i / 8U] |= (uint8_t)(1U << (i % 8U));
    int length = TofJpeg_Encode(data + source_offset, info->width, info->height,
                                data, mask_offset);
    if (length < 0 || (size_t)length + mask_bytes > source_offset) return -1;
    memmove(data + (size_t)length, data + mask_offset, mask_bytes);
    info->payload_length = (uint16_t)((size_t)length + mask_bytes);
  }
  else info->payload_length = (uint16_t)(count * bytes_per_pixel);
  info->payload_crc32 = TofImage_Crc32(data, info->payload_length);
  return 0;
}

void TofImage_Header(uint8_t header[TOF_IMAGE_HEADER_SIZE],
                     const TofImageInfo *info, uint16_t offset, uint8_t flags)
{
  memset(header, 0, TOF_IMAGE_HEADER_SIZE);
  write_u16(header, 0x364e);
  header[2] = TOF_IMAGE_VERSION;
  header[3] = flags;
  write_u32(header + 4, info->frame_id);
  write_u16(header + 8, offset);
  write_u16(header + 10, info->payload_length);
  header[12] = info->width;
  header[13] = info->height;
  header[14] = info->channel;
  header[15] = info->mode;
  write_u32(header + 16, info->payload_crc32);
  write_f32(header + 20, info->base);
  write_f32(header + 24, info->step);
  write_u32(header + 28, info->timestamp_ms);
  write_u16(header + 32, TOF_IMAGE_HEADER_SIZE);
  header[34] = info->npu_state;
  header[35] = info->npu_class;
  write_u16(header + 36, info->npu_confidence);
  /* 38..39 reserved, zero. All metadata is protected on every fragment. */
  write_u32(header + 40, info->npu_frame);
  write_u32(header + 44, info->npu_runs);
  write_u32(header + 48, info->npu_inference_ms);
  write_u32(header + 52, TofImage_Crc32(header, 52));
}
