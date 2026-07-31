/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    app_threadx.c
  * @author  MCD Application Team
  * @brief   ThreadX applicative file
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
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "app_threadx.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "app_console.h"
#include "app_features.h"
#include "freertos_compat.h"
#include "debug_cli.h"
#include "debug_uart.h"
#include "firmware_update.h"
#include "main.h"
#include "tof_app.h"
#include "wifi_ble_app.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define TX_TOF_ACQUISITION_STACK_SIZE  (16U * 1024U)
#define TX_TOF_ACQUISITION_PRIORITY    (7U)
#define TX_UPDATE_CONFIRM_STACK_SIZE   (2U * 1024U)
/* Confirmation must not be starved by the continuously-ready priority-10 ToF
 * processor.  It wakes once after five seconds, commits metadata, and exits. */
#define TX_UPDATE_CONFIRM_PRIORITY     (6U)

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TX_THREAD tx_app_thread;
/* USER CODE BEGIN PV */
static TX_THREAD tx_tof_acquisition_thread;
static TX_THREAD tx_update_confirm_thread;
#if (APP_ST67W6X_ENABLED == 1U)
static TX_THREAD tx_wifi_ble_thread;
#endif
#if (APP_USB_CLI_ENABLED == 1U)
static TX_THREAD tx_usb_cli_thread;
#endif

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */
static void ToFAcquisitionThread_Entry(ULONG thread_input);
static void UpdateConfirmThread_Entry(ULONG thread_input);
#if (APP_ST67W6X_ENABLED == 1U)
static void WiFiBleThread_Entry(ULONG thread_input);
#endif
#if (APP_USB_CLI_ENABLED == 1U)
static void UsbCliThread_Entry(ULONG thread_input);
#endif

/* USER CODE END PFP */

/**
  * @brief  Application ThreadX Initialization.
  * @param memory_ptr: memory pointer
  * @retval int
  */
