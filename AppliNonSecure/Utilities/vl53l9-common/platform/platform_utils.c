/**
 ******************************************************************************
 * @file    platform_utils.c
 * @author  IMD Software Team
 ******************************************************************************
 * @attention
 *
 * Copyright (c) 2026 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */

#include "main.h"
#include "stm32n6xx_hal.h"
#include "stm32n6xx_hal_i3c.h"
#include "tx_api.h"
#include "vl53l9_device.h"
#include "vl53l9_interface.h"
#include <stdint.h>
#include <string.h>

// when updating use semantic versioning (https://semver.org/)
#define FW_MAJOR (1)
#define FW_MINOR (0)
#define FW_PATCH (0)

/* global variables */

extern I3C_HandleTypeDef hi3c1;

platform_gpio_t g_debug_gpio_1 = { 0 };
platform_gpio_t g_debug_gpio_2 = { 0 };

static volatile platform_event_t g_platform_evt;
static TX_EVENT_FLAGS_GROUP g_platform_event_flags;
static volatile uint32_t g_platform_event_ready;
static platform_diagnostics_t g_platform_diagnostics;

/* private functions */
static void platform_post_event_from_callback(platform_event_t event);

/* exported functions */

/**
 * @brief get firmware version
 * @param version structure filled with version details
 * @return 0 if success
 */
int platform_get_version(platform_version_t *version) {

    version->interface = (_version_t){ .major = INTERFACE_MAJOR, .minor = INTERFACE_MINOR, .patch = INTERFACE_PATCH };
    version->firmware = (_version_t){ .major = FW_MAJOR, .minor = FW_MINOR, .patch = FW_PATCH };
    version->driver =
        (_version_t){ .major = VL53L9_CORE_MAJOR, .minor = VL53L9_CORE_MINOR, .patch = VL53L9_CORE_PATCH };

    strncpy(version->board_name, "nucleo-n657", BOARD_NAME_STR_SIZE);

    return 0;
}

/* device power management */

/**
 * @brief Reset a device
 * @param[in] id Device identifier
 * @return 0 in case of success, negative value otherwise
 */
int platform_power_reset(uint8_t id) {
    HAL_GPIO_WritePin((GPIO_TypeDef *)device[id].xshut.port, device[id].xshut.pin, GPIO_PIN_RESET);
    HAL_Delay(50);
    HAL_GPIO_WritePin((GPIO_TypeDef *)device[id].xshut.port, device[id].xshut.pin, GPIO_PIN_SET);
    HAL_Delay(50);
    return 0;
}

/**
 * @brief Power-up a device
 * @param[in] id Device identifier
 * @return 0 in case of success, negative value otherwise
 */
int platform_power_enable(uint8_t id) {
    HAL_GPIO_WritePin((GPIO_TypeDef *)device[id].xshut.port, device[id].xshut.pin, GPIO_PIN_SET);
    HAL_Delay(50);
    return 0;
}

/**
 * @brief Power-down a device
 * @param[in] id Device identifier
 * @return 0 in case of success, negative value otherwise
 */
int platform_power_disable(uint8_t id) {
    HAL_GPIO_WritePin((GPIO_TypeDef *)device[id].xshut.port, device[id].xshut.pin, GPIO_PIN_RESET);
    HAL_Delay(50);
    return 0;
}

/* i2c/i3c interfaces */

/**
 * @brief Update the I2C static address stored in the device descriptor
 *
 * This method is meant to be called after requesting the device to change its I2C static address.
 * In order to finalize the change on the platform and ensure coherency, the address must be updated in the device
 * descriptor as well.
 *
 * @param[in] id Instance identifier of the device
 * @param[in] address New address to be used (7-bit format)
 * @return 0 in case of success, negative value otherwise
 */
int platform_set_device_address(uint8_t id, uint8_t address) {
    if (device[id].bus_type == PLATFORM_BUS_I2C) {
        device[id].address = address & 0x7F;
        return 0;
    } else {
        return -1;
    }
}

