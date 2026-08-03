/**
 ******************************************************************************
 * @file    tof_app.c
 * @brief   VL53L9CX full-resolution depth map over USB CDC.
 ******************************************************************************
 *
 * The sensor and transform code are based on STM32CubeExpansion_53L9A1
 * V1.0.0.  The sensor runs autonomously at the requested frame period so its
 * next ranging cycle overlaps CPU transform and terminal rendering.
 */

#include "tof_app.h"

#include <math.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "main.h"
#include "app_console.h"
#include "debug_uart.h"
#include "tx_api.h"
#include "ux_device_cdc_acm.h"
#include "vl53l9.h"
#include "vl53l9_device.h"
#include "vl53l9_interface.h"
#include "vl53l9_transform.h"
#include "vl53l9_utils.h"

#define TOF_DEVICE_ID              (0U)
#define TOF_USECASE                (VL53L9_USECASE_AR_PRECISION)
#define TOF_TARGET_FPS             (10U)
#define TOF_EVENT_TIMEOUT_MS       (1500U)
#define TOF_COMMAND_TIMEOUT_MS     (30U)
#define TOF_MIN_DISPLAY_MM         (200U)
#define TOF_MAX_DISPLAY_MM         (4000U)
#define TOF_TERMINAL_BUFFER_SIZE   (48U * 1024U)
#define TOF_RAW_BUFFER_SIZE        (14842U)
#define TOF_RAW_SLOT_COUNT         (3U)
#define TOF_DEPTH_WIDTH            (54U)
#define TOF_DEPTH_HEIGHT           (42U)
#define TOF_DEPTH_PIXEL_COUNT      (TOF_DEPTH_WIDTH * TOF_DEPTH_HEIGHT)
#define TOF_PIPELINE_READY_FLAG    (1UL << 0)

typedef struct
{
    uint8_t data[TOF_RAW_BUFFER_SIZE];
} TOF_RawSlot_t;

/* The renderer writes directly into a transport-owned static map slot. */
static char *terminal_buffer;
static size_t terminal_capacity;
static TOF_RawSlot_t tof_raw_slots[TOF_RAW_SLOT_COUNT]
                                    __attribute__((aligned(32)));
static float tof_depth_data[TOF_DEPTH_PIXEL_COUNT]
                           __attribute__((aligned(32)));
static uint8_t tof_calibration[VL53L9_CALIB_DATA_SIZE];
static TX_QUEUE tof_free_queue;
static TX_QUEUE tof_ready_queue;
static TX_EVENT_FLAGS_GROUP tof_pipeline_flags;
static ULONG tof_free_queue_storage[TOF_RAW_SLOT_COUNT];
static ULONG tof_ready_queue_storage[TOF_RAW_SLOT_COUNT];
static transform_t *tof_transform;
static uint16_t tof_raw_buffer_size;
static uint8_t tof_depth_width;
static uint8_t tof_depth_height;
static volatile uint32_t tof_pipeline_initialized;
static volatile TOF_App_State_t tof_state = TOF_APP_STATE_STARTING;
static volatile uint32_t tof_map_enabled;
static volatile uint32_t tof_paused;
static volatile uint32_t tof_width;
static volatile uint32_t tof_height;
static volatile uint32_t tof_frame_counter;
static volatile uint32_t tof_fps_x10;
static volatile uint32_t tof_acquired_frames;
static volatile uint32_t tof_processed_frames;
static volatile uint32_t tof_dropped_frames;
static volatile uint32_t tof_queue_failures;
static volatile uint32_t tof_minimum_mm;
static volatile uint32_t tof_maximum_mm;
static volatile int tof_error_code;
static const char *volatile tof_error_stage;

static const uint8_t depth_palette[] = {
    196U, 202U, 208U, 214U, 220U, 226U, 190U, 154U, 118U, 82U, 46U,
    47U, 48U, 49U, 50U, 51U, 45U, 39U, 33U, 27U, 21U,
};

static void tof_fatal(const char *stage, int error);
static void tof_log(const char *format, ...);
static int tof_configure_transform(transform_t *transform,
                                   const uint8_t *calibration,
                                   uint32_t raw_width,
                                   uint8_t depth_width,
                                   uint8_t depth_height);
