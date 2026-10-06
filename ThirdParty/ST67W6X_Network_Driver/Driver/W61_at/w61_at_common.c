/**
  ******************************************************************************
  * @file    w61_at_common.c
  * @author  ST67 Application Team
  * @brief   This file provides the common implementations of the AT driver
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2024 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "w61_at_common.h"
#include "w61_at_internal.h"
#include "w61_io.h"
#include <stdlib.h>
#include "modem_cmd_handler.h"
#include "debug_uart.h"
#include "stdio.h"
#if (defined(SYS_DBG_ENABLE_TA4) && (SYS_DBG_ENABLE_TA4 >= 1))
#include "trcRecorder.h"
#endif /* SYS_DBG_ENABLE_TA4 */

/* Global variables ----------------------------------------------------------*/
/* Private typedef -----------------------------------------------------------*/
/* Private defines -----------------------------------------------------------*/
/** @defgroup ST67W61_AT_Common_Defines ST67W61 AT Driver Common Defines
  * @ingroup ST67W61_AT_Common
  * @{
  */

/** Timeout for io send operation */
#define IO_SEND_TIMEOUT                         2000U

/** Timeout for io receive operation */
#define IO_RECEIVE_TIMEOUT                      portMAX_DELAY

#ifndef IO_AT_CMDQ_DEPTH
/** IO queue depth for AT CMD */
#define IO_AT_CMDQ_DEPTH                        16
#endif /* IO_AT_CMDQ_DEPTH */

/** @} */

/* Private macros ------------------------------------------------------------*/
/* Private function prototypes -----------------------------------------------*/
/** @addtogroup ST67W61_AT_Common_Functions
  * @{
  */

/**
  * @brief  Initialize the IO interface
  * @param iface: pointer to the modem interface
  * @return 0 on success, negative value on error
  */
static int32_t io_init(struct modem_iface *iface);

/**
  * @brief  Deinitialize the IO interface
  * @param iface: pointer to the modem interface
  * @return 0 on success, negative value on error
  */
static int32_t io_deinit(struct modem_iface *iface);

/**
  * @brief  Modem process task
  * @param arg: pointer to the task argument
  */
static void W61_Modem_Process_task(void *arg);

/**
  * @brief  Write data to the modem interface
  * @param iface: pointer to the modem interface
  * @param buf: pointer to the data buffer
  * @param size: size of the data to write
  * @return 0 on success, negative value on error
  */
static int32_t modem_iface_spi_write(struct modem_iface *iface,
                                     const uint8_t *buf, size_t size);

/**
  * @brief  Read data from the modem interface
  * @param iface: pointer to the modem interface
  * @param buf: pointer to the buffer to store read data
  * @param size: size of the buffer
  * @param bytes_read: pointer to store the number of bytes read
  * @return 0 on success, negative value on error
  */
static int32_t modem_iface_spi_read(struct modem_iface *iface,
                                    uint8_t *buf, size_t size, size_t *bytes_read);

/**
  * @brief  Callback function to handle query events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings
  * @param  argc: number of argument
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_query);

/**
  * @brief  Callback function to handle "OK" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_ok);

/**
  * @brief  Callback function to handle "ERROR" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_error);

/**
  * @brief  Callback function to handle "ready" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_ready);

/**
  * @brief  Callback function to handle "+CW" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings
  * @param  argc: number of arguments
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_wifi_event);

/**
  * @brief  Callback function to handle "+BLE" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings
  * @param  argc: number of arguments
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_ble_event);

/**
  * @brief  Callback function to handle "+CIP" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_net_event);

/**
  * @brief  Callback function to handle "+MQTT" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings
  * @param  argc: number of arguments
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_mqtt_event);

/**
  * @brief  Callback function to handle ">" events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DIRECT_DECLARE(on_cmd_tx_ready);

/**
  * @brief  Callback function to handle "RECV " events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return 0 on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_recv);

/**
  * @brief  Callback function to handle MQTT data events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DIRECT_DECLARE(on_cmd_mqtt_data_event);

/**
  * @brief  Callback function to handle Net data events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings
  * @param  argc: number of arguments
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_net_data_event);

/**
  * @brief  Callback function to handle BLE Write data events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DIRECT_DECLARE(on_cmd_ble_write_data_event);

/**
  * @brief  Callback function to handle BLE Read data events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DIRECT_DECLARE(on_cmd_ble_read_data_event);

/**
  * @brief  Callback function to handle BLE Notification data events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DIRECT_DECLARE(on_cmd_ble_noti_data_event);

/**
  * @brief  Callback function to handle ping events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_net_ping_event);

/**
  * @brief  Callback function to handle Wi-Fi scan events
  * @param  data: pointer to the modem_cmd_handler_data structure
  * @param  len: length of the data
  * @param  argv: array of argument strings (unused)
  * @param  argc: number of arguments (unused)
  * @return process length on success, negative value on error
 */