int platform_assign_dynamic_address() {

    HAL_StatusTypeDef status;
    uint64_t payload;

    // set i3c bus frequency to 1 MHz before dynamic address assignment
    hi3c1.Init.CtrlBusCharacteristic.SCLPPLowDuration = 0x7c;
    hi3c1.Init.CtrlBusCharacteristic.SCLI3CHighDuration = 0x7c;
    hi3c1.Init.CtrlBusCharacteristic.SCLODLowDuration = 0x7c;
    if (HAL_I3C_Init(&hi3c1) != HAL_OK) {
        return -1;
    }

    // NOTE: for the moment apply static address as dynamic address
    do {
        status = HAL_I3C_Ctrl_DynAddrAssign(&hi3c1, &payload, I3C_RSTDAA_THEN_ENTDAA, 5000);
        if (status == HAL_BUSY) {
            HAL_I3C_Ctrl_SetDynAddr(&hi3c1, 0x52 & 0x7F);
        }
    } while (status == HAL_BUSY);

    // Restore the 12 MHz timings generated for the STM32N657 I3C kernel clock.
    hi3c1.Init.CtrlBusCharacteristic.SCLPPLowDuration = 0x07;
    hi3c1.Init.CtrlBusCharacteristic.SCLI3CHighDuration = 0x07;
    hi3c1.Init.CtrlBusCharacteristic.SCLODLowDuration = 0x47;
    if (HAL_I3C_Init(&hi3c1) != HAL_OK) {
        return -1;
    }

    // required to register ibi notifications
    I3C_DeviceConfTypeDef DeviceConf;
    DeviceConf.DeviceIndex = 1;
    DeviceConf.TargetDynamicAddr = 0x52 & 0x7F;
    DeviceConf.IBIAck = __HAL_I3C_GET_IBI_CAPABLE(__HAL_I3C_GET_BCR(payload));
    DeviceConf.IBIPayload = __HAL_I3C_GET_IBI_PAYLOAD(__HAL_I3C_GET_BCR(payload));
    DeviceConf.CtrlRoleReqAck = __HAL_I3C_GET_CR_CAPABLE(__HAL_I3C_GET_BCR(payload));
    DeviceConf.CtrlStopTransfer = DISABLE;

    if (HAL_I3C_Ctrl_ConfigBusDevices(&hi3c1, &DeviceConf, 1U) != HAL_OK) {
        Error_Handler();
    }

    return 0;
}

int platform_assign_dynamic_address_multisensor() {

    HAL_StatusTypeDef status;
    uint64_t payload;
    I3C_ENTDAAPayloadTypeDef payload_info;
    uint8_t address = VL53L9_DEFAULT_ADDRESS;

    // set i3c bus frequency to 1 MHz before dynamic address assignment
    hi3c1.Init.CtrlBusCharacteristic.SCLPPLowDuration = 0x7c;
    hi3c1.Init.CtrlBusCharacteristic.SCLI3CHighDuration = 0x7c;
    hi3c1.Init.CtrlBusCharacteristic.SCLODLowDuration = 0x7c;
    if (HAL_I3C_Init(&hi3c1) != HAL_OK) {
        return -1;
    }

    // NOTE: for the moment apply static address as dynamic address
    do {
        payload = 0;
        status = HAL_I3C_Ctrl_DynAddrAssign(&hi3c1, &payload, I3C_RSTDAA_THEN_ENTDAA, 5000);
        if (status == HAL_BUSY) {
            HAL_I3C_Get_ENTDAA_Payload_Info(&hi3c1, payload, &payload_info);

            for (int i = 0; i < NB_DEVICES; i++) {
                if (device[i].instance_id == payload_info.PID.MIPIID) {
                    address = device[i].address;
                    break;
                }
            }
            HAL_I3C_Ctrl_SetDynAddr(&hi3c1, address & 0x7F);
        }
    } while (status == HAL_BUSY);

    // Restore the 12 MHz timings generated for the STM32N657 I3C kernel clock.
    hi3c1.Init.CtrlBusCharacteristic.SCLPPLowDuration = 0x07;
    hi3c1.Init.CtrlBusCharacteristic.SCLI3CHighDuration = 0x07;
    hi3c1.Init.CtrlBusCharacteristic.SCLODLowDuration = 0x47;
    if (HAL_I3C_Init(&hi3c1) != HAL_OK) {
        return -1;
    }

    // TODO: add HAL_I3C_Ctrl_ConfigBusDevices call to enable ibi notifications

    return 0;
}

