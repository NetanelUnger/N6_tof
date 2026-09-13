#include "display_app.h"

#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "debug_uart.h"
#include "gc9a01.h"
#include "main.h"

#define DISPLAY_EVENT_TX_COMPLETE  (1UL << 0)
#define DISPLAY_EVENT_TX_ERROR     (1UL << 1)
#define DISPLAY_EVENT_FRAME_READY  (1UL << 2)
#define DISPLAY_EVENT_MODE_CHANGED (1UL << 3)
#define DISPLAY_TRANSFER_TIMEOUT   (2U * TX_TIMER_TICKS_PER_SECOND)
#define DISPLAY_TEXT_SCALE         (2U)
#define DISPLAY_GLYPH_WIDTH        (5U)
#define DISPLAY_GLYPH_HEIGHT       (7U)
#define DISPLAY_GLYPH_ADVANCE      (6U)
#define DISPLAY_TEXT               "SYSTEM IS LOADING"
#define DISPLAY_TEXT_LENGTH        (sizeof(DISPLAY_TEXT) - 1U)
#define DISPLAY_TEXT_WIDTH         \
  (((DISPLAY_TEXT_LENGTH * DISPLAY_GLYPH_ADVANCE) - 1U) * DISPLAY_TEXT_SCALE)
#define DISPLAY_TEXT_HEIGHT        (DISPLAY_GLYPH_HEIGHT * DISPLAY_TEXT_SCALE)
#define DISPLAY_MAP_SCALE          (4U)
#define DISPLAY_MAP_WIDTH          \
  (DISPLAY_APP_MAP_SOURCE_WIDTH * DISPLAY_MAP_SCALE)
#define DISPLAY_MAP_HEIGHT         \
  (DISPLAY_APP_MAP_SOURCE_HEIGHT * DISPLAY_MAP_SCALE)
#define DISPLAY_MAP_X              ((GC9A01_WIDTH - DISPLAY_MAP_WIDTH) / 2U)
#define DISPLAY_MAP_Y              ((GC9A01_HEIGHT - DISPLAY_MAP_HEIGHT) / 2U)
#define DISPLAY_RESULT_SCALE       (2U)
#define DISPLAY_RESULT_AREA_WIDTH  (120U)
#define DISPLAY_RESULT_AREA_HEIGHT (DISPLAY_GLYPH_HEIGHT * DISPLAY_RESULT_SCALE)
#define DISPLAY_RESULT_AREA_X      ((GC9A01_WIDTH - DISPLAY_RESULT_AREA_WIDTH) / 2U)
#define DISPLAY_RESULT_AREA_Y      (210U)
#define DISPLAY_MAP_PIXEL_BYTES    \
  (DISPLAY_APP_MAP_SOURCE_WIDTH * DISPLAY_APP_MAP_SOURCE_HEIGHT * 2U)
#define DISPLAY_RGB565(red, green, blue) \
  (uint16_t)((((uint16_t)(red) & 0xF8U) << 8) | \
             (((uint16_t)(green) & 0xFCU) << 3) | \
             ((uint16_t)(blue) >> 3))

extern SPI_HandleTypeDef hspi4;

typedef struct
{
  uint8_t command;
  uint8_t length;
  uint16_t delay_ms;
  uint8_t data[14];
} Display_InitCommand_t;

typedef struct
{
  uint32_t frame_number;
  uint16_t width;
  uint16_t height;
  Display_App_FrameReleaseCallback_t release_callback;
  void *release_context;
  uint32_t rps_frame_number;
  uint16_t rps_confidence_per_mille;
  uint8_t rps_class_id;
  uint8_t rps_valid;
  uint8_t pixels[DISPLAY_MAP_PIXEL_BYTES];
} Display_Frame_t;

_Static_assert(sizeof(Display_Frame_t) <= DISPLAY_APP_FRAME_STORAGE_SIZE,
               "Display frame metadata and RGB565 pixels exceed storage contract");

static TX_EVENT_FLAGS_GROUP display_events;
static GC9A01_Handle_t display_handle;
static volatile uint32_t display_initialized;
static volatile uint32_t display_map_enabled;
static volatile uint32_t display_frame_in_flight;
static volatile Display_Frame_t *display_pending_frame;
static volatile uint32_t display_submitted_frames;
static volatile uint32_t display_rendered_frames;
static volatile uint32_t display_dropped_frames;
static volatile uint32_t display_render_errors;
static volatile uint32_t display_last_submitted_frame;
static volatile uint32_t display_last_rendered_frame;
static volatile uint32_t display_last_rendered_rps_frame;
static volatile uint16_t display_last_rendered_rps_confidence_per_mille;
static volatile uint8_t display_last_rendered_rps_class_id;
static volatile uint8_t display_last_rendered_rps_valid;
static volatile uint32_t display_dma_completions;
static volatile uint32_t display_dma_errors;
static volatile uint32_t display_last_render_dma_completions;
static volatile uint32_t display_clear_operations;