static void tof_render_frame(const float *depth, uint8_t width, uint8_t height,
                             uint32_t frame_counter, uint32_t elapsed_ms);
static size_t append_text(size_t pos, const char *text);
static size_t append_u32(size_t pos, uint32_t value);
static uint8_t depth_to_color(float distance_mm);
static void tof_release_raw_slot(ULONG slot_index);
static void tof_log_queue_failure(const char *operation, UINT status,
                                  ULONG slot_index);
static int tof_wait_i3c_event(platform_event_t event);
static void tof_log_platform_failure(platform_event_t event, int result);
static int tof_wait_command_complete(vl53l9_device_t *sensor,
                                     uint32_t timeout_ms);
static int tof_start_command_and_wait(vl53l9_device_t *sensor,
                                      int (*start)(void *const),
                                      uint32_t timeout_ms);

UINT TOF_App_Init(void)
{
    ULONG slot_index;

    if (tof_pipeline_initialized != 0U)
    {
        return TX_SUCCESS;
    }

    if (platform_event_init() != 0)
    {
        return TX_GROUP_ERROR;
    }

    if ((tx_queue_create(&tof_free_queue, "ToF free raw slots", TX_1_ULONG,
                         tof_free_queue_storage,
                         sizeof(tof_free_queue_storage)) != TX_SUCCESS) ||
        (tx_queue_create(&tof_ready_queue, "ToF ready raw slots", TX_1_ULONG,
                         tof_ready_queue_storage,
                         sizeof(tof_ready_queue_storage)) != TX_SUCCESS))
    {
        return TX_QUEUE_ERROR;
    }
    if (tx_event_flags_create(&tof_pipeline_flags,
                              "ToF pipeline state") != TX_SUCCESS)
    {
        return TX_GROUP_ERROR;
    }

    for (slot_index = 0U; slot_index < TOF_RAW_SLOT_COUNT; ++slot_index)
    {
        if (tx_queue_send(&tof_free_queue, &slot_index,
                          TX_NO_WAIT) != TX_SUCCESS)
        {
            return TX_QUEUE_ERROR;
        }
    }

    tof_pipeline_initialized = 1U;
    return TX_SUCCESS;
}

