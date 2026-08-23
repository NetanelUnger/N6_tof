#include "rps_ai.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "app_features.h"
#include "debug_uart.h"
#include "main.h"
#include "npu_shared_memory.h"

#if (APP_RPS_NPU_ENABLED == 1U)
#include "rps_model_weights.h"
#include "stai.h"
#include "stai_rps_tof.h"
#endif

#define RPS_SOURCE_WIDTH             (54U)
#define RPS_SOURCE_HEIGHT            (42U)
#define RPS_SOURCE_PIXELS            (RPS_SOURCE_WIDTH * RPS_SOURCE_HEIGHT)
#define RPS_MODEL_WIDTH              (64U)
#define RPS_MODEL_HEIGHT             (50U)
#define RPS_MODEL_PIXELS             (RPS_MODEL_WIDTH * RPS_MODEL_HEIGHT)
#define RPS_NEAR_MM                  (100U)
#define RPS_FAR_MM                   (1200U)
#define RPS_FOREGROUND_BAND_MM       (160U)
#define RPS_FOREGROUND_MARGIN        (2U)
#define RPS_HISTOGRAM_BINS           (RPS_FAR_MM - RPS_NEAR_MM + 1U)

static RPS_AI_Status_t rps_status = {
  .enabled = APP_RPS_NPU_ENABLED,
  .last_frame = UINT32_MAX,
  .class_id = RPS_AI_CLASS_NONE
};