/* All display paths are sent synchronously one DMA row at a time.  Reusing one
 * full-width row avoids a 72 KiB scaled framebuffer in the limited LRun SRAM. */
__ALIGNED(32) static uint8_t display_row_pixels[GC9A01_WIDTH * 2U];

static const uint16_t display_depth_palette[] = {
  DISPLAY_RGB565(255U,   0U,   0U), DISPLAY_RGB565(255U,  95U,   0U),
  DISPLAY_RGB565(255U, 135U,   0U), DISPLAY_RGB565(255U, 175U,   0U),
  DISPLAY_RGB565(255U, 215U,   0U), DISPLAY_RGB565(255U, 255U,   0U),
  DISPLAY_RGB565(215U, 255U,   0U), DISPLAY_RGB565(175U, 255U,   0U),
  DISPLAY_RGB565(135U, 255U,   0U), DISPLAY_RGB565( 95U, 255U,   0U),
  DISPLAY_RGB565(  0U, 255U,   0U), DISPLAY_RGB565(  0U, 255U,  95U),
  DISPLAY_RGB565(  0U, 255U, 135U), DISPLAY_RGB565(  0U, 255U, 175U),
  DISPLAY_RGB565(  0U, 255U, 215U), DISPLAY_RGB565(  0U, 255U, 255U),
  DISPLAY_RGB565(  0U, 215U, 255U), DISPLAY_RGB565(  0U, 175U, 255U),
  DISPLAY_RGB565(  0U, 135U, 255U), DISPLAY_RGB565(  0U,  95U, 255U),
  DISPLAY_RGB565(  0U,   0U, 255U)
};

static const Display_InitCommand_t display_init_commands[] = {
  {0xEFU, 0U, 0U, {0}},
  {0xEBU, 1U, 0U, {0x14U}},
  {0xFEU, 0U, 0U, {0}},
  {0xEFU, 0U, 0U, {0}},
  {0xEBU, 1U, 0U, {0x14U}},
  {0x84U, 1U, 0U, {0x40U}},
  {0x85U, 1U, 0U, {0xFFU}},
  {0x86U, 1U, 0U, {0xFFU}},
  {0x87U, 1U, 0U, {0xFFU}},
  {0x88U, 1U, 0U, {0x0AU}},
  {0x89U, 1U, 0U, {0x21U}},
  {0x8AU, 1U, 0U, {0x00U}},
  {0x8BU, 1U, 0U, {0x80U}},
  {0x8CU, 1U, 0U, {0x01U}},
  {0x8DU, 1U, 0U, {0x01U}},
  {0x8EU, 1U, 0U, {0xFFU}},
  {0x8FU, 1U, 0U, {0xFFU}},
  {0xB6U, 2U, 0U, {0x00U, 0x20U}},
  {0x36U, 1U, 0U, {0x08U}},
  {0x3AU, 1U, 0U, {0x05U}},
  {0x90U, 4U, 0U, {0x08U, 0x08U, 0x08U, 0x08U}},
  {0xBDU, 1U, 0U, {0x06U}},
  {0xBCU, 1U, 0U, {0x00U}},
  {0xFFU, 3U, 0U, {0x60U, 0x01U, 0x04U}},
  {0xC3U, 1U, 0U, {0x13U}},
  {0xC4U, 1U, 0U, {0x13U}},
  {0xC9U, 1U, 0U, {0x22U}},
  {0xBEU, 1U, 0U, {0x11U}},
  {0xE1U, 2U, 0U, {0x10U, 0x0EU}},
  {0xDFU, 3U, 0U, {0x21U, 0x0CU, 0x02U}},
  {0xF0U, 6U, 0U, {0x45U, 0x09U, 0x08U, 0x08U, 0x26U, 0x2AU}},
  {0xF1U, 6U, 0U, {0x43U, 0x70U, 0x72U, 0x36U, 0x37U, 0x6FU}},
  {0xF2U, 6U, 0U, {0x45U, 0x09U, 0x08U, 0x08U, 0x26U, 0x2AU}},
  {0xF3U, 6U, 0U, {0x43U, 0x70U, 0x72U, 0x36U, 0x37U, 0x6FU}},
  {0xEDU, 2U, 0U, {0x1BU, 0x0BU}},
  {0xAEU, 1U, 0U, {0x77U}},
  {0xCDU, 1U, 0U, {0x63U}},
  {0x70U, 9U, 0U, {0x07U, 0x07U, 0x04U, 0x0EU, 0x0FU, 0x09U, 0x07U, 0x08U, 0x03U}},
  {0xE8U, 1U, 0U, {0x34U}},
  {0x62U, 12U, 0U, {0x18U, 0x0DU, 0x71U, 0xEDU, 0x70U, 0x70U, 0x18U, 0x0FU, 0x71U, 0xEFU, 0x70U, 0x70U}},
  {0x63U, 12U, 0U, {0x18U, 0x11U, 0x71U, 0xF1U, 0x70U, 0x70U, 0x18U, 0x13U, 0x71U, 0xF3U, 0x70U, 0x70U}},
  {0x64U, 7U, 0U, {0x28U, 0x29U, 0xF1U, 0x01U, 0xF1U, 0x00U, 0x07U}},
  {0x66U, 10U, 0U, {0x3CU, 0x00U, 0xCDU, 0x67U, 0x45U, 0x45U, 0x10U, 0x00U, 0x00U, 0x00U}},
  {0x67U, 10U, 0U, {0x00U, 0x3CU, 0x00U, 0x00U, 0x00U, 0x01U, 0x54U, 0x10U, 0x32U, 0x98U}},
  {0x74U, 7U, 0U, {0x10U, 0x85U, 0x80U, 0x00U, 0x00U, 0x4EU, 0x00U}},
  {0x98U, 2U, 0U, {0x3EU, 0x07U}},
  {0x35U, 0U, 0U, {0}},
  {0x21U, 0U, 0U, {0}},
  {0x11U, 0U, 120U, {0}},
  {0x29U, 0U, 20U, {0}}
};