MODEM_CMD_DECLARE(on_cmd_wifi_scan_event);

/** @} */

/* Private variables ---------------------------------------------------------*/
/** @defgroup ST67W61_AT_Common_Variables ST67W61 AT Driver Common Variables
  * @ingroup ST67W61_AT_Common
  * @{
  */

/** List of response commands for the modem */
static const struct modem_cmd response_cmds_list[] =
{
  MODEM_CMD("OK", on_cmd_ok, 0U, ""),
  MODEM_CMD("ERROR", on_cmd_error, 0U, ""),
};

/** List of unsolicited commands for the modem */
static const struct modem_cmd unsol_cmds_list[] =
{
  MODEM_CMD("ready", on_cmd_ready, 0U, ""),
  MODEM_CMD("+CWLAP:", on_cmd_wifi_scan_event, 8U, ","),
  MODEM_CMD_DIRECT("+BLE:GATTWRITE:", on_cmd_ble_write_data_event),
  MODEM_CMD_DIRECT("+BLE:GATTREAD:", on_cmd_ble_read_data_event),
  MODEM_CMD_DIRECT("+BLE:NOTIDATA:", on_cmd_ble_noti_data_event),
  MODEM_CMD_DIRECT("+MQTT:SUBRECV:", on_cmd_mqtt_data_event),
  MODEM_CMD_ARGS_MAX("+IPD:", on_cmd_net_data_event, 1U, 10U, ","),
  MODEM_CMD_ARGS_MAX("+CW:", on_cmd_wifi_event, 1U, 10U, ", "),
  MODEM_CMD_ARGS_MAX("+BLE:", on_cmd_ble_event, 1U, 11U, ",:()"),
  MODEM_CMD_ARGS_MAX("+CIP:", on_cmd_net_event, 1U, 10U, ","),
  MODEM_CMD_ARGS_MAX("+MQTT:", on_cmd_mqtt_event, 1U, 10U, ","),
  MODEM_CMD("+PING:", on_cmd_net_ping_event, 1U, ""),
};

/** @} */

/* Functions Definition ------------------------------------------------------*/
/** @addtogroup ST67W61_AT_Common_Functions
  * @{
  */