#if (APP_RPS_NPU_ENABLED == 1U)
STAI_NETWORK_CONTEXT_DECLARE(rps_network_context, STAI_RPS_TOF_CONTEXT_SIZE)
static stai_ptr rps_input;
static stai_ptr rps_output;
static uint16_t rps_depth_mm[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint16_t rps_histogram[RPS_HISTOGRAM_BINS] NPU_SHARED_BSS;
static uint8_t rps_crop[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;

static uint32_t rps_round_even(uint32_t numerator, uint32_t denominator)
{
  uint32_t quotient = numerator / denominator;
  uint32_t remainder = numerator % denominator;
  uint32_t twice = remainder * 2U;

  if ((twice > denominator) ||
      ((twice == denominator) && ((quotient & 1U) != 0U)))
  {
    ++quotient;
  }
  return quotient;
}

static uint16_t rps_histogram_value_at(uint32_t rank)
{
  uint32_t count = 0U;

  for (uint32_t index = 0U; index < RPS_HISTOGRAM_BINS; ++index)
  {
    count += rps_histogram[index];
    if (count > rank)
    {
      return (uint16_t)(RPS_NEAR_MM + index);
    }
  }
  return RPS_FAR_MM;
}

static uint8_t rps_map_depth(uint16_t millimetres, uint16_t cutoff)
{
  uint32_t numerator;

  if ((millimetres < RPS_NEAR_MM) || (millimetres > RPS_FAR_MM) ||
      (millimetres > cutoff))
  {
    return 0U;
  }
  numerator = (RPS_FAR_MM - millimetres) * 255U;
  return (uint8_t)rps_round_even(numerator, RPS_FAR_MM - RPS_NEAR_MM);
}

static void rps_preprocess(const float *depth, uint8_t *output)
{
  uint32_t candidate_count = 0U;
  uint32_t top = 0U;
  uint32_t bottom = RPS_SOURCE_HEIGHT;
  uint32_t left = 0U;
  uint32_t right = RPS_SOURCE_WIDTH;
  uint16_t cutoff = RPS_FAR_MM;

  memset(rps_histogram, 0, sizeof(rps_histogram));
  for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
  {
    float value = depth[index];
    uint16_t millimetres = UINT16_MAX;
    if (isfinite(value) && (value > 0.0f) && (value < 65535.0f))
    {
      millimetres = (uint16_t)(value + 0.5f);
    }
    rps_depth_mm[index] = millimetres;
    if ((millimetres >= RPS_NEAR_MM) && (millimetres <= RPS_FAR_MM))
    {
      ++rps_histogram[millimetres - RPS_NEAR_MM];
      ++candidate_count;
    }
  }

  if (candidate_count != 0U)
  {
    uint32_t percentile_numerator = (candidate_count - 1U) * 5U;
    uint32_t lower_rank = percentile_numerator / 100U;
    uint32_t remainder = percentile_numerator % 100U;
    uint16_t lower = rps_histogram_value_at(lower_rank);
    uint16_t upper = rps_histogram_value_at(
        (lower_rank + ((remainder != 0U) ? 1U : 0U)));
    uint32_t reference_x100 = ((uint32_t)lower * 100U) +
                              ((uint32_t)(upper - lower) * remainder);
    cutoff = (uint16_t)((reference_x100 +
                         (RPS_FOREGROUND_BAND_MM * 100U)) / 100U);
    if (cutoff > RPS_FAR_MM)
    {
      cutoff = RPS_FAR_MM;
    }

    uint32_t min_row = RPS_SOURCE_HEIGHT;
    uint32_t max_row = 0U;
    uint32_t min_column = RPS_SOURCE_WIDTH;
    uint32_t max_column = 0U;
    uint32_t foreground_count = 0U;
    for (uint32_t row = 0U; row < RPS_SOURCE_HEIGHT; ++row)
    {
      for (uint32_t column = 0U; column < RPS_SOURCE_WIDTH; ++column)
      {
        uint16_t value = rps_depth_mm[(row * RPS_SOURCE_WIDTH) + column];
        if ((value >= RPS_NEAR_MM) && (value <= cutoff))
        {
          if (row < min_row) min_row = row;
          if (row > max_row) max_row = row;
          if (column < min_column) min_column = column;
          if (column > max_column) max_column = column;
          ++foreground_count;
        }
      }
    }
    if (foreground_count != 0U)
    {
      top = (min_row > RPS_FOREGROUND_MARGIN) ?
            (min_row - RPS_FOREGROUND_MARGIN) : 0U;
      left = (min_column > RPS_FOREGROUND_MARGIN) ?
             (min_column - RPS_FOREGROUND_MARGIN) : 0U;
      bottom = max_row + RPS_FOREGROUND_MARGIN + 1U;
      right = max_column + RPS_FOREGROUND_MARGIN + 1U;
      if (bottom > RPS_SOURCE_HEIGHT) bottom = RPS_SOURCE_HEIGHT;
      if (right > RPS_SOURCE_WIDTH) right = RPS_SOURCE_WIDTH;
    }
  }

  uint32_t crop_width = right - left;
  uint32_t crop_height = bottom - top;
  for (uint32_t row = 0U; row < crop_height; ++row)
  {
    for (uint32_t column = 0U; column < crop_width; ++column)
    {
      uint16_t value = rps_depth_mm[((top + row) * RPS_SOURCE_WIDTH) +
                                    left + column];
      rps_crop[(row * crop_width) + column] =
          rps_map_depth(value, cutoff);
    }
  }

  uint32_t resized_width;
  uint32_t resized_height;
  if ((RPS_MODEL_WIDTH * crop_height) <=
      (RPS_MODEL_HEIGHT * crop_width))
  {
    resized_width = RPS_MODEL_WIDTH;
    resized_height = rps_round_even(crop_height * RPS_MODEL_WIDTH,
                                    crop_width);
  }
  else
  {
    resized_height = RPS_MODEL_HEIGHT;
    resized_width = rps_round_even(crop_width * RPS_MODEL_HEIGHT,
                                   crop_height);
  }
  if (resized_width == 0U) resized_width = 1U;
  if (resized_height == 0U) resized_height = 1U;

  memset(output, 0, RPS_MODEL_PIXELS);
  uint32_t x_offset = (RPS_MODEL_WIDTH - resized_width) / 2U;
  uint32_t y_offset = (RPS_MODEL_HEIGHT - resized_height) / 2U;
  for (uint32_t row = 0U; row < resized_height; ++row)
  {
    uint32_t source_row = ((2U * row + 1U) * crop_height) /
                          (2U * resized_height);
    if (source_row >= crop_height) source_row = crop_height - 1U;
    for (uint32_t column = 0U; column < resized_width; ++column)
    {
      uint32_t source_column = ((2U * column + 1U) * crop_width) /
                               (2U * resized_width);
      if (source_column >= crop_width) source_column = crop_width - 1U;
      output[((y_offset + row) * RPS_MODEL_WIDTH) + x_offset + column] =
          rps_crop[(source_row * crop_width) + source_column];
    }
  }
}
#endif /* APP_RPS_NPU_ENABLED */

int RPS_AI_Init(void)
{
#if (APP_RPS_NPU_ENABLED == 1U)
  stai_size count;
  stai_return_code result;

  memcpy((void *)(uintptr_t)RPS_MODEL_WEIGHTS_NPU_ADDRESS, rps_model_weights,
         RPS_MODEL_WEIGHTS_SIZE);
  __DSB();

  result = stai_runtime_init();
  if (result != STAI_SUCCESS)
  {
    rps_status.last_error = (int32_t)result;
    ++rps_status.errors;
    return -1;
  }
  result = stai_rps_tof_init(rps_network_context);
  if (result != STAI_SUCCESS)
  {
    rps_status.last_error = (int32_t)result;
    ++rps_status.errors;
    return -2;
  }
  count = 1U;
  result = stai_rps_tof_get_inputs(rps_network_context, &rps_input, &count);
  if ((result != STAI_SUCCESS) || (count != 1U) || (rps_input == NULL))
  {
    rps_status.last_error = (int32_t)result;
    ++rps_status.errors;
    return -3;
  }
  count = 1U;
  result = stai_rps_tof_get_outputs(rps_network_context, &rps_output, &count);
  if ((result != STAI_SUCCESS) || (count != 1U) || (rps_output == NULL))
  {
    rps_status.last_error = (int32_t)result;
    ++rps_status.errors;
    return -4;
  }
  rps_status.ready = 1U;
  rps_status.last_error = STAI_SUCCESS;
  Debug_UART_Log("RPS", "Neural-ART ready; %lu signed weight bytes copied to NPU SRAM6",
                 (unsigned long)RPS_MODEL_WEIGHTS_SIZE);
  return 0;
#else
  rps_status.enabled = 0U;
  return -1;
#endif
}

int RPS_AI_ProcessDepth(const float *depth, uint8_t width, uint8_t height,
                        uint32_t frame_id)
{
#if (APP_RPS_NPU_ENABLED == 1U)
  uint32_t started;
  stai_return_code result;

  if ((rps_status.enabled == 0U) || (rps_status.ready == 0U))
  {
    return 1;
  }
  if ((depth == NULL) || (width != RPS_SOURCE_WIDTH) ||
      (height != RPS_SOURCE_HEIGHT))
  {
    ++rps_status.errors;
    rps_status.last_error = STAI_ERROR_NETWORK_INVALID_API_ARGUMENTS;
    return -1;
  }

  rps_preprocess(depth, rps_input);
  started = HAL_GetTick();
  result = stai_rps_tof_run(rps_network_context, STAI_MODE_SYNC);
  rps_status.inference_ms = HAL_GetTick() - started;
  if ((result != STAI_DONE) && (result != STAI_SUCCESS))
  {
    ++rps_status.errors;
    rps_status.last_error = (int32_t)result;
    return -2;
  }

  int8_t *scores = (int8_t *)rps_output;
  uint8_t best = 0U;
  for (uint32_t index = 0U; index < RPS_AI_CLASS_COUNT; ++index)
  {
    rps_status.scores[index] = scores[index];
    if (scores[index] > scores[best]) best = (uint8_t)index;
  }
  rps_status.class_id = best;
  rps_status.confidence_per_mille =
      (uint16_t)(((uint32_t)((int32_t)scores[best] + 128) * 1000U) / 256U);
  rps_status.last_frame = frame_id;
  rps_status.last_error = STAI_SUCCESS;
  ++rps_status.runs;
  return 0;
#else
  (void)depth;
  (void)width;
  (void)height;
  (void)frame_id;
  return 1;
#endif
}

void RPS_AI_SetEnabled(uint32_t enabled)
{
  rps_status.enabled = ((enabled != 0U) &&
                        (APP_RPS_NPU_ENABLED == 1U)) ? 1U : 0U;
}

void RPS_AI_GetStatus(RPS_AI_Status_t *status)
{
  if (status != NULL)
  {
    *status = rps_status;
  }
}

const char *RPS_AI_ClassName(uint8_t class_id)
{
  static const char *const names[RPS_AI_CLASS_COUNT] = {
    "none", "rock", "paper", "scissors"
  };
  return (class_id < RPS_AI_CLASS_COUNT) ? names[class_id] : "unknown";
}

const char *RPS_AI_ClassDisplayName(uint8_t class_id)
{
  static const char *const names[RPS_AI_CLASS_COUNT] = {
    "NOTHING", "ROCK", "PAPER", "SCISSORS"
  };
  return (class_id < RPS_AI_CLASS_COUNT) ? names[class_id] : "UNKNOWN";
}