static ULONG Display_MillisecondsToTicks(uint32_t milliseconds)
{
  ULONG ticks = ((ULONG)milliseconds * TX_TIMER_TICKS_PER_SECOND + 999UL) / 1000UL;
  return (ticks == 0UL) ? 1UL : ticks;
}

static void Display_TransferCallback(GC9A01_TransferResult_t result,
                                     void *context)
{
  TX_EVENT_FLAGS_GROUP *events = (TX_EVENT_FLAGS_GROUP *)context;
  ULONG flag = (result == GC9A01_TRANSFER_OK) ? DISPLAY_EVENT_TX_COMPLETE
                                               : DISPLAY_EVENT_TX_ERROR;
  if (result == GC9A01_TRANSFER_OK)
  {
    ++display_dma_completions;
  }
  else
  {
    ++display_dma_errors;
  }
  (void)tx_event_flags_set(events, flag, TX_OR);
}

static UINT Display_Transmit(bool data_mode, const uint8_t *data,
                             uint16_t length, bool release_cs)
{
  ULONG ignored_flags;
  ULONG actual_flags;

  (void)tx_event_flags_get(&display_events,
                           DISPLAY_EVENT_TX_COMPLETE | DISPLAY_EVENT_TX_ERROR,
                           TX_OR_CLEAR, &ignored_flags, TX_NO_WAIT);

  if (GC9A01_TransmitAsync(&display_handle, data_mode, data, length,
                           release_cs) != HAL_OK)
  {
    return TX_NOT_AVAILABLE;
  }

  if (tx_event_flags_get(&display_events,
                         DISPLAY_EVENT_TX_COMPLETE | DISPLAY_EVENT_TX_ERROR,
                         TX_OR_CLEAR, &actual_flags,
                         DISPLAY_TRANSFER_TIMEOUT) != TX_SUCCESS)
  {
    (void)GC9A01_Abort(&display_handle);
    return TX_NOT_DONE;
  }

  return ((actual_flags & DISPLAY_EVENT_TX_ERROR) == 0UL) ? TX_SUCCESS
                                                           : TX_NOT_DONE;
}

static UINT Display_WriteCommand(uint8_t command, const uint8_t *data,
                                 uint8_t length)
{
  if (Display_Transmit(false, &command, 1U, length == 0U) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }
  if ((length != 0U) &&
      (Display_Transmit(true, data, length, true) != TX_SUCCESS))
  {
    return TX_NOT_DONE;
  }
  return TX_SUCCESS;
}

