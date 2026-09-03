#include "rps_ai.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#if defined(__ARM_FEATURE_MVE) && (__ARM_FEATURE_MVE > 0)
#include <arm_mve.h>
#define RPS_MVE_ACCELERATED (1U)
#else
#define RPS_MVE_ACCELERATED (0U)
#endif

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
#define RPS_MODEL_WIDTH              RPS_AI_MODEL_INPUT_WIDTH
#define RPS_MODEL_HEIGHT             RPS_AI_MODEL_INPUT_HEIGHT
#define RPS_MODEL_PIXELS             (RPS_MODEL_WIDTH * RPS_MODEL_HEIGHT)
#define RPS_MODEL_BORDER_PIXELS      (4U)
#define RPS_RESIZE_WIDTH             (RPS_MODEL_WIDTH - (2U * RPS_MODEL_BORDER_PIXELS))
#define RPS_RESIZE_HEIGHT            (RPS_MODEL_HEIGHT - (2U * RPS_MODEL_BORDER_PIXELS))
#define RPS_NEAR_MM                  (100U)
#define RPS_SENSOR_VALID_FAR_MM      (1200U)
#define RPS_MODEL_MAX_DISTANCE_MM    (600U)
#define RPS_FOREGROUND_BAND_MM       (220U)
#define RPS_NEIGHBOR_DEPTH_JUMP_MM   (120U)
#define RPS_FOREGROUND_MARGIN        (4U)
#define RPS_COMPONENT_MIN_PIXELS     (12U)
#define RPS_RELATIVE_PERCENTILE      (10U)
#define RPS_RELATIVE_SPAN_MM         (260U)
#define RPS_FOREGROUND_FLOOR         (32U)
#define RPS_FLAT_FOREGROUND_VALUE    (255U)
#define RPS_STAGE_6_BINARY_THRESHOLD (0U)
#define RPS_PRODUCTION_BINARY_THRESHOLD (210U)
#define RPS_BINARY_DILATION_PASSES   (1U)
#define RPS_OBJECT_7_DEFAULT_THRESHOLD RPS_PRODUCTION_BINARY_THRESHOLD
#define RPS_HISTOGRAM_BINS           (RPS_SENSOR_VALID_FAR_MM - RPS_NEAR_MM + 1U)
#define RPS_OUTPUT_ZERO_POINT        (-128)
#define RPS_OUTPUT_SCALE_DENOMINATOR (256U)

static RPS_AI_Status_t rps_status = {
  .enabled = APP_RPS_NPU_ENABLED,
  .last_frame = UINT32_MAX,
  .class_id = RPS_AI_CLASS_NONE
};

_Static_assert(RPS_RESIZE_WIDTH > 0U && RPS_RESIZE_HEIGHT > 0U,
               "RPS model border must leave a non-empty resize area");