void TOF_App_Acquire(void)
{
    int ret;
    ULONG slot_index;
    uint32_t first_frame_diagnostic = 1U;
    vl53l9_device_t *sensor = &device[TOF_DEVICE_ID];
    vl53l9_profile_t profile = g_ranging_profiles[TOF_USECASE];

    tof_state = TOF_APP_STATE_STARTING;
    Debug_UART_Log("TOF", "VL53L9CX acquisition task: initialization started");

    /* Let USBX finish its first scheduling pass before lengthy sensor setup. */
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 4U);
    tof_log("\r\nVL53L9CX: starting initialization...\r\n");

    tof_transform = vl53l9_transform_create();
    if (tof_transform == NULL)
    {
        tof_fatal("transform create", -1);
    }

    ret = vl53l9_get_raw_buffer_size(profile.binning, &tof_raw_buffer_size);
    if ((ret != 0) || (tof_raw_buffer_size != TOF_RAW_BUFFER_SIZE))
    {
        tof_fatal("raw buffer size", (ret != 0) ? ret : -1);
    }

    ret = vl53l9_utils_get_resolution(profile.binning, &tof_depth_width,
                                      &tof_depth_height);
    if ((ret != 0) || (tof_depth_width != TOF_DEPTH_WIDTH) ||
        (tof_depth_height != TOF_DEPTH_HEIGHT))
    {
        tof_fatal("resolution", (ret != 0) ? ret : -1);
    }
    tof_width = tof_depth_width;
    tof_height = tof_depth_height;

    ret = platform_power_reset(TOF_DEVICE_ID);
    if (ret != 0)
    {
        tof_fatal("XSHUT reset", ret);
    }
    ret = platform_assign_dynamic_address();
    if (ret != 0)
    {
        tof_fatal("I3C dynamic address", ret);
    }
    ret = vl53l9_init(sensor);
    if (ret != 0)
    {
        tof_fatal("sensor init", ret);
    }
    ret = vl53l9_get_calib_data(sensor, tof_calibration);
    if (ret != 0)
    {
        tof_fatal("calibration read", ret);
    }

    profile.frame_period_us = 1000000U / TOF_TARGET_FPS;
    profile.sync = VL53L9_SYNC_AUTONOMOUS;
    ret = vl53l9_utils_set_profile(sensor, &profile);
    if (ret != 0)
    {
        tof_fatal("ranging profile", ret);
    }

    ret = tof_configure_transform(tof_transform, tof_calibration,
                                  TOF_RAW_BUFFER_SIZE,
                                  tof_depth_width, tof_depth_height);
    if (ret != 0)
    {
        tof_fatal("depth transform", ret);
    }

    (void)platform_acknowledge_event(PLATFORM_GPIO_IT_EVT);
    ret = vl53l9_start(sensor);
    if (ret != 0)
    {
        tof_fatal("stream start", ret);
    }

    tof_log("VL53L9CX: ready, %ux%u at up to %u fps.\r\n",
            (unsigned int)tof_depth_width, (unsigned int)tof_depth_height,
            (unsigned int)TOF_TARGET_FPS);
    Debug_UART_Log("TOF", "pipeline ready: 3x14842 raw slots, %ux%u depth, target=%u fps",
                   (unsigned int)tof_depth_width,
                   (unsigned int)tof_depth_height,
                   (unsigned int)TOF_TARGET_FPS);

    tof_state = TOF_APP_STATE_READY;
    UINT pipeline_status = tx_event_flags_set(&tof_pipeline_flags,
                                              TOF_PIPELINE_READY_FLAG, TX_OR);
    if (pipeline_status != TX_SUCCESS)
    {
        Debug_UART_Log("TOF", "ERROR: pipeline-ready event post failed: %u",
                       (unsigned int)pipeline_status);
        tof_fatal("pipeline-ready event post", (int)pipeline_status);
    }

    for (;;)
    {
        while (tof_paused != 0U)
        {
            ret = vl53l9_stop(sensor);
            if (ret != 0)
            {
                tof_fatal("stream pause", ret);
            }
            tof_state = TOF_APP_STATE_PAUSED;
            while (tof_paused != 0U)
            {
                tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 20U);
            }
            (void)platform_acknowledge_event(PLATFORM_GPIO_IT_EVT);
            ret = vl53l9_start(sensor);
            if (ret != 0)
            {
                tof_fatal("stream resume", ret);
            }
        }
        tof_state = TOF_APP_STATE_READY;

        if (first_frame_diagnostic != 0U)
        {
            Debug_UART_Log("TOF", "frame 1: acquisition waiting for sensor event");
        }
        (void)platform_acknowledge_event(PLATFORM_GPIO_IT_EVT);
        ret = platform_wait_for_event(PLATFORM_GPIO_IT_EVT,
                                      TOF_EVENT_TIMEOUT_MS);
        if (ret != 0)
        {
            tof_log_platform_failure(PLATFORM_GPIO_IT_EVT, ret);
            tof_fatal("sensor interrupt timeout", ret);
        }
        (void)platform_acknowledge_event(PLATFORM_GPIO_IT_EVT);

        if (tx_queue_receive(&tof_free_queue, &slot_index,
                             TX_NO_WAIT) != TX_SUCCESS)
        {
            /* Keep live-display latency bounded: evict the oldest frame that
             * has not yet been claimed by the processing task. */
            if (tx_queue_receive(&tof_ready_queue, &slot_index,
                                 TX_NO_WAIT) != TX_SUCCESS)
            {
                ++tof_dropped_frames;
                tof_log_queue_failure("no free or evictable raw slot",
                                      TX_QUEUE_EMPTY, UINT32_MAX);
                continue;
            }
            ++tof_dropped_frames;
        }

        if (first_frame_diagnostic != 0U)
        {
            Debug_UART_Log("TOF", "frame 1: sensor event; DMA into raw slot %lu",
                           (unsigned long)slot_index);
        }
        (void)platform_acknowledge_event(PLATFORM_I3C_DMA_RX_EVT);
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        ret = vl53l9_frame_main_read_start_async(
            sensor, tof_raw_slots[slot_index].data, tof_raw_buffer_size);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("frame main DMA start", ret);
        }
        ret = tof_wait_i3c_event(PLATFORM_I3C_DMA_RX_EVT);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("frame main DMA completion", ret);
        }

        ret = tof_start_command_and_wait(sensor,
                                         vl53l9_frame_dss_map_start_async,
                                         TOF_COMMAND_TIMEOUT_MS);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("DSS map command", ret);
        }

        (void)platform_acknowledge_event(PLATFORM_I3C_DMA_RX_EVT);
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        ret = vl53l9_frame_dss_read_start_async(
            sensor, tof_raw_slots[slot_index].data, tof_raw_buffer_size);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("DSS DMA start", ret);
        }
        ret = tof_wait_i3c_event(PLATFORM_I3C_DMA_RX_EVT);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("DSS DMA completion", ret);
        }

        ret = tof_start_command_and_wait(sensor,
                                         vl53l9_frame_dss_unmap_start_async,
                                         TOF_COMMAND_TIMEOUT_MS);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("DSS unmap command", ret);
        }

        (void)platform_acknowledge_event(PLATFORM_I3C_DMA_RX_EVT);
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        ret = vl53l9_frame_status_read_start_async(
            sensor, tof_raw_slots[slot_index].data, tof_raw_buffer_size);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("status DMA start", ret);
        }
        ret = tof_wait_i3c_event(PLATFORM_I3C_DMA_RX_EVT);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("status DMA completion", ret);
        }

        ret = tof_start_command_and_wait(sensor,
                                         vl53l9_frame_ack_start_async,
                                         TOF_COMMAND_TIMEOUT_MS);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("frame acknowledge command", ret);
        }

        ++tof_acquired_frames;
        UINT queue_status = tx_queue_send(&tof_ready_queue, &slot_index,
                                          TX_NO_WAIT);
        if (queue_status != TX_SUCCESS)
        {
            ++tof_dropped_frames;
            tof_log_queue_failure("publish ready raw slot", queue_status,
                                  slot_index);
            tof_release_raw_slot(slot_index);
        }
        if (first_frame_diagnostic != 0U)
        {
            Debug_UART_Log("TOF", "frame 1: acquisition published raw slot %lu",
                           (unsigned long)slot_index);
            first_frame_diagnostic = 0U;
        }
    }
}