static UINT Display_SetAddressWindow(uint16_t x, uint16_t y,
                                     uint16_t width, uint16_t height)
{
  uint16_t x_end = (uint16_t)(x + width - 1U);
  uint16_t y_end = (uint16_t)(y + height - 1U);
  uint8_t coordinates[4];
  uint8_t memory_write = 0x2CU;

  coordinates[0] = (uint8_t)(x >> 8);
  coordinates[1] = (uint8_t)x;
  coordinates[2] = (uint8_t)(x_end >> 8);
  coordinates[3] = (uint8_t)x_end;
  if (Display_WriteCommand(0x2AU, coordinates, sizeof(coordinates)) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  coordinates[0] = (uint8_t)(y >> 8);
  coordinates[1] = (uint8_t)y;
  coordinates[2] = (uint8_t)(y_end >> 8);
  coordinates[3] = (uint8_t)y_end;
  if (Display_WriteCommand(0x2BU, coordinates, sizeof(coordinates)) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  return Display_Transmit(false, &memory_write, 1U, false);
}

static UINT Display_InitializePanel(void)
{
  GC9A01_Config_t config = {
    .spi = &hspi4,
    .cs_port = LCD_CS_GPIO_Port,
    .cs_pin = LCD_CS_Pin,
    .dc_port = LCD_DC_GPIO_Port,
    .dc_pin = LCD_DC_Pin,
    .reset_port = LCD_RST_GPIO_Port,
    .reset_pin = LCD_RST_Pin,
    .transfer_callback = Display_TransferCallback,
    .callback_context = &display_events
  };
  size_t index;

  if (GC9A01_Open(&display_handle, &config) != HAL_OK)
  {
    return TX_NOT_AVAILABLE;
  }

  tx_thread_sleep(Display_MillisecondsToTicks(10U));
  GC9A01_SetReset(&display_handle, true);
  tx_thread_sleep(Display_MillisecondsToTicks(120U));

  for (index = 0U;
       index < (sizeof(display_init_commands) / sizeof(display_init_commands[0]));
       ++index)
  {
    const Display_InitCommand_t *entry = &display_init_commands[index];
    if (Display_WriteCommand(entry->command, entry->data, entry->length) != TX_SUCCESS)
    {
      return TX_NOT_DONE;
    }
    if (entry->delay_ms != 0U)
    {
      tx_thread_sleep(Display_MillisecondsToTicks(entry->delay_ms));
    }
  }
  return TX_SUCCESS;
}

static UINT Display_Clear(void)
{
  uint32_t remaining = GC9A01_WIDTH * GC9A01_HEIGHT * 2U;

  memset(display_row_pixels, 0, sizeof(display_row_pixels));
  if (Display_SetAddressWindow(0U, 0U, GC9A01_WIDTH, GC9A01_HEIGHT) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  while (remaining != 0U)
  {
    uint16_t chunk = (remaining > sizeof(display_row_pixels))
                       ? (uint16_t)sizeof(display_row_pixels)
                       : (uint16_t)remaining;
    remaining -= chunk;
    if (Display_Transmit(true, display_row_pixels, chunk,
                         remaining == 0U) != TX_SUCCESS)
    {
      return TX_NOT_DONE;
    }
  }
  return TX_SUCCESS;
}

static const uint8_t *Display_Glyph(char character)
{
  static const uint8_t blank[5] = {0, 0, 0, 0, 0};
  static const uint8_t glyph_a[5] = {0x7EU, 0x11U, 0x11U, 0x11U, 0x7EU};
  static const uint8_t glyph_c[5] = {0x3EU, 0x41U, 0x41U, 0x41U, 0x22U};
  static const uint8_t glyph_d[5] = {0x7FU, 0x41U, 0x41U, 0x22U, 0x1CU};
  static const uint8_t glyph_e[5] = {0x7FU, 0x49U, 0x49U, 0x49U, 0x41U};
  static const uint8_t glyph_f[5] = {0x7FU, 0x09U, 0x09U, 0x09U, 0x01U};
  static const uint8_t glyph_g[5] = {0x3EU, 0x41U, 0x49U, 0x49U, 0x7AU};
  static const uint8_t glyph_h[5] = {0x7FU, 0x08U, 0x08U, 0x08U, 0x7FU};
  static const uint8_t glyph_i[5] = {0x00U, 0x41U, 0x7FU, 0x41U, 0x00U};
  static const uint8_t glyph_k[5] = {0x7FU, 0x08U, 0x14U, 0x22U, 0x41U};
  static const uint8_t glyph_l[5] = {0x7FU, 0x40U, 0x40U, 0x40U, 0x40U};
  static const uint8_t glyph_m[5] = {0x7FU, 0x02U, 0x0CU, 0x02U, 0x7FU};
  static const uint8_t glyph_n[5] = {0x7FU, 0x04U, 0x08U, 0x10U, 0x7FU};
  static const uint8_t glyph_o[5] = {0x3EU, 0x41U, 0x41U, 0x41U, 0x3EU};
  static const uint8_t glyph_p[5] = {0x7FU, 0x09U, 0x09U, 0x09U, 0x06U};
  static const uint8_t glyph_r[5] = {0x7FU, 0x09U, 0x19U, 0x29U, 0x46U};
  static const uint8_t glyph_s[5] = {0x46U, 0x49U, 0x49U, 0x49U, 0x31U};
  static const uint8_t glyph_t[5] = {0x01U, 0x01U, 0x7FU, 0x01U, 0x01U};
  static const uint8_t glyph_y[5] = {0x03U, 0x04U, 0x78U, 0x04U, 0x03U};
  static const uint8_t glyph_u[5] = {0x3FU, 0x40U, 0x40U, 0x40U, 0x3FU};
  static const uint8_t glyph_w[5] = {0x7FU, 0x20U, 0x18U, 0x20U, 0x7FU};

  switch (character)
  {
    case 'A': return glyph_a;
    case 'C': return glyph_c;
    case 'D': return glyph_d;
    case 'E': return glyph_e;
    case 'F': return glyph_f;
    case 'G': return glyph_g;
    case 'H': return glyph_h;
    case 'I': return glyph_i;
    case 'K': return glyph_k;
    case 'L': return glyph_l;
    case 'M': return glyph_m;
    case 'N': return glyph_n;
    case 'O': return glyph_o;
    case 'P': return glyph_p;
    case 'R': return glyph_r;
    case 'S': return glyph_s;
    case 'T': return glyph_t;
    case 'U': return glyph_u;
    case 'W': return glyph_w;
    case 'Y': return glyph_y;
    default: return blank;
  }
}

static UINT Display_RenderResultText(const Display_Frame_t *frame)
{
  const char *text = "";
  size_t text_length;
  uint32_t text_width;
  uint32_t text_x;
  uint32_t row;

  if ((frame != NULL) && (frame->rps_valid != 0U))
  {
    text = RPS_AI_ClassDisplayName(frame->rps_class_id);
  }
  else if (frame != NULL)
  {
    text = "WAITING";
  }
  text_length = strlen(text);
  text_width = (text_length == 0U) ? 0U :
      (((uint32_t)text_length * DISPLAY_GLYPH_ADVANCE - 1U) *
       DISPLAY_RESULT_SCALE);
  text_x = (DISPLAY_RESULT_AREA_WIDTH - text_width) / 2U;

  if (Display_SetAddressWindow(DISPLAY_RESULT_AREA_X, DISPLAY_RESULT_AREA_Y,
                               DISPLAY_RESULT_AREA_WIDTH,
                               DISPLAY_RESULT_AREA_HEIGHT) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }
  for (row = 0U; row < DISPLAY_RESULT_AREA_HEIGHT; ++row)
  {
    uint32_t glyph_row = row / DISPLAY_RESULT_SCALE;
    uint32_t x;
    memset(display_row_pixels, 0, DISPLAY_RESULT_AREA_WIDTH * 2U);
    for (x = 0U; x < text_width; ++x)
    {
      uint32_t unscaled_x = x / DISPLAY_RESULT_SCALE;
      uint32_t character_index = unscaled_x / DISPLAY_GLYPH_ADVANCE;
      uint32_t glyph_column = unscaled_x % DISPLAY_GLYPH_ADVANCE;
      if ((character_index < text_length) &&
          (glyph_column < DISPLAY_GLYPH_WIDTH) &&
          ((Display_Glyph(text[character_index])[glyph_column] &
            (1U << glyph_row)) != 0U))
      {
        size_t offset = ((size_t)text_x + x) * 2U;
        display_row_pixels[offset] = 0xFFU;
        display_row_pixels[offset + 1U] = 0xFFU;
      }
    }
    if (Display_Transmit(true, display_row_pixels,
                         DISPLAY_RESULT_AREA_WIDTH * 2U,
                         row == (DISPLAY_RESULT_AREA_HEIGHT - 1U)) != TX_SUCCESS)
    {
      return TX_NOT_DONE;
    }
  }
  return TX_SUCCESS;
}

static void Display_RenderLoadingTextRow(uint32_t y)
{
  uint32_t x;
  uint32_t glyph_row = y / DISPLAY_TEXT_SCALE;

  memset(display_row_pixels, 0, sizeof(display_row_pixels));
  for (x = 0U; x < DISPLAY_TEXT_WIDTH; ++x)
  {
    uint32_t unscaled_x = x / DISPLAY_TEXT_SCALE;
    uint32_t character_index = unscaled_x / DISPLAY_GLYPH_ADVANCE;
    uint32_t glyph_column = unscaled_x % DISPLAY_GLYPH_ADVANCE;
    bool foreground = false;

    if ((character_index < DISPLAY_TEXT_LENGTH) &&
        (glyph_column < DISPLAY_GLYPH_WIDTH))
    {
      const uint8_t *glyph = Display_Glyph(DISPLAY_TEXT[character_index]);
      foreground = ((glyph[glyph_column] & (1U << glyph_row)) != 0U);
    }

    if (foreground)
    {
      uint32_t offset = x * 2U;
      display_row_pixels[offset] = 0xFFU;
      display_row_pixels[offset + 1U] = 0xFFU;
    }
  }
}

static UINT Display_ShowLoadingText(void)
{
  uint16_t x = (uint16_t)((GC9A01_WIDTH - DISPLAY_TEXT_WIDTH) / 2U);
  uint16_t y = (uint16_t)((GC9A01_HEIGHT - DISPLAY_TEXT_HEIGHT) / 2U);
  uint32_t row;

  if (Display_SetAddressWindow(x, y, DISPLAY_TEXT_WIDTH,
                               DISPLAY_TEXT_HEIGHT) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  for (row = 0U; row < DISPLAY_TEXT_HEIGHT; ++row)
  {
    Display_RenderLoadingTextRow(row);
    if (Display_Transmit(true, display_row_pixels,
                         (uint16_t)(DISPLAY_TEXT_WIDTH * 2U),
                         row == (DISPLAY_TEXT_HEIGHT - 1U)) != TX_SUCCESS)
    {
      return TX_NOT_DONE;
    }
  }
  return TX_SUCCESS;
}

static uint16_t Display_DepthToRgb565(float distance_mm,
                                      uint16_t minimum_mm,
                                      uint16_t maximum_mm)
{
  size_t palette_count = sizeof(display_depth_palette) /
                         sizeof(display_depth_palette[0]);
  uint32_t distance;
  size_t index;

  if (!isfinite(distance_mm) || (distance_mm <= 0.0f) ||
      (maximum_mm <= minimum_mm))
  {
    return 0U;
  }

  distance = (uint32_t)distance_mm;
  if (distance <= minimum_mm)
  {
    return display_depth_palette[0];
  }
  if (distance >= maximum_mm)
  {
    return display_depth_palette[palette_count - 1U];
  }

  index = ((size_t)(distance - minimum_mm) * (palette_count - 1U)) /
          (size_t)(maximum_mm - minimum_mm);
  return display_depth_palette[index];
}

static void Display_EncodeDepthFrame(Display_Frame_t *frame,
                                     const float *depth,
                                     uint16_t minimum_mm,
                                     uint16_t maximum_mm)
{
  size_t pixel_count = (size_t)frame->width * frame->height;
  size_t index;

  for (index = 0U; index < pixel_count; ++index)
  {
    uint16_t color = Display_DepthToRgb565(depth[index], minimum_mm,
                                           maximum_mm);
    frame->pixels[index * 2U] = (uint8_t)(color >> 8);
    frame->pixels[(index * 2U) + 1U] = (uint8_t)color;
  }
}

static UINT Display_RenderMapFrame(const Display_Frame_t *frame)
{
  uint32_t source_y;

  if ((frame == NULL) ||
      (frame->width != DISPLAY_APP_MAP_SOURCE_WIDTH) ||
      (frame->height != DISPLAY_APP_MAP_SOURCE_HEIGHT))
  {
    return TX_PTR_ERROR;
  }

  if (Display_SetAddressWindow(DISPLAY_MAP_X, DISPLAY_MAP_Y,
                               DISPLAY_MAP_WIDTH,
                               DISPLAY_MAP_HEIGHT) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  for (source_y = 0U; source_y < frame->height; ++source_y)
  {
    uint32_t source_x;
    uint32_t repeat_y;
    size_t row_source = (size_t)source_y * frame->width * 2U;

    for (source_x = 0U; source_x < frame->width; ++source_x)
    {
      uint8_t high = frame->pixels[row_source + (source_x * 2U)];
      uint8_t low = frame->pixels[row_source + (source_x * 2U) + 1U];
      uint32_t repeat_x;

      for (repeat_x = 0U; repeat_x < DISPLAY_MAP_SCALE; ++repeat_x)
      {
        size_t destination =
            ((size_t)source_x * DISPLAY_MAP_SCALE + repeat_x) * 2U;
        display_row_pixels[destination] = high;
        display_row_pixels[destination + 1U] = low;
      }
    }

    for (repeat_y = 0U; repeat_y < DISPLAY_MAP_SCALE; ++repeat_y)
    {
      bool final_row =
          (source_y == (frame->height - 1U)) &&
          (repeat_y == (DISPLAY_MAP_SCALE - 1U));
      if (Display_Transmit(true, display_row_pixels,
                           (uint16_t)(DISPLAY_MAP_WIDTH * 2U),
                           final_row) != TX_SUCCESS)
      {
        return TX_NOT_DONE;
      }
    }
  }
  return TX_SUCCESS;
}

static UINT Display_ClearMapArea(void)
{
  uint32_t row;

  memset(display_row_pixels, 0, DISPLAY_MAP_WIDTH * 2U);
  if (Display_SetAddressWindow(DISPLAY_MAP_X, DISPLAY_MAP_Y,
                               DISPLAY_MAP_WIDTH,
                               DISPLAY_MAP_HEIGHT) != TX_SUCCESS)
  {
    return TX_NOT_DONE;
  }

  for (row = 0U; row < DISPLAY_MAP_HEIGHT; ++row)
  {
    if (Display_Transmit(true, display_row_pixels,
                         (uint16_t)(DISPLAY_MAP_WIDTH * 2U),
                         row == (DISPLAY_MAP_HEIGHT - 1U)) != TX_SUCCESS)
    {
      return TX_NOT_DONE;
    }
  }
  ++display_clear_operations;
  return Display_RenderResultText(NULL);
}

void Display_App_SetMapEnabled(uint32_t enabled)
{
  display_map_enabled = (enabled != 0U) ? 1U : 0U;
  (void)tx_event_flags_set(&display_events, DISPLAY_EVENT_MODE_CHANGED, TX_OR);
}

uint32_t Display_App_IsMapEnabled(void)
{
  return display_map_enabled;
}

UINT Display_App_SubmitDepthFrame(
    void *storage, size_t storage_size, const float *depth,
    uint8_t width, uint8_t height, uint32_t frame_number,
    uint16_t minimum_mm, uint16_t maximum_mm,
    const RPS_AI_Status_t *rps_status,
    Display_App_FrameReleaseCallback_t release_callback,
    void *release_context)
{
  Display_Frame_t *frame;
  UINT event_status;
  TX_INTERRUPT_SAVE_AREA

  if ((storage == NULL) || (depth == NULL) || (release_callback == NULL))
  {
    return TX_PTR_ERROR;
  }
  if ((storage_size < sizeof(Display_Frame_t)) ||
      (width != DISPLAY_APP_MAP_SOURCE_WIDTH) ||
      (height != DISPLAY_APP_MAP_SOURCE_HEIGHT) ||
      (maximum_mm <= minimum_mm))
  {
    return TX_SIZE_ERROR;
  }

  TX_DISABLE
  if ((display_initialized == 0U) || (display_map_enabled == 0U))
  {
    TX_RESTORE
    return TX_NOT_AVAILABLE;
  }
  if (display_frame_in_flight != 0U)
  {
    ++display_dropped_frames;
    TX_RESTORE
    return TX_QUEUE_FULL;
  }
  display_frame_in_flight = 1U;
  TX_RESTORE

  frame = (Display_Frame_t *)storage;
  frame->frame_number = frame_number;
  frame->width = width;
  frame->height = height;
  frame->release_callback = release_callback;
  frame->release_context = release_context;
  frame->rps_valid = ((rps_status != NULL) &&
                      (rps_status->enabled != 0U) &&
                      (rps_status->ready != 0U) &&
                      (rps_status->runs != 0U) &&
                      (rps_status->last_frame == frame_number)) ? 1U : 0U;
  frame->rps_frame_number = (rps_status != NULL) ?
                            rps_status->last_frame : UINT32_MAX;
  frame->rps_confidence_per_mille = (rps_status != NULL) ?
                                    rps_status->confidence_per_mille : 0U;
  frame->rps_class_id = (rps_status != NULL) ? rps_status->class_id : 0U;
  Display_EncodeDepthFrame(frame, depth, minimum_mm, maximum_mm);

  TX_DISABLE
  if (display_map_enabled == 0U)
  {
    display_frame_in_flight = 0U;
    TX_RESTORE
    return TX_NOT_AVAILABLE;
  }
  display_pending_frame = frame;
  ++display_submitted_frames;
  display_last_submitted_frame = frame_number;
  TX_RESTORE

  event_status = tx_event_flags_set(&display_events,
                                    DISPLAY_EVENT_FRAME_READY, TX_OR);
  if (event_status != TX_SUCCESS)
  {
    TX_DISABLE
    display_pending_frame = NULL;
    display_frame_in_flight = 0U;
    ++display_dropped_frames;
    TX_RESTORE
  }
  return event_status;
}

void Display_App_GetStatus(Display_App_Status_t *status)
{
  TX_INTERRUPT_SAVE_AREA

  if (status == NULL)
  {
    return;
  }

  TX_DISABLE
  status->initialized = display_initialized;
  status->map_enabled = display_map_enabled;
  status->frame_in_flight = display_frame_in_flight;
  status->submitted_frames = display_submitted_frames;
  status->rendered_frames = display_rendered_frames;
  status->dropped_frames = display_dropped_frames;
  status->render_errors = display_render_errors;
  status->last_submitted_frame = display_last_submitted_frame;
  status->last_rendered_frame = display_last_rendered_frame;
  status->last_rendered_rps_frame = display_last_rendered_rps_frame;
  status->last_rendered_rps_confidence_per_mille =
      display_last_rendered_rps_confidence_per_mille;
  status->last_rendered_rps_class_id = display_last_rendered_rps_class_id;
  status->last_rendered_rps_valid = display_last_rendered_rps_valid;
  status->dma_completions = display_dma_completions;
  status->dma_errors = display_dma_errors;
  status->last_render_dma_completions =
      display_last_render_dma_completions;
  status->clear_operations = display_clear_operations;
  TX_RESTORE
}

UINT Display_App_Init(void)
{
  return tx_event_flags_create(&display_events, "GC9A01 DMA events");
}

void Display_App_Run(void)
{
  ULONG actual_flags;

  Debug_UART_Log("DISPLAY", "GC9A01 task started on SPI4 TX DMA");

  if ((Display_InitializePanel() != TX_SUCCESS) ||
      (Display_Clear() != TX_SUCCESS) ||
      (Display_ShowLoadingText() != TX_SUCCESS))
  {
    Debug_UART_Log("DISPLAY", "ERROR: GC9A01 initialization/transfer failed");
  }
  else
  {
    display_initialized = 1U;
    Debug_UART_Log("DISPLAY", "SYSTEM IS LOADING rendered");
  }

  /* This task is the sole display/SPI owner. At most one transformed raw slot
   * can be owned by it; the release callback returns that slot only after every
   * scaled RGB565 row has completed through SPI DMA. */
  for (;;)
  {
    UINT wait_status = tx_event_flags_get(
        &display_events, DISPLAY_EVENT_FRAME_READY | DISPLAY_EVENT_MODE_CHANGED,
        TX_OR_CLEAR, &actual_flags, TX_WAIT_FOREVER);
    if (wait_status != TX_SUCCESS)
    {
      Debug_UART_Log("DISPLAY", "ERROR: event wait failed: %u",
                     (unsigned int)wait_status);
      continue;
    }

    if ((actual_flags & DISPLAY_EVENT_FRAME_READY) != 0UL)
    {
      Display_Frame_t *frame = (Display_Frame_t *)display_pending_frame;
      uint32_t dma_before = display_dma_completions;
      UINT render_status = TX_NOT_AVAILABLE;

      if ((frame != NULL) && (display_map_enabled != 0U) &&
          (display_initialized != 0U))
      {
        render_status = Display_RenderMapFrame(frame);
        if (render_status == TX_SUCCESS)
        {
          render_status = Display_RenderResultText(frame);
        }
      }

      if (render_status == TX_SUCCESS)
      {
        ++display_rendered_frames;
        display_last_rendered_frame = frame->frame_number;
        display_last_rendered_rps_frame = frame->rps_frame_number;
        display_last_rendered_rps_confidence_per_mille =
            frame->rps_confidence_per_mille;
        display_last_rendered_rps_class_id = frame->rps_class_id;
        display_last_rendered_rps_valid = frame->rps_valid;
        display_last_render_dma_completions =
            display_dma_completions - dma_before;
        if ((display_rendered_frames == 1U) ||
            ((display_rendered_frames % 10U) == 0U))
        {
          Debug_UART_Log(
              "DISPLAY",
              "frame rendered: source=%lu submitted=%lu rendered=%lu dropped=%lu dma/frame=%lu",
              (unsigned long)frame->frame_number,
              (unsigned long)display_submitted_frames,
              (unsigned long)display_rendered_frames,
              (unsigned long)display_dropped_frames,
              (unsigned long)display_last_render_dma_completions);
        }
      }
      else if (render_status != TX_NOT_AVAILABLE)
      {
        ++display_render_errors;
        Debug_UART_Log("DISPLAY", "ERROR: frame %lu render failed: %u",
                       (frame != NULL) ?
                           (unsigned long)frame->frame_number : 0UL,
                       (unsigned int)render_status);
      }

      if (frame != NULL)
      {
        Display_App_FrameReleaseCallback_t release_callback =
            frame->release_callback;
        void *release_context = frame->release_context;
        TX_INTERRUPT_SAVE_AREA

        TX_DISABLE
        display_pending_frame = NULL;
        display_frame_in_flight = 0U;
        TX_RESTORE
        release_callback(release_context);
      }
    }

    if ((display_map_enabled == 0U) && (display_initialized != 0U) &&
        (((actual_flags & DISPLAY_EVENT_MODE_CHANGED) != 0UL) ||
         ((actual_flags & DISPLAY_EVENT_FRAME_READY) != 0UL)))
    {
      if (Display_ClearMapArea() != TX_SUCCESS)
      {
        ++display_render_errors;
        Debug_UART_Log("DISPLAY", "ERROR: map-area clear failed");
      }
      else
      {
        Debug_UART_Log("DISPLAY", "screen map disabled and map area cleared");
      }
    }
  }
}

void Display_App_SPI_TxCompleteFromISR(SPI_HandleTypeDef *spi)
{
  GC9A01_SPI_TxCompleteFromISR(&display_handle, spi);
}

void Display_App_SPI_ErrorFromISR(SPI_HandleTypeDef *spi)
{
  GC9A01_SPI_ErrorFromISR(&display_handle, spi);
}