UINT App_ThreadX_Init(VOID *memory_ptr)
{
  UINT ret = TX_SUCCESS;
  TX_BYTE_POOL *byte_pool = (TX_BYTE_POOL*)memory_ptr;

  /* USER CODE BEGIN App_ThreadX_MEM_POOL */
  if (TOF_App_Init() != TX_SUCCESS)
  {
    return TX_QUEUE_ERROR;
  }

  /* USER CODE END App_ThreadX_MEM_POOL */
  CHAR *pointer;

  /* Allocate the stack for ToF Main Thread  */
  if (tx_byte_allocate(byte_pool, (VOID**) &pointer,
                       TX_APP_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  /* Create ToF Main Thread.  */
  if (tx_thread_create(&tx_app_thread, "ToF Main Thread", MainThread_Entry, 0, pointer,
                       TX_APP_STACK_SIZE, TX_APP_THREAD_PRIO, TX_APP_THREAD_PREEMPTION_THRESHOLD,
                       TX_APP_THREAD_TIME_SLICE, TX_APP_THREAD_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

  /* USER CODE BEGIN App_ThreadX_Init */
  if (App_Console_Init() != TX_SUCCESS)
  {
    return TX_MUTEX_ERROR;
  }

  Debug_UART_Log("RTOS", "Console API ready; USB manager owns RX/TX workers");

  if (tx_byte_allocate(byte_pool, (VOID **)&pointer,
                       TX_TOF_ACQUISITION_STACK_SIZE,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  if (tx_thread_create(&tx_tof_acquisition_thread, "ToF Acquisition",
                       ToFAcquisitionThread_Entry, 0U, pointer,
                       TX_TOF_ACQUISITION_STACK_SIZE,
                       TX_TOF_ACQUISITION_PRIORITY,
                       TX_TOF_ACQUISITION_PRIORITY,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }
  Debug_UART_Log("RTOS", "ToF acquisition and processing tasks created");

  if (tx_byte_allocate(byte_pool, (VOID **)&pointer,
                       TX_UPDATE_CONFIRM_STACK_SIZE,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  if (tx_thread_create(&tx_update_confirm_thread, "Firmware confirmation",
                       UpdateConfirmThread_Entry, 0U, pointer,
                       TX_UPDATE_CONFIRM_STACK_SIZE,
                       TX_UPDATE_CONFIRM_PRIORITY,
                       TX_UPDATE_CONFIRM_PRIORITY,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

#if (APP_ST67W6X_ENABLED == 1U)
  /* The ST67 vendor driver uses the small FreeRTOS-to-ThreadX compatibility
     layer.  Do not initialize or allocate it while the radio is disabled. */
  if (FreeRTOS_Compat_Init(byte_pool) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }

  if (tx_byte_allocate(byte_pool, (VOID **)&pointer,
                       TX_WIFI_BLE_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }

  if (tx_thread_create(&tx_wifi_ble_thread, "ST67 WiFi BLE", WiFiBleThread_Entry,
                       0U, pointer, TX_WIFI_BLE_STACK_SIZE,
                       TX_WIFI_BLE_THREAD_PRIO, TX_WIFI_BLE_THREAD_PRIO,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }
#endif

#if (APP_ST67W6X_ENABLED == 0U)
  /* EXTI line 9 can select PD9 or PE9, never both.  While the radio shield is
     absent, route the line to the ToF active-low interrupt so acquisition is
     event driven instead of polling once per RTOS tick. */
  GPIO_InitTypeDef tof_int_gpio = { 0 };
  HAL_GPIO_DeInit(SPI_RDY_GPIO_Port, SPI_RDY_Pin);
  tof_int_gpio.Pin = TOF_INT_Pin;
  tof_int_gpio.Mode = GPIO_MODE_IT_FALLING;
  tof_int_gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(TOF_INT_GPIO_Port, &tof_int_gpio);
  HAL_NVIC_SetPriority(EXTI9_IRQn, 5U, 0U);
  HAL_NVIC_EnableIRQ(EXTI9_IRQn);
  Debug_UART_Log("RADIO", "ST67 Wi-Fi/BLE thread and hardware init are disabled");
#endif

#if (APP_USB_CLI_ENABLED == 1U)
  if (tx_byte_allocate(byte_pool, (VOID **)&pointer,
                       TX_USB_CLI_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }

  if (tx_thread_create(&tx_usb_cli_thread, "USB debug CLI", UsbCliThread_Entry,
                       0U, pointer, TX_USB_CLI_STACK_SIZE,
                       TX_USB_CLI_THREAD_PRIO, TX_USB_CLI_THREAD_PRIO,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

  Debug_UART_Log("CLI", "USB CLI thread created");
#endif
  /* USER CODE END App_ThreadX_Init */

  return ret;
}
/**
  * @brief  Function implementing the MainThread_Entry thread.
  * @param  thread_input: Not used.
  * @retval None
  */
void MainThread_Entry(ULONG thread_input)
{
  /* USER CODE BEGIN MainThread_Entry */
  (void)thread_input;
  Debug_UART_Log("TOF", "ToF processing task started");
  TOF_App_Process();
  /* USER CODE END MainThread_Entry */
}

  /**
  * @brief  Function that implements the kernel's initialization.
  * @param  None
  * @retval None
  */
void MX_ThreadX_Init(void)
{
  /* USER CODE BEGIN Before_Kernel_Start */
  Debug_UART_Log("RTOS", "Entering ThreadX kernel");

  /* USER CODE END Before_Kernel_Start */

  tx_kernel_enter();

  /* USER CODE BEGIN Kernel_Start_Error */

  /* USER CODE END Kernel_Start_Error */
}

/* USER CODE BEGIN 1 */
static void ToFAcquisitionThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  Debug_UART_Log("TOF", "ToF acquisition task started");
  TOF_App_Acquire();
}

static void UpdateConfirmThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  /* A trial image must remain alive under ThreadX long enough to prove that
   * startup and scheduling work before it closes the rollback window. */
  tx_thread_sleep(5U * TX_TIMER_TICKS_PER_SECOND);
  Firmware_Update_ConfirmBoot();
}

#if (APP_ST67W6X_ENABLED == 1U)
static void WiFiBleThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  WIFI_BLE_App_Run();
}
#endif

#if (APP_USB_CLI_ENABLED == 1U)
static void UsbCliThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  Debug_CLI_Run();
}
#endif

/* USER CODE END 1 */