void TOF_App_Process(void)
{
    ULONG actual_flags;
    ULONG slot_index;
    uint32_t previous_tick;
    uint32_t first_frame_diagnostic = 1U;

    Debug_UART_Log("TOF", "processing task waiting for sensor pipeline");
    UINT pipeline_status = tx_event_flags_get(
        &tof_pipeline_flags, TOF_PIPELINE_READY_FLAG,
        TX_AND, &actual_flags, TX_WAIT_FOREVER);
    if (pipeline_status != TX_SUCCESS)
    {
        Debug_UART_Log("TOF", "ERROR: pipeline-ready wait failed: %u",
                       (unsigned int)pipeline_status);
        tof_fatal("pipeline-ready event wait", (int)pipeline_status);
    }
    previous_tick = HAL_GetTick();

    for (;;)
    {
        int ret;
        size_t depth_buffer_size = sizeof(tof_depth_data);

        UINT queue_status = tx_queue_receive(&tof_ready_queue, &slot_index,
                                             TX_WAIT_FOREVER);
        if (queue_status != TX_SUCCESS)
        {
            tof_log_queue_failure("receive ready raw slot", queue_status,
                                  UINT32_MAX);
            tof_fatal("processing ready queue receive", (int)queue_status);
        }

        memory_t raw_memory = {
            .data = tof_raw_slots[slot_index].data,
            .offset = 0U,
            .size = tof_raw_buffer_size,
            .maxsize = tof_raw_buffer_size,
            .flags = MEM_FLAG_NONE,
        };
        memory_t depth_memory = {
            .data = (uint8_t *)tof_depth_data,
            .offset = 0U,
            .size = depth_buffer_size,
            .maxsize = depth_buffer_size,
            .flags = MEM_FLAG_NONE,
        };
        memories_t raw_memories = {
            .items = &raw_memory,
            .size = 1U,
            .capacity = 1U,
            .item_size = sizeof(memory_t),
        };
        memories_t depth_memories = {
            .items = &depth_memory,
            .size = 1U,
            .capacity = 1U,
            .item_size = sizeof(memory_t),
        };
        stream_buffer_t stream_items[2] = {
            { .name = "raw", .buffer = { .memories = &raw_memories, .nb = 1U } },
            { .name = "depth", .buffer = { .memories = &depth_memories, .nb = 1U } },
        };
        stream_buffers_t stream_buffers = {
            .items = stream_items,
            .size = 2U,
            .capacity = 2U,
            .item_size = sizeof(stream_buffer_t),
        };

        if (first_frame_diagnostic != 0U)
        {
            Debug_UART_Log("TOF", "frame 1: processing raw slot %lu",
                           (unsigned long)slot_index);
        }
        ret = transform_process_stream(tof_transform, &stream_buffers);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("frame transform", ret);
        }

        vl53l9_frame_t frame = { 0 };
        ret = vl53l9_utils_parse_frame(tof_raw_slots[slot_index].data,
                                       tof_raw_buffer_size, &frame);
        if (ret != 0)
        {
            tof_release_raw_slot(slot_index);
            tof_fatal("frame parse", ret);
        }

        uint32_t now = HAL_GetTick();
        uint32_t elapsed_ms = now - previous_tick;
        previous_tick = now;
        tof_render_frame(tof_depth_data, tof_depth_width, tof_depth_height,
                         frame.p_metadata->frame_counter, elapsed_ms);

        ++tof_processed_frames;
        tof_release_raw_slot(slot_index);
        if (first_frame_diagnostic != 0U)
        {
            Debug_UART_Log("TOF", "frame 1: transform/render complete; raw slot released");
            first_frame_diagnostic = 0U;
        }
        if ((tof_processed_frames % 10U) == 0U)
        {
            Debug_UART_Log("TOF", "alive: acquired=%lu processed=%lu dropped=%lu sensor-frame=%lu",
                           (unsigned long)tof_acquired_frames,
                           (unsigned long)tof_processed_frames,
                           (unsigned long)tof_dropped_frames,
                           (unsigned long)tof_frame_counter);
        }
    }
}