int platform_ctrl_gpio(platform_gpio_t gpio, platform_gpio_state_t state) {
    switch (state) {
    case PLATFORM_GPIO_STATE_RESET:
        HAL_GPIO_WritePin(gpio.port, gpio.pin, GPIO_PIN_RESET);
        break;
    case PLATFORM_GPIO_STATE_SET:
        HAL_GPIO_WritePin(gpio.port, gpio.pin, GPIO_PIN_SET);
        break;
    case PLATFORM_GPIO_STATE_TOGGLE:
        HAL_GPIO_TogglePin(gpio.port, gpio.pin);
        break;
    default:
        return -1;
        break;
    }
    return 0;
}

/* profiling */

int platform_profiler_enable() {
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk; // enable counter
    return 0;
}

int platform_profiler_disable() {
    // TODO: clear CoreDebug_DEMCR_TRCENA_Msk in DEMCR register
    // TODO: disable counter
    return 0;
}

uint32_t platform_profiler_get_timestamp() {
    return DWT->CYCCNT;
}

uint32_t platform_profiler_convert_to_us(uint32_t timestamp) {
    uint32_t tick_per_1us = SystemCoreClock / 1000000;
    return timestamp / tick_per_1us;
}

/* event handling */

int platform_event_init(void) {
    if (g_platform_event_ready != 0U) {
        return 0;
    }
    if (tx_event_flags_create(&g_platform_event_flags,
                              "VL53L9 platform events") != TX_SUCCESS) {
        return -1;
    }
    g_platform_evt = PLATFORM_NONE_EVT;
    memset(&g_platform_diagnostics, 0, sizeof(g_platform_diagnostics));
    g_platform_event_ready = 1U;
    return 0;
}

int platform_enable_event(platform_event_t event) {
    int res = 0;
    switch (event) {
    case PLATFORM_I3C_IBI_EVT:
        g_platform_evt &= ~PLATFORM_I3C_IBI_EVT;
        HAL_I3C_ActivateNotification(&hi3c1, NULL, LL_I3C_IER_IBIIE);
        HAL_NVIC_EnableIRQ(I3C1_EV_IRQn);
        break;
    case PLATFORM_GPIO_IT_EVT:
        g_platform_evt &= ~PLATFORM_GPIO_IT_EVT;
        break;
    default:
        res = -1;
        break;
    }
    return res;
}

int platform_disable_event(platform_event_t event) {
    int res = 0;
    switch (event) {
    case PLATFORM_I3C_IBI_EVT:
        HAL_I3C_DeactivateNotification(&hi3c1, LL_I3C_IER_IBIIE);
        HAL_NVIC_DisableIRQ(I3C1_EV_IRQn);
        g_platform_evt &= ~PLATFORM_I3C_IBI_EVT;
        break;
    case PLATFORM_GPIO_IT_EVT:
        g_platform_evt &= ~PLATFORM_GPIO_IT_EVT;
        break;
    default:
        res = -1; // not supported
        break;
    }
    return res;
}