int32_t W61_AT_ModemInit(W61_Object_t *Obj)
{
  BaseType_t xReturned;
  int32_t ret = -1;
  struct modem *mdm = (struct modem *) &Obj->Modem;

  mdm->spi_rx_pending = NULL;
  mdm->spi_rx_pending_data = NULL;
  mdm->spi_rx_pending_len = 0U;
  mdm->spi_rx_pending_offset = 0U;

  /* Cmd handler */
  const struct modem_cmd_handler_config cmd_handler_config =
  {
    .match_buf = (char *) &mdm->cmd_match_buf[0],
    .match_buf_len = sizeof(mdm->cmd_match_buf),
    .eol = "", /* CRLF sent within the command string to avoid 2 successive write */
    .user_data = mdm,
    .response_cmds = response_cmds_list,
    .response_cmds_len = ARRAY_SIZE(response_cmds_list),
    .unsol_cmds = unsol_cmds_list,
    .unsol_cmds_len = ARRAY_SIZE(unsol_cmds_list),
  };

  mdm->sem_response = xSemaphoreCreateBinary();
  if (mdm->sem_response == NULL)
  {
    goto __err;
  }
  mdm->sem_if_ready = xSemaphoreCreateBinary();
  if (mdm->sem_if_ready == NULL)
  {
    goto __err;
  }
  mdm->sem_tx_ready = xSemaphoreCreateBinary();
  if (mdm->sem_tx_ready == NULL)
  {
    goto __err;
  }

  /* The static modem object lives in application SRAM, not the constrained
   * 64 KiB radio byte pool. Keep one extra sentinel byte for direct parsers. */
  (void)memset(mdm->rx_assembly, 0, sizeof(mdm->rx_assembly));
  mdm->handler_data.rx_buf = mdm->rx_assembly;

  ret = modem_cmd_handler_init(&mdm->handler, &mdm->handler_data,
                               &cmd_handler_config);
  if (ret < 0)
  {
    goto __err;
  }

  ret = io_init(&mdm->iface);
  if (ret < 0)
  {
    goto __err;
  }

  xReturned = xTaskCreate(W61_Modem_Process_task,
                          (char *)"Modem_Process",
                          W61_MDM_RX_TASK_STACK_SIZE_BYTES >> 2U,
                          mdm,
                          W61_MDM_RX_TASK_PRIO,
                          &mdm->modem_task_handle);

  if (xReturned != pdPASS)
  {
    SYS_LOG_ERROR("xTaskCreate failed to create\n");
    ret = -1;
    goto __err;
  }

  /* Wait for the module to be ready */
  if (W61_WaitForReady(Obj, W61_READY_DEFAULT_TIMEOUT_MS) != W61_STATUS_OK)
  {
    SYS_LOG_ERROR("sem_if_ready not received\n");
    ret = -1;
    goto __err;
  }

  (void)W61_AT_Common_SetExecute(Obj, (uint8_t *)"AT\r\n", W61_NCP_TIMEOUT);

  return ret;
__err:
  if (mdm->modem_task_handle != NULL)
  {
    vTaskDelete(mdm->modem_task_handle);
    mdm->modem_task_handle = NULL;
  }
  if (mdm->spi_rx_pending != NULL)
  {
    (void)BusIo_SPI_Free(mdm->spi_rx_pending);
    mdm->spi_rx_pending = NULL;
  }
  mdm->spi_rx_pending_data = NULL;
  mdm->spi_rx_pending_len = 0U;
  mdm->spi_rx_pending_offset = 0U;
  if (mdm->handler_data.rx_buf != NULL)
  {
    (void)memset(mdm->rx_assembly, 0, sizeof(mdm->rx_assembly));
    mdm->handler_data.rx_buf = NULL;
  }
  if (mdm->sem_response != NULL)
  {
    vSemaphoreDelete(mdm->sem_response);
    mdm->sem_response = NULL;
  }
  if (mdm->sem_if_ready != NULL)
  {
    vSemaphoreDelete(mdm->sem_if_ready);
    mdm->sem_if_ready = NULL;
  }
  if (mdm->sem_tx_ready != NULL)
  {
    vSemaphoreDelete(mdm->sem_tx_ready);
    mdm->sem_tx_ready = NULL;
  }
  return ret;
}

void W61_AT_ModemDeInit(W61_Object_t *Obj)
{
  struct modem *mdm = (struct modem *) &Obj->Modem;
  if (mdm->modem_task_handle != NULL)
  {
    vTaskDelete(mdm->modem_task_handle);
    mdm->modem_task_handle = NULL;
  }
  (void)io_deinit(&mdm->iface);
  if (mdm->spi_rx_pending != NULL)
  {
    (void)BusIo_SPI_Free(mdm->spi_rx_pending);
    mdm->spi_rx_pending = NULL;
  }
  mdm->spi_rx_pending_data = NULL;
  mdm->spi_rx_pending_len = 0U;
  mdm->spi_rx_pending_offset = 0U;
  if (mdm->handler_data.rx_buf != NULL)
  {
    (void)memset(mdm->rx_assembly, 0, sizeof(mdm->rx_assembly));
    mdm->handler_data.rx_buf = NULL;
  }
  if (mdm->sem_response != NULL)
  {
    vSemaphoreDelete(mdm->sem_response);
    mdm->sem_response = NULL;
  }
  if (mdm->sem_if_ready != NULL)
  {
    vSemaphoreDelete(mdm->sem_if_ready);
    mdm->sem_if_ready = NULL;
  }
  if (mdm->sem_tx_ready != NULL)
  {
    vSemaphoreDelete(mdm->sem_tx_ready);
    mdm->sem_tx_ready = NULL;
  }
}

