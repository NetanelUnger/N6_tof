#ifndef DISPLAY_APP_H
#define DISPLAY_APP_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32n6xx_hal.h"
#include "tx_api.h"
#include "rps_ai.h"

#include <stddef.h>
#include <stdint.h>

#define DISPLAY_APP_MAP_SOURCE_WIDTH   (54U)
#define DISPLAY_APP_MAP_SOURCE_HEIGHT  (42U)
#define DISPLAY_APP_FRAME_STORAGE_SIZE (4608U)

typedef void (*Display_App_FrameReleaseCallback_t)(void *context);

typedef struct
{
  uint32_t initialized;
  uint32_t map_enabled;
  uint32_t frame_in_flight;
  uint32_t submitted_frames;
  uint32_t rendered_frames;
  uint32_t dropped_frames;
  uint32_t render_errors;
  uint32_t last_submitted_frame;
  uint32_t last_rendered_frame;
  uint32_t last_rendered_rps_frame;
  uint16_t last_rendered_rps_confidence_per_mille;
  uint8_t last_rendered_rps_class_id;
  uint8_t last_rendered_rps_valid;
  uint32_t dma_completions;
  uint32_t dma_errors;
  uint32_t last_render_dma_completions;
  uint32_t clear_operations;
} Display_App_Status_t;

UINT Display_App_Init(void);
void Display_App_Run(void);
void Display_App_SetMapEnabled(uint32_t enabled);
uint32_t Display_App_IsMapEnabled(void);
UINT Display_App_SubmitDepthFrame(
    void *storage, size_t storage_size, const float *depth,
    uint8_t width, uint8_t height, uint32_t frame_number,
    uint16_t minimum_mm, uint16_t maximum_mm,
    const RPS_AI_Status_t *rps_status,
    Display_App_FrameReleaseCallback_t release_callback,
    void *release_context);
void Display_App_GetStatus(Display_App_Status_t *status);
void Display_App_SPI_TxCompleteFromISR(SPI_HandleTypeDef *spi);
void Display_App_SPI_ErrorFromISR(SPI_HandleTypeDef *spi);

#ifdef __cplusplus
}
#endif

#endif /* DISPLAY_APP_H */
