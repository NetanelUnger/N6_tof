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
#include "cloud_relay.h"
#include "freertos_compat.h"
#include "debug_cli.h"
#include "debug_uart.h"
#include "display_app.h"
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
#define TX_DISPLAY_STACK_SIZE          (4U * 1024U)
#define TX_DISPLAY_PRIORITY            (8U)
#define TX_DEBUG_UART_STACK_SIZE       (3U * 1024U)
#define TX_DEBUG_UART_TEST_STACK_SIZE  (3U * 1024U)
/* The priority-10 ToF processor is intentionally continuously ready and uses
 * no time slice.  Keep the short UART queue owner above application producers
 * so interrupt completions cannot be stranded behind CPU-bound processing. */
#define TX_DEBUG_UART_PRIORITY         (5U)
#define TX_DEBUG_UART_TEST_PRIORITY    (9U)
#define TX_WIFI_CONTROL_STACK_SIZE     (6144U)
#define TX_WIFI_CONTROL_PRIORITY       (11U)
#define TX_CLOUD_RELAY_STACK_SIZE       (8U * 1024U)
/* Priority 12 from the original plan can starve behind the continuously-ready
 * priority-10 ToF processor. Like the CLI/Radio loops, Cloud must outrank it;
 * Cloud yields on its own event wait and all blocking modem operations. */
#define TX_CLOUD_RELAY_PRIORITY         (9U)

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TX_THREAD tx_app_thread;
/* USER CODE BEGIN PV */
static TX_THREAD tx_tof_acquisition_thread;
static TX_THREAD tx_update_confirm_thread;
static TX_THREAD tx_debug_uart_thread;
static TX_THREAD tx_debug_uart_test_thread;
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static TX_THREAD tx_display_thread;
#endif
#if (APP_ST67W6X_ENABLED == 1U)
static TX_THREAD tx_wifi_ble_thread;
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static TX_THREAD tx_wifi_control_thread;
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static TX_THREAD tx_cloud_relay_thread;
/* Fixed stack in the existing lower SRAM4 region, outside both byte pools.
 * Never consume another 8 KiB of the scarce radio packet allocation reserve. */
static UCHAR cloud_relay_stack[TX_CLOUD_RELAY_STACK_SIZE]
    __attribute__((section(".app_shared_bss"), aligned(8)));
#endif
#if (APP_USB_CLI_ENABLED == 1U)
static TX_THREAD tx_usb_cli_thread;
#endif

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */
extern TX_BYTE_POOL *MX_RadioBytePool_Get(void);