int platform_wait_for_event(platform_event_t event, uint32_t timeout_ms) {
    ULONG requested = (ULONG)event;
    ULONG actual = 0U;
    ULONG wait_ticks;
    UINT status;

    if (g_platform_event_ready == 0U) {
        return -1;
    }

    /* The sensor interrupt is level-active-low.  Checking the level before
     * sleeping closes the race where the falling edge arrived immediately
     * before the task acknowledged an older event bit. */
    if (event == PLATFORM_GPIO_IT_EVT) {
        for (uint8_t i = 0; i < NB_DEVICES; ++i) {
            if (HAL_GPIO_ReadPin((GPIO_TypeDef *)device[i].intr.port,
                                 device[i].intr.pin) == GPIO_PIN_RESET) {
                return 0;
            }
        }
    }

    /* g_platform_evt is a sticky fallback for the rare case where the ISR ran
     * but ThreadX rejected the event-flags post. Callers acknowledge stale
     * bits before starting each transaction, so consuming the sticky bit here
     * cannot complete a newer transfer accidentally. */
    if (((event == PLATFORM_I3C_DMA_RX_EVT) ||
         (event == PLATFORM_I3C_DMA_TX_EVT)) &&
        ((g_platform_evt & PLATFORM_I3C_ERROR_EVT) != 0U)) {
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        return -2;
    }
    if ((g_platform_evt & event) != 0U) {
        return 0;
    }

    if ((event == PLATFORM_I3C_DMA_RX_EVT) ||
        (event == PLATFORM_I3C_DMA_TX_EVT)) {
        requested |= PLATFORM_I3C_ERROR_EVT;
    }

    wait_ticks = (((ULONG)timeout_ms * TX_TIMER_TICKS_PER_SECOND) + 999U) /
                 1000U;
    if (wait_ticks == 0U) {
        wait_ticks = 1U;
    }
    status = tx_event_flags_get(&g_platform_event_flags, requested, TX_OR,
                                &actual, wait_ticks);
    if (status != TX_SUCCESS) {
        ++g_platform_diagnostics.event_wait_failures;
        g_platform_diagnostics.last_event_status = (uint32_t)status;
        return -1;
    }
    if ((actual & PLATFORM_I3C_ERROR_EVT) != 0U) {
        (void)platform_acknowledge_event(PLATFORM_I3C_ERROR_EVT);
        return -2;
    }
    return ((actual & (ULONG)event) != 0U) ? 0 : -1;
}

int platform_acknowledge_event(platform_event_t event) {
    int res = 0;
    UINT status;
    TX_INTERRUPT_SAVE_AREA

    TX_DISABLE
    switch (event) {
    case PLATFORM_GPIO_IT_EVT:
        g_platform_evt &= ~PLATFORM_GPIO_IT_EVT;
        break;
    case PLATFORM_I3C_DMA_RX_EVT:
        g_platform_evt &= ~PLATFORM_I3C_DMA_RX_EVT;
        break;
    case PLATFORM_I3C_IBI_EVT:
        g_platform_evt &= ~PLATFORM_I3C_IBI_EVT;
        break;
    case PLATFORM_I3C_DMA_TX_EVT:
        g_platform_evt &= ~PLATFORM_I3C_DMA_TX_EVT;
        break;
    case PLATFORM_I3C_ERROR_EVT:
        g_platform_evt &= ~PLATFORM_I3C_ERROR_EVT;
        break;
    default:
        res = -1;
        break;
    }
    TX_RESTORE

    if ((res == 0) && (g_platform_event_ready != 0U)) {
        ULONG actual = 0U;
        status = tx_event_flags_get(&g_platform_event_flags, (ULONG)event,
                                    TX_OR_CLEAR, &actual, TX_NO_WAIT);
        /* TX_NO_EVENTS is expected when only the sticky ISR fallback was set.
         * Every other failure indicates an invalid/corrupted ThreadX object. */
        if ((status != TX_SUCCESS) && (status != TX_NO_EVENTS)) {
            ++g_platform_diagnostics.event_clear_failures;
            g_platform_diagnostics.last_event_status = (uint32_t)status;
        }
    }
    return res;
}

int platform_get_event_status(platform_event_t event, bool *active) {
    *active = (g_platform_evt & event) ? true : false;
    return 0;
}

void platform_get_diagnostics(platform_diagnostics_t *diagnostics) {
    if (diagnostics == NULL) {
        return;
    }

    TX_INTERRUPT_SAVE_AREA
    TX_DISABLE
    *diagnostics = g_platform_diagnostics;
    TX_RESTORE
}

