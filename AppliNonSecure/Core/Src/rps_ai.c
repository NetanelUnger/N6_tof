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
#define RPS_FOREGROUND_BAND_MM       (220U)
#define RPS_FOREGROUND_MARGIN        (2U)
#define RPS_COMPONENT_MIN_PIXELS     (12U)
#define RPS_RELATIVE_PERCENTILE      (10U)
#define RPS_RELATIVE_SPAN_MM         (260U)
#define RPS_FOREGROUND_FLOOR         (32U)
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
static uint16_t rps_component_labels[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint16_t rps_component_queue[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint8_t rps_crop[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static const uint8_t rps_search_percentiles[] = {
  1U, 2U, 5U, 10U, 15U, 25U, 40U, 60U, 80U, 100U
};

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

static uint32_t rps_percentile_x100(uint32_t count, uint32_t percentile)
{
  uint32_t percentile_numerator = (count - 1U) * percentile;
  uint32_t lower_rank = percentile_numerator / 100U;
  uint32_t remainder = percentile_numerator % 100U;
  uint16_t lower = rps_histogram_value_at(lower_rank);
  uint16_t upper = rps_histogram_value_at(
      lower_rank + ((remainder != 0U) ? 1U : 0U));

  return ((uint32_t)lower * 100U) +
         ((uint32_t)(upper - lower) * remainder);
}

static uint32_t rps_find_component(uint16_t cutoff, uint16_t *selected_label,
                                   uint32_t *top, uint32_t *bottom,
                                   uint32_t *left, uint32_t *right)
{
  uint16_t next_label = 0U;
  uint16_t best_label = 0U;
  uint16_t best_minimum = UINT16_MAX;
  uint32_t best_count = 0U;
  uint32_t best_top = 0U, best_bottom = 0U;
  uint32_t best_left = 0U, best_right = 0U;

  memset(rps_component_labels, 0, sizeof(rps_component_labels));
  for (uint32_t start = 0U; start < RPS_SOURCE_PIXELS; ++start)
  {
    uint16_t start_depth = rps_depth_mm[start];
    if ((rps_component_labels[start] != 0U) ||
        (start_depth < RPS_NEAR_MM) || (start_depth > cutoff))
    {
      continue;
    }
    ++next_label;
    uint32_t head = 0U, tail = 0U;
    uint32_t count = 0U;
    uint16_t minimum = UINT16_MAX;
    uint32_t min_row = RPS_SOURCE_HEIGHT, max_row = 0U;
    uint32_t min_column = RPS_SOURCE_WIDTH, max_column = 0U;
    rps_component_queue[tail++] = (uint16_t)start;
    rps_component_labels[start] = next_label;
    while (head < tail)
    {
      uint32_t index = rps_component_queue[head++];
      uint32_t row = index / RPS_SOURCE_WIDTH;
      uint32_t column = index % RPS_SOURCE_WIDTH;
      uint16_t value = rps_depth_mm[index];
      ++count;
      if (value < minimum) minimum = value;
      if (row < min_row) min_row = row;
      if (row > max_row) max_row = row;
      if (column < min_column) min_column = column;
      if (column > max_column) max_column = column;
      for (int32_t row_delta = -1; row_delta <= 1; ++row_delta)
      {
        for (int32_t column_delta = -1; column_delta <= 1; ++column_delta)
        {
          int32_t next_row, next_column;
          uint32_t next_index;
          uint16_t next_depth;
          if ((row_delta == 0) && (column_delta == 0)) continue;
          next_row = (int32_t)row + row_delta;
          next_column = (int32_t)column + column_delta;
          if ((next_row < 0) || (next_row >= (int32_t)RPS_SOURCE_HEIGHT) ||
              (next_column < 0) ||
              (next_column >= (int32_t)RPS_SOURCE_WIDTH)) continue;
          next_index = ((uint32_t)next_row * RPS_SOURCE_WIDTH) +
                       (uint32_t)next_column;
          next_depth = rps_depth_mm[next_index];
          if ((rps_component_labels[next_index] == 0U) &&
              (next_depth >= RPS_NEAR_MM) && (next_depth <= cutoff))
          {
            rps_component_labels[next_index] = next_label;
            rps_component_queue[tail++] = (uint16_t)next_index;
          }
        }
      }
    }
    if ((count >= RPS_COMPONENT_MIN_PIXELS) &&
        ((minimum < best_minimum) ||
         ((minimum == best_minimum) && (count > best_count))))
    {
      best_label = next_label;
      best_minimum = minimum;
      best_count = count;
      best_top = min_row;
      best_bottom = max_row + 1U;
      best_left = min_column;
      best_right = max_column + 1U;
    }
  }
  *selected_label = best_label;
  if (best_label != 0U)
  {
    *top = best_top;
    *bottom = best_bottom;
    *left = best_left;
    *right = best_right;
  }
  return best_count;
}

static uint8_t rps_map_relative(uint16_t millimetres,
                                uint32_t reference_x100)
{
  uint32_t depth_x100 = (uint32_t)millimetres * 100U;
  uint32_t delta_x100 = (depth_x100 > reference_x100) ?
                        (depth_x100 - reference_x100) : 0U;
  uint32_t span_x100 = RPS_RELATIVE_SPAN_MM * 100U;

  if (delta_x100 > span_x100) delta_x100 = span_x100;
  return (uint8_t)(RPS_FOREGROUND_FLOOR + rps_round_even(
      (span_x100 - delta_x100) * (255U - RPS_FOREGROUND_FLOOR),
      span_x100));
}

static void rps_preprocess(const float *depth, uint8_t *output)
{
  uint32_t candidate_count = 0U;
  uint32_t top = 0U;
  uint32_t bottom = RPS_SOURCE_HEIGHT;
  uint32_t left = 0U;
  uint32_t right = RPS_SOURCE_WIDTH;
  uint16_t selected_label = 0U;
  uint32_t selected_count = 0U;
  uint32_t relative_reference_x100 = RPS_NEAR_MM * 100U;

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
    for (uint32_t search = 0U;
         search < (sizeof(rps_search_percentiles) /
                   sizeof(rps_search_percentiles[0])); ++search)
    {
      uint32_t reference_x100 = rps_percentile_x100(
          candidate_count, rps_search_percentiles[search]);
      uint32_t cutoff_x100 = reference_x100 +
                             (RPS_FOREGROUND_BAND_MM * 100U);
      uint16_t cutoff = (uint16_t)(cutoff_x100 / 100U);
      if (cutoff > RPS_FAR_MM) cutoff = RPS_FAR_MM;
      selected_count = rps_find_component(cutoff, &selected_label,
                                          &top, &bottom, &left, &right);
      if (selected_count != 0U) break;
    }
    if (selected_count != 0U)
    {
      top = (top > RPS_FOREGROUND_MARGIN) ?
            (top - RPS_FOREGROUND_MARGIN) : 0U;
      left = (left > RPS_FOREGROUND_MARGIN) ?
             (left - RPS_FOREGROUND_MARGIN) : 0U;
      bottom += RPS_FOREGROUND_MARGIN;
      right += RPS_FOREGROUND_MARGIN;
      if (bottom > RPS_SOURCE_HEIGHT) bottom = RPS_SOURCE_HEIGHT;
      if (right > RPS_SOURCE_WIDTH) right = RPS_SOURCE_WIDTH;
      memset(rps_histogram, 0, sizeof(rps_histogram));
      for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
      {
        if (rps_component_labels[index] == selected_label)
        {
          ++rps_histogram[rps_depth_mm[index] - RPS_NEAR_MM];
        }
      }
      relative_reference_x100 = rps_percentile_x100(
          selected_count, RPS_RELATIVE_PERCENTILE);
    }
  }

  uint32_t crop_width = right - left;
  uint32_t crop_height = bottom - top;
  for (uint32_t row = 0U; row < crop_height; ++row)
  {
    for (uint32_t column = 0U; column < crop_width; ++column)
    {
      uint32_t source_index = ((top + row) * RPS_SOURCE_WIDTH) +
                              left + column;
      rps_crop[(row * crop_width) + column] =
          ((selected_count != 0U) &&
           (rps_component_labels[source_index] == selected_label)) ?
          rps_map_relative(rps_depth_mm[source_index],
                           relative_reference_x100) : 0U;
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