void TOF_App_SetMapEnabled(uint32_t enabled)
{
    tof_map_enabled = (enabled != 0U) ? 1U : 0U;
}

void TOF_App_SetPaused(uint32_t paused)
{
    tof_paused = (paused != 0U) ? 1U : 0U;
}

void TOF_App_GetStatus(TOF_App_Status_t *status)
{
    if (status == NULL)
    {
        return;
    }

    status->state = tof_state;
    status->map_enabled = tof_map_enabled;
    status->paused = tof_paused;
    status->width = tof_width;
    status->height = tof_height;
    status->frame_counter = tof_frame_counter;
    status->fps_x10 = tof_fps_x10;
    status->acquired_frames = tof_acquired_frames;
    status->processed_frames = tof_processed_frames;
    status->dropped_frames = tof_dropped_frames;
    status->queue_failures = tof_queue_failures;
    status->minimum_mm = tof_minimum_mm;
    status->maximum_mm = tof_maximum_mm;
    status->error_code = tof_error_code;
    status->error_stage = tof_error_stage;
}

static void tof_release_raw_slot(ULONG slot_index)
{
    if (slot_index < TOF_RAW_SLOT_COUNT)
    {
        UINT status = tx_queue_send(&tof_free_queue, &slot_index, TX_NO_WAIT);
        if (status != TX_SUCCESS)
        {
            tof_log_queue_failure("release raw slot", status, slot_index);
        }
    }
}

static void tof_log_queue_failure(const char *operation, UINT status,
                                  ULONG slot_index)
{
    uint32_t count = ++tof_queue_failures;

    /* Log the first failure and powers of two thereafter. This retains
     * evidence of a persistent invariant violation without turning COM6
     * logging into another real-time failure source. */
    if ((count == 1U) || ((count & (count - 1U)) == 0U))
    {
        Debug_UART_Log("TOF",
                       "ERROR: queue operation '%s' failed: status=%u slot=%lu count=%lu",
                       operation, (unsigned int)status,
                       (unsigned long)slot_index, (unsigned long)count);
    }
}

static int tof_wait_i3c_event(platform_event_t event)
{
    int ret = platform_wait_for_event(event, TOF_EVENT_TIMEOUT_MS);
    (void)platform_acknowledge_event(event);
    if (ret != 0)
    {
        tof_log_platform_failure(event, ret);
    }
    return ret;
}