W61_Status_t W61_Status(int32_t ret)
{
  W61_Status_t status;

  switch (ret)
  {
    case 0:
      status = W61_STATUS_OK;
      break;
    case -ETIMEDOUT:
      status = W61_STATUS_TIMEOUT;
      break;
    case -EIO:
      status = W61_STATUS_IO_ERROR;
      break;
    default:
      status = W61_STATUS_ERROR;
      break;
  }
  return status;
}

W61_Status_t W61_AT_Common_SetExecute(W61_Object_t *Obj, uint8_t *p_cmd, uint32_t timeout_ms)
{
  struct modem *mdm = &Obj->Modem;
  return W61_Status(modem_cmd_send(&mdm->iface,
                                   &mdm->handler,
                                   NULL,
                                   0,
                                   p_cmd,
                                   mdm->sem_response,
                                   timeout_ms));
}

TickType_t W61_AT_Common_RemainingTxBudget(TickType_t started_at, uint32_t timeout_ms)
{
  TickType_t budget = pdMS_TO_TICKS(timeout_ms);
  TickType_t elapsed = xTaskGetTickCount() - started_at;

  return (elapsed >= budget) ? 0U : (budget - elapsed);
}

TickType_t W61_AT_Common_TakeTxLockBudget(SemaphoreHandle_t lock, uint32_t timeout_ms,
                                          TickType_t *started_at)
{
  TickType_t remaining;

  if ((lock == NULL) || (started_at == NULL))
  {
    return 0U;
  }
  *started_at = xTaskGetTickCount();
  if (xSemaphoreTake(lock, pdMS_TO_TICKS(timeout_ms)) != pdPASS)
  {
    return 0U;
  }
  remaining = W61_AT_Common_RemainingTxBudget(*started_at, timeout_ms);
  if (remaining == 0U)
  {
    (void)xSemaphoreGive(lock);
    return 0U;
  }
  return remaining;
}

W61_Status_t W61_AT_Common_Query_Parse(W61_Object_t *Obj, char *p_cmd, char *p_resp,
                                       uint16_t *argc, char **argv, uint32_t timeout_ms)
{
  struct modem *mdm = (struct modem *) &Obj->Modem;
  struct modem_cmd_handler_data *data = (struct modem_cmd_handler_data *)mdm->handler.cmd_handler_data;
  W61_Status_t ret;
  TickType_t lock_budget = pdMS_TO_TICKS(timeout_ms);
  TickType_t started_at = xTaskGetTickCount();
  TickType_t remaining;

  if (data == NULL)
  {
    return W61_STATUS_ERROR;
  }
  if (xSemaphoreTake(data->sem_tx_lock, lock_budget) != pdPASS)
  {
    return W61_STATUS_TIMEOUT;
  }
  remaining = xTaskGetTickCount() - started_at;
  remaining = (remaining >= lock_budget) ? 0U :
              (lock_budget - remaining);
  if (remaining == 0U)
  {
    (void)xSemaphoreGive(data->sem_tx_lock);
    return W61_STATUS_TIMEOUT;
  }
  /* **argv reference p_cmd to ensure re-entrance */
  mdm->rx_data = p_cmd;
  mdm->argc = argc;
  mdm->argv = argv;

  struct modem_cmd handlers[] = {{
      .cmd = p_resp,
      .cmd_len = (uint16_t)strlen(p_resp),
      .func = on_cmd_query,
      .arg_count_min = 1,
      .arg_count_max = CONFIG_MODEM_CMD_HANDLER_MAX_PARAM_COUNT,
      .delim = ",:",
      .direct = false,
    }
  };

  ret = W61_Status(modem_cmd_send_ext(&mdm->iface,
                                      &mdm->handler,
                                      handlers,
                                      ARRAY_SIZE(handlers),
                                      (const uint8_t *)p_cmd,
                                      mdm->sem_response,
                                      remaining,
                                      MODEM_NO_TX_LOCK));
  (void)xSemaphoreGive(data->sem_tx_lock);
  return ret;
}