void platform_record_i3c_start_failure(platform_i3c_start_stage_t stage,
                                       uint32_t hal_status) {
    TX_INTERRUPT_SAVE_AREA
    TX_DISABLE
    ++g_platform_diagnostics.i3c_start_failure_count;
    g_platform_diagnostics.last_start_stage = (uint32_t)stage;
    g_platform_diagnostics.last_start_hal_status = hal_status;
    g_platform_diagnostics.last_error_tick = HAL_GetTick();
    g_platform_diagnostics.last_error_code = hi3c1.ErrorCode;
    g_platform_diagnostics.last_i3c_state = (uint32_t)hi3c1.State;
    g_platform_diagnostics.last_evr =
        (hi3c1.Instance != NULL) ? hi3c1.Instance->EVR : UINT32_MAX;
    g_platform_diagnostics.last_control_dma_state =
        (hi3c1.hdmacr != NULL) ? (uint32_t)hi3c1.hdmacr->State : UINT32_MAX;
    g_platform_diagnostics.last_rx_dma_state =
        (hi3c1.hdmarx != NULL) ? (uint32_t)hi3c1.hdmarx->State : UINT32_MAX;
    g_platform_diagnostics.last_tx_dma_state =
        (hi3c1.hdmatx != NULL) ? (uint32_t)hi3c1.hdmatx->State : UINT32_MAX;
    TX_RESTORE
}

/* HAL callbacks */

static void platform_post_event_from_callback(platform_event_t event) {
    UINT status = TX_NOT_AVAILABLE;

    g_platform_evt |= event;
    if (g_platform_event_ready != 0U) {
        status = tx_event_flags_set(&g_platform_event_flags,
                                    (ULONG)event, TX_OR);
    }
    if (status != TX_SUCCESS) {
        ++g_platform_diagnostics.event_post_failures;
    }
}

void HAL_I3C_CtrlRxCpltCallback(I3C_HandleTypeDef *hi3c) {
    if (hi3c == &hi3c1) {
        ++g_platform_diagnostics.i3c_rx_completion_count;
        platform_post_event_from_callback(PLATFORM_I3C_DMA_RX_EVT);
    }
}

void HAL_I3C_CtrlMultipleXferCpltCallback(I3C_HandleTypeDef *hi3c) {
    if (hi3c == &hi3c1) {
        /* Register reads are emitted as one DMA multiple-transfer frame:
         * two address bytes, repeated start, then the RX payload. */
        ++g_platform_diagnostics.i3c_rx_completion_count;
        platform_post_event_from_callback(PLATFORM_I3C_DMA_RX_EVT);
    }
}

void HAL_I3C_CtrlTxCpltCallback(I3C_HandleTypeDef *hi3c) {
    if (hi3c == &hi3c1) {
        ++g_platform_diagnostics.i3c_tx_completion_count;
        platform_post_event_from_callback(PLATFORM_I3C_DMA_TX_EVT);
    }
}

void HAL_I3C_ErrorCallback(I3C_HandleTypeDef *hi3c) {
    if (hi3c == &hi3c1) {
        ++g_platform_diagnostics.i3c_error_count;
        g_platform_diagnostics.last_error_tick = HAL_GetTick();
        g_platform_diagnostics.last_error_code = hi3c->ErrorCode;
        g_platform_diagnostics.last_i3c_state = (uint32_t)hi3c->State;
        g_platform_diagnostics.last_evr = hi3c->Instance->EVR;
        g_platform_diagnostics.last_control_dma_state =
            (hi3c->hdmacr != NULL) ? (uint32_t)hi3c->hdmacr->State : UINT32_MAX;
        g_platform_diagnostics.last_rx_dma_state =
            (hi3c->hdmarx != NULL) ? (uint32_t)hi3c->hdmarx->State : UINT32_MAX;
        g_platform_diagnostics.last_tx_dma_state =
            (hi3c->hdmatx != NULL) ? (uint32_t)hi3c->hdmatx->State : UINT32_MAX;
        platform_post_event_from_callback(PLATFORM_I3C_ERROR_EVT);
    }
}

void HAL_I3C_NotifyCallback(I3C_HandleTypeDef *hi3c, uint32_t eventId) {
    if ((hi3c == &hi3c1) && ((eventId & EVENT_ID_IBI) == EVENT_ID_IBI)) {
        platform_post_event_from_callback(PLATFORM_I3C_IBI_EVT);
    }
}

void platform_notify_gpio_interrupt(void) {
    ++g_platform_diagnostics.gpio_interrupt_count;
    platform_post_event_from_callback(PLATFORM_GPIO_IT_EVT);
}

/* csi interface */

int platform_start_csi_pipe(uint8_t *buff_csi) {
    return -1; // not supported
}

int platform_stop_csi_pipe() {
    return -1; // not supported
}