#if (APP_RPS_NPU_ENABLED == 1U)
STAI_NETWORK_CONTEXT_DECLARE(rps_network_context, STAI_RPS_TOF_CONTEXT_SIZE)
static stai_ptr rps_input;
static stai_ptr rps_output;
static uint16_t rps_depth_mm[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint16_t rps_histogram[RPS_HISTOGRAM_BINS] NPU_SHARED_BSS;
static uint16_t rps_component_labels[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint16_t rps_component_queue[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint8_t rps_crop[RPS_SOURCE_PIXELS] NPU_SHARED_BSS;
static uint8_t rps_model_input_snapshot[RPS_MODEL_PIXELS] NPU_SHARED_BSS;
static uint8_t rps_processing_view_snapshot[RPS_MODEL_PIXELS] NPU_SHARED_BSS;
static uint8_t rps_resize_offsets[RPS_MODEL_WIDTH] NPU_SHARED_BSS;
static uint32_t rps_model_input_frame = UINT32_MAX;
static RPS_AI_ViewSelection_t rps_requested_view = RPS_AI_VIEW_NPU;
static uint8_t rps_object_7_threshold = RPS_OBJECT_7_DEFAULT_THRESHOLD;
static RPS_AI_ViewSelection_t rps_published_view = RPS_AI_VIEW_NPU;
static const uint8_t *rps_published_view_pixels;
static uint8_t rps_published_view_width;
static uint8_t rps_published_view_height;
static uint8_t rps_published_view_is_npu;
static const uint8_t rps_search_percentiles[] = {
  1U, 2U, 5U, 10U, 15U, 25U, 40U, 60U, 80U, 100U
};

typedef struct
{
  uint32_t count;
  uint32_t top;
  uint32_t bottom;
  uint32_t left;
  uint32_t right;
  uint32_t reference_x100;
  uint16_t label;
  uint16_t cutoff_mm;
} RPS_ObjectSelection_t;

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
  return RPS_SENSOR_VALID_FAR_MM;
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

/* The adaptive 220 mm band is only a robust seed finder. A tilted sheet can
 * span more than 220 mm from one side to the other while adjacent sensor
 * pixels still change smoothly. Grow the seed through those locally
 * continuous neighbors so a single physical object is not sliced into depth
 * stripes. The hard production maximum (600 mm) remains absolute. */
static void rps_grow_component(uint16_t maximum_distance_mm,
                               RPS_ObjectSelection_t *selection)
{
  uint32_t head = 0U;
  uint32_t tail = 0U;
  uint32_t top = RPS_SOURCE_HEIGHT;
  uint32_t bottom = 0U;
  uint32_t left = RPS_SOURCE_WIDTH;
  uint32_t right = 0U;

  if ((selection == NULL) || (selection->label == 0U))
  {
    return;
  }

  for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
  {
    if (rps_component_labels[index] == selection->label)
    {
      uint32_t row = index / RPS_SOURCE_WIDTH;
      uint32_t column = index % RPS_SOURCE_WIDTH;
      rps_component_queue[tail++] = (uint16_t)index;
      if (row < top) top = row;
      if ((row + 1U) > bottom) bottom = row + 1U;
      if (column < left) left = column;
      if ((column + 1U) > right) right = column + 1U;
    }
  }

  while (head < tail)
  {
    uint32_t index = rps_component_queue[head++];
    uint32_t row = index / RPS_SOURCE_WIDTH;
    uint32_t column = index % RPS_SOURCE_WIDTH;
    uint16_t depth = rps_depth_mm[index];

    for (int32_t row_delta = -1; row_delta <= 1; ++row_delta)
    {
      for (int32_t column_delta = -1; column_delta <= 1; ++column_delta)
      {
        int32_t next_row;
        int32_t next_column;
        uint32_t next_index;
        uint16_t next_depth;
        uint16_t difference;

        if ((row_delta == 0) && (column_delta == 0)) continue;
        next_row = (int32_t)row + row_delta;
        next_column = (int32_t)column + column_delta;
        if ((next_row < 0) || (next_row >= (int32_t)RPS_SOURCE_HEIGHT) ||
            (next_column < 0) ||
            (next_column >= (int32_t)RPS_SOURCE_WIDTH)) continue;
        next_index = ((uint32_t)next_row * RPS_SOURCE_WIDTH) +
                     (uint32_t)next_column;
        if (rps_component_labels[next_index] == selection->label) continue;
        next_depth = rps_depth_mm[next_index];
        if ((next_depth < RPS_NEAR_MM) ||
            (next_depth > maximum_distance_mm)) continue;
        difference = (next_depth > depth) ? (next_depth - depth) :
                                            (depth - next_depth);
        if (difference > RPS_NEIGHBOR_DEPTH_JUMP_MM) continue;

        rps_component_labels[next_index] = selection->label;
        rps_component_queue[tail++] = (uint16_t)next_index;
        if ((uint32_t)next_row < top) top = (uint32_t)next_row;
        if (((uint32_t)next_row + 1U) > bottom)
        {
          bottom = (uint32_t)next_row + 1U;
        }
        if ((uint32_t)next_column < left) left = (uint32_t)next_column;
        if (((uint32_t)next_column + 1U) > right)
        {
          right = (uint32_t)next_column + 1U;
        }
      }
    }
  }

  selection->count = tail;
  selection->top = top;
  selection->bottom = bottom;
  selection->left = left;
  selection->right = right;
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

static void rps_copy_model_input(uint8_t *destination,
                                 const uint8_t *source)
{
#if (RPS_MVE_ACCELERATED == 1U)
  for (uint32_t offset = 0U; offset < RPS_MODEL_PIXELS; offset += 16U)
  {
    mve_pred16_t predicate = vctp8q(RPS_MODEL_PIXELS - offset);
    uint8x16_t pixels = vldrbq_z_u8(&source[offset], predicate);
    vstrbq_p_u8(&destination[offset], pixels, predicate);
  }
#else
  memcpy(destination, source, RPS_MODEL_PIXELS);
#endif
}

static void rps_resize_nearest(const uint8_t *crop, uint32_t crop_width,
                               uint32_t crop_height, uint8_t *output,
                               uint32_t resized_width,
                               uint32_t resized_height)
{
  uint32_t x_offset = (RPS_MODEL_WIDTH - resized_width) / 2U;
  uint32_t y_offset = (RPS_MODEL_HEIGHT - resized_height) / 2U;

  memset(output, 0, RPS_MODEL_PIXELS);
  for (uint32_t column = 0U; column < resized_width; ++column)
  {
    uint32_t source_column = ((2U * column + 1U) * crop_width) /
                             (2U * resized_width);
    if (source_column >= crop_width) source_column = crop_width - 1U;
    rps_resize_offsets[column] = (uint8_t)source_column;
  }

  for (uint32_t row = 0U; row < resized_height; ++row)
  {
    uint32_t source_row = ((2U * row + 1U) * crop_height) /
                          (2U * resized_height);
    const uint8_t *source;
    uint8_t *destination;
    if (source_row >= crop_height) source_row = crop_height - 1U;
    source = &crop[source_row * crop_width];
    destination = &output[((y_offset + row) * RPS_MODEL_WIDTH) + x_offset];

#if (RPS_MVE_ACCELERATED == 1U)
    for (uint32_t column = 0U; column < resized_width; column += 16U)
    {
      mve_pred16_t predicate = vctp8q(resized_width - column);
      uint8x16_t offsets = vldrbq_z_u8(&rps_resize_offsets[column],
                                       predicate);
      uint8x16_t pixels = vldrbq_gather_offset_z_u8(source, offsets,
                                                    predicate);
      vstrbq_p_u8(&destination[column], pixels, predicate);
    }
#else
    for (uint32_t column = 0U; column < resized_width; ++column)
    {
      destination[column] = source[rps_resize_offsets[column]];
    }
#endif
  }
}

static uint8_t rps_map_absolute(uint16_t millimetres)
{
  uint32_t span = RPS_SENSOR_VALID_FAR_MM - RPS_NEAR_MM;
  uint32_t delta = millimetres - RPS_NEAR_MM;

  return (uint8_t)(RPS_FOREGROUND_FLOOR + rps_round_even(
      (span - delta) * (255U - RPS_FOREGROUND_FLOOR), span));
}

static void rps_select_object(uint16_t maximum_distance_mm,
                              RPS_ObjectSelection_t *selection)
{
  uint32_t candidate_count = 0U;

  memset(selection, 0, sizeof(*selection));
  selection->cutoff_mm = maximum_distance_mm;

  memset(rps_histogram, 0, sizeof(rps_histogram));
  for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
  {
    uint16_t millimetres = rps_depth_mm[index];
    if ((millimetres >= RPS_NEAR_MM) &&
        (millimetres <= maximum_distance_mm))
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
      if (cutoff > maximum_distance_mm) cutoff = maximum_distance_mm;
      selection->cutoff_mm = cutoff;
      selection->count = rps_find_component(
          cutoff, &selection->label, &selection->top, &selection->bottom,
          &selection->left, &selection->right);
      if (selection->count != 0U) break;
    }
    if (selection->count != 0U)
    {
      rps_grow_component(maximum_distance_mm, selection);
      selection->top = (selection->top > RPS_FOREGROUND_MARGIN) ?
                       (selection->top - RPS_FOREGROUND_MARGIN) : 0U;
      selection->left = (selection->left > RPS_FOREGROUND_MARGIN) ?
                        (selection->left - RPS_FOREGROUND_MARGIN) : 0U;
      selection->bottom += RPS_FOREGROUND_MARGIN;
      selection->right += RPS_FOREGROUND_MARGIN;
      if (selection->bottom > RPS_SOURCE_HEIGHT)
      {
        selection->bottom = RPS_SOURCE_HEIGHT;
      }
      if (selection->right > RPS_SOURCE_WIDTH)
      {
        selection->right = RPS_SOURCE_WIDTH;
      }
      memset(rps_histogram, 0, sizeof(rps_histogram));
      for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
      {
        if (rps_component_labels[index] == selection->label)
        {
          ++rps_histogram[rps_depth_mm[index] - RPS_NEAR_MM];
        }
      }
      selection->reference_x100 = rps_percentile_x100(
          selection->count, RPS_RELATIVE_PERCENTILE);
    }
  }
  else
  {
    memset(rps_component_labels, 0, sizeof(rps_component_labels));
  }
}

static void rps_render_native_view(RPS_AI_ViewSelection_t view,
                                   const RPS_ObjectSelection_t *selection,
                                   uint8_t *output)
{
  memset(output, 0, RPS_SOURCE_PIXELS);
  for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
  {
    uint16_t millimetres = rps_depth_mm[index];
    uint32_t include = 0U;

    if ((millimetres < RPS_NEAR_MM) ||
        (millimetres > RPS_SENSOR_VALID_FAR_MM))
    {
      continue;
    }
    if (view == RPS_AI_VIEW_OBJECT_1)
    {
      include = 1U;
    }
    else if ((view == RPS_AI_VIEW_OBJECT_2) && (selection != NULL) &&
             (millimetres <= selection->cutoff_mm))
    {
      include = 1U;
    }
    else if ((view == RPS_AI_VIEW_OBJECT_3) && (selection != NULL) &&
             (selection->count != 0U) &&
             (rps_component_labels[index] == selection->label))
    {
      include = 1U;
    }
    if (include != 0U)
    {
      output[index] = rps_map_absolute(millimetres);
    }
  }
}

static void rps_render_selection(const RPS_ObjectSelection_t *selection,
                                 uint8_t *output)
{
  if (selection->count == 0U)
  {
    memset(output, 0, RPS_MODEL_PIXELS);
    return;
  }

  uint32_t crop_width = selection->right - selection->left;
  uint32_t crop_height = selection->bottom - selection->top;
  for (uint32_t row = 0U; row < crop_height; ++row)
  {
    for (uint32_t column = 0U; column < crop_width; ++column)
    {
      uint32_t source_index =
          ((selection->top + row) * RPS_SOURCE_WIDTH) +
          selection->left + column;
      rps_crop[(row * crop_width) + column] =
          (rps_component_labels[source_index] == selection->label) ?
          rps_map_relative(rps_depth_mm[source_index],
                           selection->reference_x100) : 0U;
    }
  }

  uint32_t resized_width;
  uint32_t resized_height;
  if ((RPS_RESIZE_WIDTH * crop_height) <=
      (RPS_RESIZE_HEIGHT * crop_width))
  {
    resized_width = RPS_RESIZE_WIDTH;
    resized_height = rps_round_even(crop_height * RPS_RESIZE_WIDTH,
                                    crop_width);
  }
  else
  {
    resized_height = RPS_RESIZE_HEIGHT;
    resized_width = rps_round_even(crop_width * RPS_RESIZE_HEIGHT,
                                   crop_height);
  }
  if (resized_width == 0U) resized_width = 1U;
  if (resized_height == 0U) resized_height = 1U;

  rps_resize_nearest(rps_crop, crop_width, crop_height, output,
                     resized_width, resized_height);
}

/* OBJECT 6 is intentionally much more aggressive than a normal grayscale
 * threshold. A 3x3 maximum pass first repairs one-pixel sensor dropouts and
 * the thin black stripes they create after resizing. Then every remaining
 * non-black pixel becomes fully white. The padded row buffers keep the pass
 * in-place and let Helium/MVE process 16 pixels at a time without another
 * 64x50 framebuffer. */
static void rps_flatten_binary(uint8_t *image, uint8_t threshold)
{
  uint8_t rows[3][RPS_MODEL_WIDTH + 2U];
  uint8_t *previous = rows[0];
  uint8_t *current = rows[1];
  uint8_t *next = rows[2];

  for (uint32_t pass = 0U; pass < RPS_BINARY_DILATION_PASSES; ++pass)
  {
    memset(previous, 0, RPS_MODEL_WIDTH + 2U);
    memset(current, 0, RPS_MODEL_WIDTH + 2U);
    memset(next, 0, RPS_MODEL_WIDTH + 2U);
    memcpy(&current[1], image, RPS_MODEL_WIDTH);
    if (RPS_MODEL_HEIGHT > 1U)
    {
      memcpy(&next[1], &image[RPS_MODEL_WIDTH], RPS_MODEL_WIDTH);
    }

    for (uint32_t row = 0U; row < RPS_MODEL_HEIGHT; ++row)
    {
#if (RPS_MVE_ACCELERATED == 1U)
      for (uint32_t column = 0U; column < RPS_MODEL_WIDTH; column += 16U)
      {
        mve_pred16_t predicate = vctp8q(RPS_MODEL_WIDTH - column);
        uint8x16_t maximum = vldrbq_z_u8(&previous[column], predicate);
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&previous[column + 1U], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&previous[column + 2U], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&current[column], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&current[column + 1U], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&current[column + 2U], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&next[column], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&next[column + 1U], predicate));
        maximum = vmaxq_u8(maximum,
                           vldrbq_z_u8(&next[column + 2U], predicate));
        vstrbq_p_u8(&image[(row * RPS_MODEL_WIDTH) + column], maximum,
                     predicate);
      }
#else
      for (uint32_t column = 0U; column < RPS_MODEL_WIDTH; ++column)
      {
        uint8_t maximum = 0U;
        const uint8_t *source_rows[3] = { previous, current, next };
        for (uint32_t source_row = 0U; source_row < 3U; ++source_row)
        {
          for (uint32_t source_column = column;
               source_column <= column + 2U; ++source_column)
          {
            if (source_rows[source_row][source_column] > maximum)
            {
              maximum = source_rows[source_row][source_column];
            }
          }
        }
        image[(row * RPS_MODEL_WIDTH) + column] = maximum;
      }
#endif

      uint8_t *old_previous = previous;
      previous = current;
      current = next;
      next = old_previous;
      memset(next, 0, RPS_MODEL_WIDTH + 2U);
      if ((row + 2U) < RPS_MODEL_HEIGHT)
      {
        memcpy(&next[1], &image[(row + 2U) * RPS_MODEL_WIDTH],
               RPS_MODEL_WIDTH);
      }
    }
  }

  for (uint32_t index = 0U; index < RPS_MODEL_PIXELS; ++index)
  {
    image[index] = (image[index] > threshold) ?
                   RPS_FLAT_FOREGROUND_VALUE : 0U;
  }
}

static void rps_preprocess(const float *depth, uint8_t *output,
                           RPS_AI_ViewSelection_t requested_view)
{
  RPS_ObjectSelection_t educational_selection;
  RPS_ObjectSelection_t model_selection;

  for (uint32_t index = 0U; index < RPS_SOURCE_PIXELS; ++index)
  {
    float value = depth[index];
    uint16_t millimetres = UINT16_MAX;
    if (isfinite(value) && (value > 0.0f) && (value < 65535.0f))
    {
      millimetres = (uint16_t)(value + 0.5f);
    }
    rps_depth_mm[index] = millimetres;
  }

  if (requested_view == RPS_AI_VIEW_OBJECT_1)
  {
    rps_render_native_view(requested_view, NULL,
                           rps_processing_view_snapshot);
  }
  else if ((requested_view >= RPS_AI_VIEW_OBJECT_2) &&
           (requested_view <= RPS_AI_VIEW_OBJECT_4))
  {
    rps_select_object(RPS_SENSOR_VALID_FAR_MM, &educational_selection);
    if (requested_view <= RPS_AI_VIEW_OBJECT_3)
    {
      rps_render_native_view(requested_view, &educational_selection,
                             rps_processing_view_snapshot);
    }
    else
    {
      rps_render_selection(&educational_selection,
                           rps_processing_view_snapshot);
    }
  }

  /* Production selection never admits pixels beyond 600 mm.  Rebuilding the
   * component map here also guarantees that a farther teaching-stage object
   * cannot leak into the model crop. */
  rps_select_object(RPS_MODEL_MAX_DISTANCE_MM, &model_selection);

  /* Build OBJECT 5 first. OBJECT 6 preserves the historical >0 teaching
   * silhouette, while OBJECT 7 lets the same normalized-depth threshold be
   * tuned interactively. The production NPU tensor uses the hardware-tested
   * fixed threshold of 210 regardless of the requested teaching view. Every
   * binary path includes the MVE-accelerated 3x3 repair pass. */
  rps_render_selection(&model_selection, output);
  if ((requested_view == RPS_AI_VIEW_OBJECT_5) ||
      (requested_view == RPS_AI_VIEW_OBJECT_6) ||
      (requested_view == RPS_AI_VIEW_OBJECT_7))
  {
    rps_copy_model_input(rps_processing_view_snapshot, output);
  }
  if (requested_view == RPS_AI_VIEW_OBJECT_6)
  {
    rps_flatten_binary(rps_processing_view_snapshot,
                       RPS_STAGE_6_BINARY_THRESHOLD);
  }
  else if (requested_view == RPS_AI_VIEW_OBJECT_7)
  {
    rps_flatten_binary(rps_processing_view_snapshot,
                       rps_object_7_threshold);
  }
  rps_flatten_binary(output, RPS_PRODUCTION_BINARY_THRESHOLD);

  rps_published_view = requested_view;
  if (requested_view == RPS_AI_VIEW_NPU)
  {
    rps_published_view_pixels = output;
    rps_published_view_width = RPS_MODEL_WIDTH;
    rps_published_view_height = RPS_MODEL_HEIGHT;
    rps_published_view_is_npu =
        (requested_view == RPS_AI_VIEW_NPU) ? 1U : 0U;
  }
  else
  {
    rps_published_view_pixels = rps_processing_view_snapshot;
    rps_published_view_width =
        (requested_view <= RPS_AI_VIEW_OBJECT_3) ? RPS_SOURCE_WIDTH :
                                                  RPS_MODEL_WIDTH;
    rps_published_view_height =
        (requested_view <= RPS_AI_VIEW_OBJECT_3) ? RPS_SOURCE_HEIGHT :
                                                  RPS_MODEL_HEIGHT;
    rps_published_view_is_npu = 0U;
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

  /* Neural-ART reuses its activation arena during inference, including the
   * input address. Keep one exact production snapshot plus the selected
   * educational view, then use Helium/MVE to feed the preallocated NPU input
   * without a scalar copy. */
  RPS_AI_ViewSelection_t requested_view = rps_requested_view;
  rps_preprocess(depth, rps_model_input_snapshot, requested_view);
  rps_model_input_frame = frame_id;
  rps_copy_model_input((uint8_t *)rps_input, rps_model_input_snapshot);
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
  rps_status.confidence_per_mille = RPS_AI_ScorePerMille(scores[best]);
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

void RPS_AI_SetViewSelection(RPS_AI_ViewSelection_t selection)
{
#if (APP_RPS_NPU_ENABLED == 1U)
  if ((uint32_t)selection <= (uint32_t)RPS_AI_VIEW_OBJECT_7)
  {
    rps_requested_view = selection;
  }
#else
  (void)selection;
#endif
}

void RPS_AI_SetObject7Threshold(uint32_t threshold)
{
#if (APP_RPS_NPU_ENABLED == 1U)
  rps_object_7_threshold = (threshold <= UINT8_MAX) ?
                           (uint8_t)threshold : UINT8_MAX;
#else
  (void)threshold;
#endif
}

int RPS_AI_GetImageView(RPS_AI_ImageView_t *view)
{
  if (view == NULL)
  {
    return -1;
  }

#if (APP_RPS_NPU_ENABLED == 1U)
  if ((rps_model_input_frame == UINT32_MAX) || (rps_input == NULL))
  {
    return -2;
  }
  view->pixels = rps_published_view_pixels;
  view->frame_id = rps_model_input_frame;
  view->width = rps_published_view_width;
  view->height = rps_published_view_height;
  view->mve_accelerated = RPS_MVE_ACCELERATED;
  view->is_npu_input = rps_published_view_is_npu;
  view->selection = rps_published_view;
  return 0;
#else
  view->pixels = NULL;
  view->frame_id = UINT32_MAX;
  view->width = 0U;
  view->height = 0U;
  view->mve_accelerated = 0U;
  view->is_npu_input = 0U;
  view->selection = RPS_AI_VIEW_NPU;
  return -2;
#endif
}

int RPS_AI_GetModelInputView(RPS_AI_ImageView_t *view)
{
  if (view == NULL)
  {
    return -1;
  }

#if (APP_RPS_NPU_ENABLED == 1U)
  if ((rps_model_input_frame == UINT32_MAX) || (rps_input == NULL))
  {
    return -2;
  }
  view->pixels = rps_model_input_snapshot;
  view->frame_id = rps_model_input_frame;
  view->width = RPS_MODEL_WIDTH;
  view->height = RPS_MODEL_HEIGHT;
  view->mve_accelerated = RPS_MVE_ACCELERATED;
  view->is_npu_input = 1U;
  view->selection = RPS_AI_VIEW_NPU;
  return 0;
#else
  view->pixels = NULL;
  view->frame_id = UINT32_MAX;
  view->width = 0U;
  view->height = 0U;
  view->mve_accelerated = 0U;
  view->is_npu_input = 0U;
  view->selection = RPS_AI_VIEW_NPU;
  return -2;
#endif
}

uint16_t RPS_AI_ScorePerMille(int8_t score)
{
  /* The current model output uses scale 1/256 and zero point -128. */
  uint32_t quantized_probability =
      (uint32_t)((int32_t)score - RPS_OUTPUT_ZERO_POINT);

  return (uint16_t)((quantized_probability * 1000U +
                     (RPS_OUTPUT_SCALE_DENOMINATOR / 2U)) /
                    RPS_OUTPUT_SCALE_DENOMINATOR);
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
