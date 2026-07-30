/**
 ******************************************************************************
 * @file    tof_app.h
 * @brief   VL53L9CX acquisition and USB CDC terminal display.
 ******************************************************************************
 */

#ifndef TOF_APP_H
#define TOF_APP_H

#include <stdint.h>
#include "tx_api.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    TOF_APP_STATE_STARTING = 0,
    TOF_APP_STATE_READY,
    TOF_APP_STATE_PAUSED,
    TOF_APP_STATE_ERROR
} TOF_App_State_t;

typedef struct
{
    TOF_App_State_t state;
    uint32_t map_enabled;
    uint32_t paused;
    uint32_t width;
    uint32_t height;
    uint32_t frame_counter;
    uint32_t fps_x10;
    uint32_t acquired_frames;
    uint32_t processed_frames;
    uint32_t dropped_frames;
    uint32_t minimum_mm;
    uint32_t maximum_mm;
    int error_code;
    const char *error_stage;
} TOF_App_Status_t;

UINT TOF_App_Init(void);
void TOF_App_Acquire(void);
void TOF_App_Process(void);
void TOF_App_SetMapEnabled(uint32_t enabled);
void TOF_App_SetPaused(uint32_t paused);
void TOF_App_GetStatus(TOF_App_Status_t *status);

#ifdef __cplusplus
}
#endif

#endif /* TOF_APP_H */
