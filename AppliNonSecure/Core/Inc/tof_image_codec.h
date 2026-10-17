#ifndef TOF_IMAGE_CODEC_H
#define TOF_IMAGE_CODEC_H
#include <stddef.h>
#include <stdint.h>
#define TOF_IMAGE_HEADER_SIZE 56U
#define TOF_IMAGE_VERSION 3U
#define TOF_IMAGE_NPU_OFF 0U
#define TOF_IMAGE_NPU_NOT_READY 1U
#define TOF_IMAGE_NPU_NO_RESULT 2U
#define TOF_IMAGE_NPU_VALID 3U
#define TOF_IMAGE_RAW 1U
#define TOF_IMAGE_Q16 2U
#define TOF_IMAGE_Q8 3U
#define TOF_IMAGE_JPEG 4U
/* Quantized code 0 is invalid; codes 1..max decode as base+(code-1)*step.
 * RAW preserves all float bits. Other modes preserve finite nonnegative values
 * (depth must be positive), rounded to the nearest affine level. JPEG then
 * adds lossy coding; only its appended validity bitmap remains exact. */
typedef struct {
  uint32_t frame_id, timestamp_ms, payload_crc32;
  float base, step;
  uint16_t payload_length;
  uint8_t width, height, channel, mode;
  /* Immutable result captured with the pixels, never sampled by the sender. */
  uint8_t npu_state, npu_class;
  uint16_t npu_confidence;
  uint32_t npu_frame, npu_runs, npu_inference_ms;
} TofImageInfo;
/* Caller owns at least count*4 writable bytes. JPEG uses the same buffer
 * as bounded scratch and returns -1 if the encoded payload does not fit;
 * failures may overwrite input, so the caller must drop the frame.
 * metadata must already contain dimensions/channel/mode/frame/timestamp. */
int TofImage_Encode(uint8_t *data, size_t capacity, TofImageInfo *info);
void TofImage_Header(uint8_t header[TOF_IMAGE_HEADER_SIZE],
                     const TofImageInfo *info, uint16_t offset, uint8_t flags);
uint32_t TofImage_Crc32(const uint8_t *data, size_t length);
#endif