static void tof_log_platform_failure(platform_event_t event, int result)
{
    platform_diagnostics_t diagnostics;

    platform_get_diagnostics(&diagnostics);
    Debug_UART_Log(
        "I3C",
        "event wait failed: event=0x%02lX result=%d IRQ=%lu RX=%lu TX=%lu errors=%lu start-fail=%lu(stage=%lu HAL=%lu) event(post=%lu wait=%lu clear=%lu last-status=%lu) last(tick=%lu code=0x%08lX state=0x%02lX EVR=0x%08lX CR-DMA=0x%02lX RX-DMA=0x%02lX TX-DMA=0x%02lX)",
        (unsigned long)event, result,
        (unsigned long)diagnostics.gpio_interrupt_count,
        (unsigned long)diagnostics.i3c_rx_completion_count,
        (unsigned long)diagnostics.i3c_tx_completion_count,
        (unsigned long)diagnostics.i3c_error_count,
        (unsigned long)diagnostics.i3c_start_failure_count,
        (unsigned long)diagnostics.last_start_stage,
        (unsigned long)diagnostics.last_start_hal_status,
        (unsigned long)diagnostics.event_post_failures,
        (unsigned long)diagnostics.event_wait_failures,
        (unsigned long)diagnostics.event_clear_failures,
        (unsigned long)diagnostics.last_event_status,
        (unsigned long)diagnostics.last_error_tick,
        (unsigned long)diagnostics.last_error_code,
        (unsigned long)diagnostics.last_i3c_state,
        (unsigned long)diagnostics.last_evr,
        (unsigned long)diagnostics.last_control_dma_state,
        (unsigned long)diagnostics.last_rx_dma_state,
        (unsigned long)diagnostics.last_tx_dma_state);
}

static int tof_wait_command_complete(vl53l9_device_t *sensor,
                                     uint32_t timeout_ms)
{
    uint32_t started_at = HAL_GetTick();
    uint8_t command_status = UINT8_MAX;

    do
    {
        int ret;

        (void)platform_acknowledge_event(PLATFORM_I3C_DMA_RX_EVT);
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        ret = vl53l9_frame_command_status_start_async(sensor,
                                                       &command_status);
        if (ret != 0)
        {
            return ret;
        }
        ret = tof_wait_i3c_event(PLATFORM_I3C_DMA_RX_EVT);
        if (ret != 0)
        {
            return ret;
        }
        if (command_status == 0U)
        {
            return VL53L9_ERROR_NONE;
        }

        tx_thread_sleep(1U);
    } while ((uint32_t)(HAL_GetTick() - started_at) < timeout_ms);

    return VL53L9_ERROR_TIMEOUT;
}