static void ToFAcquisitionThread_Entry(ULONG thread_input);
static void UpdateConfirmThread_Entry(ULONG thread_input);
static void DebugUartThread_Entry(ULONG thread_input);
static void DebugUartTestThread_Entry(ULONG thread_input);
#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static void DisplayThread_Entry(ULONG thread_input);
#endif
#if (APP_ST67W6X_ENABLED == 1U)
static void WiFiBleThread_Entry(ULONG thread_input);
#endif
#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void WiFiControlThread_Entry(ULONG thread_input);
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void CloudRelayThread_Entry(ULONG thread_input);
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
  CHAR *debug_uart_stack;
  CHAR *debug_uart_test_stack;

  if (Debug_UART_AsyncInitialize() != 0)
  {
    return TX_QUEUE_ERROR;
  }
  if (tx_byte_allocate(byte_pool, (VOID **)&debug_uart_stack,
                       TX_DEBUG_UART_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  if (tx_thread_create(&tx_debug_uart_thread, "Debug UART TX",
                       DebugUartThread_Entry, 0U, debug_uart_stack,
                       TX_DEBUG_UART_STACK_SIZE, TX_DEBUG_UART_PRIORITY,
                       TX_DEBUG_UART_PRIORITY, TX_NO_TIME_SLICE,
                       TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }
  if (tx_byte_allocate(byte_pool, (VOID **)&debug_uart_test_stack,
                       TX_DEBUG_UART_TEST_STACK_SIZE,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  if (tx_thread_create(&tx_debug_uart_test_thread, "Debug UART test",
                       DebugUartTestThread_Entry, 0U, debug_uart_test_stack,
                       TX_DEBUG_UART_TEST_STACK_SIZE,
                       TX_DEBUG_UART_TEST_PRIORITY,
                       TX_DEBUG_UART_TEST_PRIORITY, TX_NO_TIME_SLICE,
                       TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

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

  /* Resolve the shared EXTI9 line before either ToF or radio workers can run.
     This also enforces safe NCP boot levels (active-high CS, BOOT, and
     CHIP_EN all low). */
  WIFI_BLE_App_ConfigureHardware();
#if (APP_ST67W6X_ENABLED == 1U)
  Debug_UART_Log("RADIO", "EXTI9 routed to PE9 SPI_RDY; ToF uses bounded GPIO polling");
#endif

#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
  if (Display_App_Init() != TX_SUCCESS)
  {
    return TX_GROUP_ERROR;
  }
  if (tx_byte_allocate(byte_pool, (VOID **)&pointer,
                       TX_DISPLAY_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }
  if (tx_thread_create(&tx_display_thread, "GC9A01 display",
                       DisplayThread_Entry, 0U, pointer,
                       TX_DISPLAY_STACK_SIZE, TX_DISPLAY_PRIORITY,
                       TX_DISPLAY_PRIORITY, TX_NO_TIME_SLICE,
                       TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }
#endif

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
  TX_BYTE_POOL *radio_pool = MX_RadioBytePool_Get();

  /* The ST67 vendor driver uses the small FreeRTOS-to-ThreadX compatibility
     layer.  Keep its dynamic objects, internal task stacks, and the project
     Radio Manager stack in the isolated SRAM4 pool. */
  if ((radio_pool == TX_NULL) ||
      (FreeRTOS_Compat_Init(radio_pool) != TX_SUCCESS))
  {
    return TX_POOL_ERROR;
  }

  if (tx_byte_allocate(radio_pool, (VOID **)&pointer,
                       TX_WIFI_BLE_STACK_SIZE, TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }

  if (tx_thread_create(&tx_wifi_ble_thread, "ST67 Radio Manager", WiFiBleThread_Entry,
                       0U, pointer, TX_WIFI_BLE_STACK_SIZE,
                       TX_WIFI_BLE_THREAD_PRIO, TX_WIFI_BLE_THREAD_PRIO,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
  if (tx_byte_allocate(radio_pool, (VOID **)&pointer,
                       TX_WIFI_CONTROL_STACK_SIZE,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    return TX_POOL_ERROR;
  }

  /* Preserve the existing task/diagnostic name and stack. This worker now
   * owns slow BLE control commands as well as Wi-Fi requests. */
  if (tx_thread_create(&tx_wifi_control_thread, "ST67 Wi-Fi control",
                       WiFiControlThread_Entry, 0U, pointer,
                       TX_WIFI_CONTROL_STACK_SIZE,
                       TX_WIFI_CONTROL_PRIORITY, TX_WIFI_CONTROL_PRIORITY,
                       TX_NO_TIME_SLICE, TX_AUTO_START) != TX_SUCCESS)
  {
    (void)tx_byte_release(pointer);
    return TX_THREAD_ERROR;
  }
  Debug_UART_Log("RTOS", "Wi-Fi control task created in SRAM4");
#endif
#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
  if (CloudRelay_Prepare() != TX_SUCCESS) return TX_QUEUE_ERROR;
  if (tx_thread_create(&tx_cloud_relay_thread, "ST67 Cloud Relay",
                       CloudRelayThread_Entry, 0U, cloud_relay_stack,
                       sizeof(cloud_relay_stack), TX_CLOUD_RELAY_PRIORITY,
                       TX_CLOUD_RELAY_PRIORITY, TX_NO_TIME_SLICE,
                       TX_AUTO_START) != TX_SUCCESS)
  {
    return TX_THREAD_ERROR;
  }
  Debug_UART_Log("RTOS", "Cloud worker created with fixed SRAM4 stack");
#endif
#endif

#if (APP_ST67W6X_ENABLED == 0U)
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
static void DebugUartThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  Debug_UART_TaskRun();
}

static void DebugUartTestThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  Debug_UART_TestTaskRun();
}

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

#if (APP_GC9A01_DISPLAY_ENABLED == 1U)
static void DisplayThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  Display_App_Run();
}
#endif

#if (APP_ST67W6X_ENABLED == 1U)
static void WiFiBleThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  WIFI_BLE_App_Run();
}
#endif

#if (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || (APP_ST67W6X_BLE_GATT_ENABLED == 1U)
static void WiFiControlThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  WIFI_BLE_App_WifiControlRun();
}
#endif

#if (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)
static void CloudRelayThread_Entry(ULONG thread_input)
{
  (void)thread_input;
  CloudRelay_Run();
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