W61_Status_t W61_AT_Common_RequestSendData(W61_Object_t *Obj, uint8_t *p_cmd, uint8_t *pdata, uint32_t len,
                                           uint32_t timeout_ms, bool check_resp)
{
  struct modem *mdm = (struct modem *) &Obj->Modem;
  int32_t ret;
  int32_t bytes_consumed_by_the_bus = 0;
  int32_t bytes_to_send;
  bool raw_announced = false;
  TickType_t lock_budget = pdMS_TO_TICKS(timeout_ms);
  TickType_t started_at = xTaskGetTickCount();
  TickType_t elapsed;
  TickType_t remaining;

  static const struct modem_cmd cmds[] =
  {
    MODEM_CMD_DIRECT(">", on_cmd_tx_ready),
    MODEM_CMD("Recv ", on_cmd_recv, 1U, " "),
  };

  if (xSemaphoreTake(mdm->handler_data.sem_tx_lock, lock_budget) != pdPASS)
  {
    return W61_STATUS_TIMEOUT;
  }
  elapsed = xTaskGetTickCount() - started_at;
  if (elapsed >= lock_budget)
  {
    ret = -ETIMEDOUT;
    goto out;
  }
  remaining = lock_budget - elapsed;
  /*reset mdm->sem_tx_read */
  (void)xSemaphoreTake(mdm->sem_tx_ready, 0);

  if (mdm->handler_data.tx_desynchronized)
  {
    ret = -EIO;
    goto out;
  }
  mdm->raw_tx_terminal_only = !check_resp;
  mdm->raw_tx_response_received = false;
  raw_announced = true;

  ret = modem_cmd_send_ext(&mdm->iface, &mdm->handler,
                           cmds, ARRAY_SIZE(cmds), p_cmd, mdm->sem_response,
                           check_resp ? remaining : 0U, /* If check_resp is false don't wait for OK */
                           MODEM_NO_TX_LOCK | MODEM_NO_UNSET_CMDS);
  if (ret < 0)
  {
    SYS_LOG_DEBUG("Failed to send command\n");
    goto out;
  }

  /* Reset semaphore that will be released by "Recv " */
  /*reset mdm->sem_response */
  (void)xSemaphoreTake(mdm->sem_response, 0);
  mdm->raw_tx_response_received = false;

  /* Set rx_data_len to be checked during "Recv " event */
  mdm->rx_data_len = len;

  /* Wait for '>' */
  elapsed = xTaskGetTickCount() - started_at;
  if (elapsed >= lock_budget)
  {
    ret = -ETIMEDOUT;
    goto out;
  }
  remaining = lock_budget - elapsed;
  if (remaining > pdMS_TO_TICKS(5000))
  {
    remaining = pdMS_TO_TICKS(5000);
  }
  if (xSemaphoreTake(mdm->sem_tx_ready, remaining) != pdPASS)
  {
    SYS_LOG_DEBUG("Timeout waiting for tx\n");
    ret = -ETIMEDOUT;
    goto out;
  }

  while (bytes_consumed_by_the_bus < len)
  {
    int32_t bytes_written;

    if ((xTaskGetTickCount() - started_at) >= lock_budget)
    {
      ret = -ETIMEDOUT;
      goto out;
    }

    bytes_to_send = len - bytes_consumed_by_the_bus;
    bytes_written = modem_cmd_send_data_nolock(&mdm->iface,
                                               &pdata[bytes_consumed_by_the_bus],
                                               bytes_to_send);
    if ((bytes_written <= 0) || (bytes_written > bytes_to_send))
    {
      /* A failed/zero-length bus write cannot make forward progress.  Do not
       * spin forever while holding sem_tx_lock: callers need the lock in
       * order to report the transport failure and continue servicing BLE and
       * Wi-Fi control traffic. */
      ret = (bytes_written < 0) ? bytes_written : -EIO;
      goto out;
    }
    bytes_consumed_by_the_bus += bytes_written;
  }

  /* Wait for "Recv " */
  elapsed = xTaskGetTickCount() - started_at;
  if (elapsed >= lock_budget)
  {
    ret = -ETIMEDOUT;
    goto out;
  }
  if (xSemaphoreTake(mdm->sem_response, lock_budget - elapsed) != pdPASS)
  {
    SYS_LOG_DEBUG("No send response\n");
    ret = -ETIMEDOUT;
    goto out;
  }

  ret = modem_cmd_handler_get_error(&mdm->handler_data);
  if (ret != 0)
  {
    SYS_LOG_DEBUG("Failed to send data\n");
  }

out:
  /* Releasing the mutex does not cancel the NCP's raw-data mode. Keep all
   * subsequent command text off the bus if this transaction has no response
   * boundary. Only module restart/reinitialization clears the fence. */
  if (raw_announced && (ret < 0) && !mdm->raw_tx_response_received &&
      !mdm->handler_data.tx_desynchronized)
  {
    mdm->handler_data.tx_desynchronized = true;
    Debug_UART_Log("ST67", "raw TX response missing; AT traffic fenced until module restart");
  }
  mdm->raw_tx_terminal_only = false;
  (void)modem_cmd_handler_update_cmds(&mdm->handler_data,
                                      NULL, 0U, false);
  (void)xSemaphoreGive(mdm->handler_data.sem_tx_lock);

  return W61_Status(ret);
}