static int tof_start_command_and_wait(vl53l9_device_t *sensor,
                                      int (*start)(void *const),
                                      uint32_t timeout_ms)
{
    int ret;

    (void)platform_acknowledge_event(PLATFORM_I3C_DMA_TX_EVT);
    (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
    ret = start(sensor);
    if (ret != 0)
    {
        return ret;
    }
    ret = tof_wait_i3c_event(PLATFORM_I3C_DMA_TX_EVT);
    if (ret != 0)
    {
        return ret;
    }
    return tof_wait_command_complete(sensor, timeout_ms);
}

static int tof_configure_transform(transform_t *transform,
                                   const uint8_t *calibration,
                                   uint32_t raw_width,
                                   uint8_t depth_width,
                                   uint8_t depth_height)
{
    int ret = transform_initialize(transform);
    if (ret != 0)
    {
        return ret;
    }

    property_t raw_format = { "format", { .val.v_string = "3DMD", .tid = VTID_STRING } };
    property_t raw_width_property = { "width", { .val.v_uint32 = raw_width, .tid = VTID_UINT32 } };
    property_t raw_height_property = { "height", { .val.v_uint32 = 1U, .tid = VTID_UINT32 } };
    properties_t *raw_properties = properties_new(3U);
    if (raw_properties == NULL)
    {
        return -1;
    }
    (void)properties_add(raw_properties, &raw_format);
    (void)properties_add(raw_properties, &raw_width_property);
    (void)properties_add(raw_properties, &raw_height_property);
    capabilities_t *raw_capabilities = capabilities_new_simple(&raw_properties);
    if (raw_capabilities == NULL)
    {
        properties_free(raw_properties, NULL);
        return -1;
    }

    property_t depth_format = { "format", { .val.v_string = "ZF32", .tid = VTID_STRING } };
    property_t depth_width_property = { "width", { .val.v_uint32 = depth_width, .tid = VTID_UINT32 } };
    property_t depth_height_property = { "height", { .val.v_uint32 = depth_height, .tid = VTID_UINT32 } };
    properties_t *depth_properties = properties_new(3U);
    if (depth_properties == NULL)
    {
        capabilities_free(raw_capabilities, NULL);
        properties_free(raw_properties, NULL);
        return -1;
    }
    (void)properties_add(depth_properties, &depth_format);
    (void)properties_add(depth_properties, &depth_width_property);
    (void)properties_add(depth_properties, &depth_height_property);
    capabilities_t *depth_capabilities = capabilities_new_simple(&depth_properties);
    if (depth_capabilities == NULL)
    {
        properties_free(depth_properties, NULL);
        capabilities_free(raw_capabilities, NULL);
        properties_free(raw_properties, NULL);
        return -1;
    }

    ret = transform_set_stream_capabilities(transform, "raw", raw_capabilities);
    if (ret == 0)
    {
        ret = transform_set_stream_capabilities(transform, "depth", depth_capabilities);
    }

    properties_free(raw_properties, NULL);
    properties_free(depth_properties, NULL);
    capabilities_free(raw_capabilities, NULL);
    capabilities_free(depth_capabilities, NULL);
    if (ret != 0)
    {
        return ret;
    }

    ret = transform_set_control(transform, "calib-buffer",
                                (value_t){ .val.v_ptr = (void *)calibration,
                                           .tid = VTID_POINTER });
    if (ret != 0)
    {
        return ret;
    }

    return transform_prepare(transform);
}

static void tof_render_frame(const float *depth, uint8_t width, uint8_t height,
                             uint32_t frame_counter, uint32_t elapsed_ms)
{
    uint32_t valid_min = UINT32_MAX;
    uint32_t valid_max = 0U;
    uint32_t valid_count = 0U;
    size_t pixel_count = (size_t)width * (size_t)height;
    for (size_t i = 0U; i < pixel_count; ++i)
    {
        if (isfinite(depth[i]) && (depth[i] > 0.0f))
        {
            uint32_t distance = (uint32_t)depth[i];
            if (distance < valid_min)
            {
                valid_min = distance;
            }
            if (distance > valid_max)
            {
                valid_max = distance;
            }
            ++valid_count;
        }
    }
    if (valid_count == 0U)
    {
        valid_min = 0U;
    }

    uint32_t fps_x10 = (elapsed_ms == 0U) ? 0U : (10000U / elapsed_ms);
    tof_frame_counter = frame_counter;
    tof_fps_x10 = fps_x10;
    tof_minimum_mm = valid_min;
    tof_maximum_mm = valid_max;

    if ((tof_map_enabled == 0U) || (App_Console_IsReady() == UX_FALSE))
    {
        return;
    }

    App_Console_FrameBuffer_t output = { 0 };
    if (App_Console_AcquireFrameBuffer(&output) != TX_SUCCESS)
    {
        return;
    }
    terminal_buffer = output.data;
    terminal_capacity = (size_t)output.capacity;

    size_t pos = 0U;
    pos = append_text(pos, "\033[?25l\033[HVL53L9CX  ");
    pos = append_u32(pos, width);
    pos = append_text(pos, "x");
    pos = append_u32(pos, height);
    pos = append_text(pos, "  frame ");
    pos = append_u32(pos, frame_counter);
    pos = append_text(pos, "  ");
    pos = append_u32(pos, fps_x10 / 10U);
    pos = append_text(pos, ".");
    pos = append_u32(pos, fps_x10 % 10U);
    pos = append_text(pos, " fps  measured ");
    pos = append_u32(pos, valid_min);
    pos = append_text(pos, "..");
    pos = append_u32(pos, valid_max);
    pos = append_text(pos, " mm\033[K\r\n");

    pos = append_text(pos, "near ");
    for (size_t i = 0U; i < sizeof(depth_palette); ++i)
    {
        pos = append_text(pos, "\033[48;5;");
        pos = append_u32(pos, depth_palette[i]);
        pos = append_text(pos, "m  ");
    }
    pos = append_text(pos, "\033[0m far   display scale ");
    pos = append_u32(pos, TOF_MIN_DISPLAY_MM);
    pos = append_text(pos, "..");
    pos = append_u32(pos, TOF_MAX_DISPLAY_MM);
    pos = append_text(pos, " mm\033[K\r\n");

    for (uint32_t y = 0U; y < height; ++y)
    {
        uint8_t previous_color = UINT8_MAX;
        for (uint32_t x = 0U; x < width; ++x)
        {
            uint8_t color = depth_to_color(depth[((size_t)y * width) + x]);
            if (color != previous_color)
            {
                pos = append_text(pos, "\033[48;5;");
                pos = append_u32(pos, color);
                pos = append_text(pos, "m");
                previous_color = color;
            }
            pos = append_text(pos, "  ");
        }
        pos = append_text(pos, "\033[0m\033[K\r\n");
    }

    pos = append_text(pos, "Close = red, far = blue, invalid = black. Press Enter to return to MENU.\033[K");
    if (pos < terminal_capacity)
    {
        (void)App_Console_CommitFrameBuffer(&output, (ULONG)pos);
    }
    else
    {
        App_Console_CancelFrameBuffer(&output);
    }
    terminal_buffer = NULL;
    terminal_capacity = 0U;
}

static uint8_t depth_to_color(float distance_mm)
{
    if (!isfinite(distance_mm) || (distance_mm <= 0.0f))
    {
        return 16U;
    }

    if (distance_mm <= (float)TOF_MIN_DISPLAY_MM)
    {
        return depth_palette[0];
    }
    if (distance_mm >= (float)TOF_MAX_DISPLAY_MM)
    {
        return depth_palette[sizeof(depth_palette) - 1U];
    }

    float normalized = (distance_mm - (float)TOF_MIN_DISPLAY_MM) /
                       (float)(TOF_MAX_DISPLAY_MM - TOF_MIN_DISPLAY_MM);
    size_t index = (size_t)(normalized * (float)(sizeof(depth_palette) - 1U));
    return depth_palette[index];
}

static size_t append_text(size_t pos, const char *text)
{
    while ((*text != '\0') && (pos < terminal_capacity))
    {
        terminal_buffer[pos++] = *text++;
    }
    return pos;
}

static size_t append_u32(size_t pos, uint32_t value)
{
    char digits[10];
    size_t count = 0U;

    do
    {
        digits[count++] = (char)('0' + (value % 10U));
        value /= 10U;
    } while ((value != 0U) && (count < sizeof(digits)));

    while ((count > 0U) && (pos < terminal_capacity))
    {
        terminal_buffer[pos++] = digits[--count];
    }
    return pos;
}

static void tof_log(const char *format, ...)
{
    char message[192];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(message, sizeof(message), format, args);
    va_end(args);

    if (length > 0)
    {
        ULONG send_length = (ULONG)length;
        if (send_length >= sizeof(message))
        {
            send_length = sizeof(message) - 1U;
        }
        (void)Debug_UART_Write(message, (size_t)send_length);
    }
}

static void tof_fatal(const char *stage, int error)
{
    tof_error_stage = stage;
    tof_error_code = error;
    tof_state = TOF_APP_STATE_ERROR;
    Debug_UART_Log("TOF", "FATAL at '%s', error=%d", stage, error);

    for (;;)
    {
        if ((error == -14) && (strcmp(stage, "frame transform") == 0))
        {
            tof_log("\r\nVL53L9CX ERROR: %s (code %d). "
                    "Transform memory/resource failure; sensor communication already succeeded.\r\n",
                    stage, error);
        }
        else
        {
            tof_log("\r\nVL53L9CX ERROR: %s (code %d). "
                    "See the COM6 diagnostic log before changing hardware.\r\n",
                    stage, error);
        }
        tx_thread_sleep(2U * TX_TIMER_TICKS_PER_SECOND);
    }
}