void W61_AT_RemoveStrQuotes(char *inbuf)
{
  int32_t len = strlen(inbuf);

  if (len < 2U)
  {
    return; /* Nothing to do */
  }
  inbuf[len - 1U] = '\0'; /* Ensure the last character is null-terminated */
  /* Ensure the first character is not a double quote */
  (void)memmove(inbuf, inbuf + 1, len);
}

void W61_AT_Logger(uint8_t *pBuf, uint32_t len, char *inOut)
{
  char log_message[W61_MAX_AT_LOG_LENGTH];
  uint32_t message_len = W61_MAX_AT_LOG_LENGTH - 1U;
  if (len < (W61_MAX_AT_LOG_LENGTH - 1U))
  {
    message_len = len;
  }
  (void)memcpy(log_message, pBuf, message_len);
  log_message[message_len] = '\0';
  if (message_len == (W61_MAX_AT_LOG_LENGTH - 1U))
  {
    log_message[message_len - 1U] = '.';
    log_message[message_len - 2U] = '.';
    log_message[message_len - 3U] = '.';
  }
  SYS_LOG_DEBUG("AT%s %s\n", inOut, log_message);
}

#if defined(__ICCARM__) || defined(__ICCRX__) || defined(__ARMCC_VERSION) /* For IAR/MDK Compiler */
char *strnstr(const char *big, const char *little, size_t len)
{
  size_t i;
  size_t j;

  if (little[0] == '\0')
  {
    return ((char *)big);
  }
  j = 0;
  while ((j < len) && (big[j] != '\0'))
  {
    i = 0;
    while ((j < len) && (little[i] != '\0') && (big[j] != '\0') && (little[i] == big[j]))
    {
      ++i;
      ++j;
    }
    if (little[i] == '\0')
    {
      return ((char *)&big[j - i]);
    }
    j = j - i + 1U;
  }
  return NULL;
}
#endif /* __ICCARM__ || __ARMCC_VERSION */

/* Private Functions Definition ----------------------------------------------*/
static int32_t io_init(struct modem_iface *iface)
{
  if (iface == NULL)
  {
    return -EINVAL;
  }
  if (BusIo_SPI_Init() != 0)
  {
    return -1;
  }
  if (BusIo_SPI_Bind(SPI_MSG_CTRL_TRAFFIC_AT_CMD, (int32_t)IO_AT_CMDQ_DEPTH, NULL) != 0)
  {
    return -1;
  }
  iface->mdm_read = modem_iface_spi_read;
  iface->mdm_write = modem_iface_spi_write;
  return 0;
}

static int32_t io_deinit(struct modem_iface *iface)
{
  if (iface == NULL)
  {
    return -EINVAL;
  }
  if (BusIo_SPI_DeInit() != 0)
  {
    return -1;
  }
  iface->mdm_read = NULL;
  iface->mdm_write = NULL;
  return 0;
}

static void W61_Modem_Process_task(void *arg)
{
  struct modem *mdm = (struct modem *) arg;

  while (true)
  {
    modem_cmd_handler_process(&mdm->handler,
                              &mdm->iface);
  }
}

static int32_t modem_iface_spi_write(struct modem_iface *iface,
                                      const uint8_t *buf, size_t size)
{
  int32_t result;
  if (size == 0U)
  {
    return 0;
  }
  AT_LOG_HOST_OUT((uint8_t *)buf, size);
  result = BusIo_SPI_SendData(SPI_MSG_CTRL_TRAFFIC_AT_CMD, (uint8_t *)buf, size, IO_SEND_TIMEOUT);
  Debug_UART_NcpTrace("TX queued", buf, size, result);
  return result;
}

static int32_t modem_iface_spi_read(struct modem_iface *iface,
                                    uint8_t *buf, size_t size, size_t *bytes_read)
{
  struct modem *mdm;
  size_t available;
  size_t copy_len;
  int32_t received;

  if ((iface == NULL) || (buf == NULL) || (bytes_read == NULL) || (size == 0U))
  {
    return -EINVAL;
  }

  mdm = CONTAINER_OF(iface, struct modem, iface);
  *bytes_read = 0U;
  if (mdm->spi_rx_pending == NULL)
  {
    /* Take ownership of the complete framed SPI packet. Never ask spi_read()
     * to copy into the parser's remaining space: that API frees the packet
     * even when its destination is shorter than the packet. */
    received = BusIo_SPI_ReceivePtr(SPI_MSG_CTRL_TRAFFIC_AT_CMD,
                                    &mdm->spi_rx_pending,
                                    &mdm->spi_rx_pending_data,
                                    portMAX_DELAY);
    if ((received <= 0) || (mdm->spi_rx_pending == NULL) ||
        (mdm->spi_rx_pending_data == NULL))
    {
      if (mdm->spi_rx_pending != NULL)
      {
        (void)BusIo_SPI_Free(mdm->spi_rx_pending);
        mdm->spi_rx_pending = NULL;
      }
      mdm->spi_rx_pending_data = NULL;
      return (received < 0) ? received : -EIO;
    }
    mdm->spi_rx_pending_len = (size_t)received;
    mdm->spi_rx_pending_offset = 0U;
  }

  available = mdm->spi_rx_pending_len - mdm->spi_rx_pending_offset;
  copy_len = (available < size) ? available : size;
  (void)memcpy(buf, mdm->spi_rx_pending_data + mdm->spi_rx_pending_offset,
               copy_len);
  mdm->spi_rx_pending_offset += copy_len;
  AT_LOG_HOST_IN(buf, copy_len);
  Debug_UART_NcpTrace("RX read", buf, copy_len, (int32_t)copy_len);
  *bytes_read = copy_len;

  if (mdm->spi_rx_pending_offset == mdm->spi_rx_pending_len)
  {
    (void)BusIo_SPI_Free(mdm->spi_rx_pending);
    mdm->spi_rx_pending = NULL;
    mdm->spi_rx_pending_data = NULL;
    mdm->spi_rx_pending_len = 0U;
    mdm->spi_rx_pending_offset = 0U;
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_query)
{
  struct modem *mdm = (struct modem *) data->user_data;
  int32_t offset = ((uint8_t *) mdm->rx_data) - mdm->cmd_match_buf;
  /*len of the current mdm->cmd_match_buf + '\0'*/
  int32_t mlen = (argv[argc - 1] - mdm->cmd_match_buf) + strlen((char *) argv[argc - 1]) + 1;

  (void)memcpy(mdm->rx_data, (char *) mdm->cmd_match_buf, mlen);
  /* Record and offset argv to mdm->rx_data */
  for (int32_t i = 0; i < argc; i++)
  {
    mdm->argv[i] = (char *)(argv[i] + offset);
  }
  *mdm->argc = argc;

  return 0;
}

MODEM_CMD_DIRECT_DEFINE(on_cmd_tx_ready)
{
  struct modem *mdm = (struct modem *) data->user_data;

  (void)xSemaphoreGive(mdm->sem_tx_ready);
  return len;
}

MODEM_CMD_DEFINE(on_cmd_recv)
{
  struct modem *mdm = (struct modem *) data->user_data;
  int32_t recv_len = 0;
  if (argc > 0U)
  {
    recv_len = atoi((char *) argv[0]);
    /*check if length received by modem is matching the sent value */
    if (recv_len != mdm->rx_data_len)
    {
      (void)modem_cmd_handler_set_error(data, -EIO);
    }
    else
    {
      (void)modem_cmd_handler_set_error(data, 0);
    }
  }
  else
  {
    (void)modem_cmd_handler_set_error(data, -EIO);
  }

  if (!mdm->raw_tx_terminal_only)
  {
    mdm->raw_tx_response_received = true;
    (void)xSemaphoreGive(mdm->sem_response);
  }

  return 0;
}

/* Handler: OK */
MODEM_CMD_DEFINE(on_cmd_ok)
{
  struct modem *mdm = (struct modem *) data->user_data;

  (void)modem_cmd_handler_set_error(data, 0);

  mdm->raw_tx_response_received = true;
  (void)xSemaphoreGive(mdm->sem_response);

  return 0;
}

/* Handler: ERROR */
MODEM_CMD_DEFINE(on_cmd_error)
{
  struct modem *mdm = (struct modem *) data->user_data;

  (void)modem_cmd_handler_set_error(data, -EIO);

  mdm->raw_tx_response_received = true;
  (void)xSemaphoreGive(mdm->sem_response);

  return 0;
}

MODEM_CMD_DEFINE(on_cmd_ready)
{
  struct modem *mdm = (struct modem *) data->user_data;

  (void)xSemaphoreGive(mdm->sem_if_ready);

  return 0;
}

MODEM_CMD_DEFINE(on_cmd_wifi_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.WiFi_event_cb != NULL)
  {
    Obj->Callbacks.WiFi_event_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_wifi_scan_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.WiFi_event_scan_cb != NULL)
  {
    Obj->Callbacks.WiFi_event_scan_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_ble_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Ble_event_cb != NULL)
  {
    Obj->Callbacks.Ble_event_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DIRECT_DEFINE(on_cmd_ble_write_data_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Ble_event_data_cb != NULL)
  {
    int32_t consumed = Obj->Callbacks.Ble_event_data_cb(W61_BLE_EVT_WRITE_ID,
                                                        data, len);
    if ((consumed > 0) && (data->rx_buf != NULL) &&
        ((size_t)consumed <= data->rx_buf_len))
    {
      Debug_UART_NcpTracePingFrame("NCP direct parsed", data->rx_buf,
                                   (size_t)consumed);
    }
    return consumed;
  }
  return 0;
}

MODEM_CMD_DIRECT_DEFINE(on_cmd_ble_read_data_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Ble_event_data_cb != NULL)
  {
    return Obj->Callbacks.Ble_event_data_cb(W61_BLE_EVT_READ_ID, data, len);
  }
  return 0;
}

MODEM_CMD_DIRECT_DEFINE(on_cmd_ble_noti_data_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Ble_event_data_cb != NULL)
  {
    return Obj->Callbacks.Ble_event_data_cb(W61_BLE_EVT_NOTIFICATION_DATA_ID, data, len);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_net_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Net_event_cb != NULL)
  {
    Obj->Callbacks.Net_event_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_net_ping_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Net_event_ping_cb != NULL)
  {
    Obj->Callbacks.Net_event_ping_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_net_data_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.Net_event_data_cb != NULL)
  {
    Obj->Callbacks.Net_event_data_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DEFINE(on_cmd_mqtt_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.MQTT_event_cb != NULL)
  {
    Obj->Callbacks.MQTT_event_cb(Obj, &argc, (char **)argv);
  }
  return 0;
}

MODEM_CMD_DIRECT_DEFINE(on_cmd_mqtt_data_event)
{
  struct modem *mdm = (struct modem *) data->user_data;
  W61_Object_t *Obj = CONTAINER_OF(mdm, W61_Object_t, Modem);

  if (Obj->Callbacks.MQTT_event_data_cb != NULL)
  {
    return Obj->Callbacks.MQTT_event_data_cb(0, data, len);
  }
  return 0;
}

/** @} */
