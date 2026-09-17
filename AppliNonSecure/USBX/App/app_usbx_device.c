/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    app_usbx_device.c
  * @author  MCD Application Team
  * @brief   USBX Device applicative file
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
#include "app_usbx_device.h"
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdint.h>
#include <string.h>

#include "debug_uart.h"
#include "firmware_update.h"
#include "main.h"
#include "tof_app.h"
#include "usb_cdc_transport.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef enum
{
  APP_USB_DEVICE_STOP = 1,
  APP_USB_DEVICE_START,
  APP_USB_CDC_ACTIVATED,
  APP_USB_CDC_DEACTIVATED,
  APP_USB_CDC_PARAMETER_CHANGE,
  APP_USB_CDC_DEBUG_PROBE,
  APP_USB_CDC_RX_ERROR,
  APP_USB_CDC_TX_ERROR,
  APP_USB_DEVICE_EVENT_COUNT
} App_USB_DeviceEventType_t;

typedef struct
{
  ULONG type;
  ULONG value;
} App_USB_DeviceEvent_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define APP_USB_DEVICE_QUEUE_DEPTH       16U
#define APP_USB_WORKER_STOP_WAIT_TICKS   (TX_TIMER_TICKS_PER_SECOND / 2U)
#define APP_USB_CDC_PROBE_DELAY_TICKS    (3U * TX_TIMER_TICKS_PER_SECOND)
#define APP_USB_CDC_HEALTH_PERIOD_TICKS  (1U * TX_TIMER_TICKS_PER_SECOND)
#define APP_USB_CDC_MAX_RECOVERIES       3U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

static ULONG cdc_acm_interface_number;
static ULONG cdc_acm_configuration_number;
static UX_SLAVE_CLASS_CDC_ACM_PARAMETER cdc_acm_parameter;
static TX_THREAD ux_device_app_thread;

/* USER CODE BEGIN PV */
extern PCD_HandleTypeDef           hpcd_USB_OTG_HS1;
static TX_QUEUE                    usb_device_state_queue;
static TX_TIMER                    usb_cdc_probe_timer;
static ULONG                       usb_device_queue_storage[APP_USB_DEVICE_QUEUE_DEPTH * 2U];
static UINT                        usb_device_started;
static UINT                        usb_cdc_active;
static UINT                        usb_cdc_probe_sent;
static UINT                        usb_cdc_recovery_count;
static UX_SLAVE_CLASS_CDC_ACM     *usb_cdc_current_instance;
static volatile ULONG             usb_device_event_post_failures;
static volatile ULONG             usb_device_event_post_failures_by_type[APP_USB_DEVICE_EVENT_COUNT];
static volatile ULONG             usb_device_last_failed_event_type;
static volatile ULONG             usb_device_last_failed_event_status;
static volatile ULONG             usb_cdc_parameter_change_count;
static volatile UINT              usb_cdc_dtr_asserted;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
static VOID app_ux_device_thread_entry(ULONG thread_input);
/* USER CODE BEGIN PFP */
static UINT app_usb_device_post_event(App_USB_DeviceEventType_t type,
                                      ULONG value);
static void app_usb_device_stop_data_plane(void);
static void app_usb_cdc_probe_timer_entry(ULONG timer_input);
static void app_usb_device_restart_data_plane(UINT cause);
static UINT app_usb_cdc_start_health_timer(void);
static void app_usb_cdc_stop_health_timer(void);

/* USER CODE END PFP */

/**
  * @brief  Application USBX Device Initialization.
  * @param  memory_ptr: memory pointer
  * @retval status
  */

UINT MX_USBX_Device_Init(VOID *memory_ptr)
{
  UINT ret = UX_SUCCESS;
  UCHAR *pointer;
  TX_BYTE_POOL *byte_pool = (TX_BYTE_POOL*)memory_ptr;
  /* USER CODE BEGIN MX_USBX_Device_Init 0 */
  Debug_UART_Log("USBX", "Creating USB device control thread");
  /* USER CODE END MX_USBX_Device_Init 0 */

  /* USER CODE BEGIN MX_USBX_Device_Init 1 */
  /* USER CODE END MX_USBX_Device_Init 1 */

  /* Allocate the stack for device application main thread */
  if (tx_byte_allocate(byte_pool, (VOID **) &pointer, UX_DEVICE_APP_THREAD_STACK_SIZE,
                       TX_NO_WAIT) != TX_SUCCESS)
  {
    /* USER CODE BEGIN MAIN_THREAD_ALLOCATE_STACK_ERROR */
    Debug_UART_Log("USBX", "ERROR: device-thread stack allocation failed");
    return TX_POOL_ERROR;
    /* USER CODE END MAIN_THREAD_ALLOCATE_STACK_ERROR */
  }

  /* Create the device application main thread */
  if (tx_thread_create(&ux_device_app_thread, UX_DEVICE_APP_THREAD_NAME, app_ux_device_thread_entry,
                       0, pointer, UX_DEVICE_APP_THREAD_STACK_SIZE, UX_DEVICE_APP_THREAD_PRIO,
                       UX_DEVICE_APP_THREAD_PREEMPTION_THRESHOLD, UX_DEVICE_APP_THREAD_TIME_SLICE,
                       UX_DEVICE_APP_THREAD_START_OPTION) != TX_SUCCESS)
  {
    /* USER CODE BEGIN MAIN_THREAD_CREATE_ERROR */
    Debug_UART_Log("USBX", "ERROR: device-thread creation failed");
    return TX_THREAD_ERROR;
    /* USER CODE END MAIN_THREAD_CREATE_ERROR */
  }

  /* USER CODE BEGIN MX_USBX_Device_Init 2 */
  if (tx_queue_create(&usb_device_state_queue, "USB device state queue",
                      TX_2_ULONG, usb_device_queue_storage,
                      sizeof(usb_device_queue_storage)) != TX_SUCCESS)
  {
    Debug_UART_Log("USBX", "ERROR: device-state queue creation failed");
    return TX_QUEUE_ERROR;
  }

  if (tx_timer_create(&usb_cdc_probe_timer, "USB CDC delayed probe",
                      app_usb_cdc_probe_timer_entry, 0U,
                      APP_USB_CDC_PROBE_DELAY_TICKS,
                      APP_USB_CDC_HEALTH_PERIOD_TICKS,
                      TX_NO_ACTIVATE) != TX_SUCCESS)
  {
    Debug_UART_Log("USBX", "ERROR: CDC debug-probe timer creation failed");
    return TX_TIMER_ERROR;
  }

  if (USB_CDC_Transport_Init() != TX_SUCCESS)
  {
    Debug_UART_Log("USBX", "ERROR: CDC transport initialization failed");
    return TX_NOT_AVAILABLE;
  }

  usb_device_started = 0U;
  usb_cdc_active = 0U;
  usb_cdc_probe_sent = 0U;
  usb_cdc_recovery_count = 0U;
  usb_cdc_current_instance = UX_NULL;
  usb_device_event_post_failures = 0U;
  memset((void *)usb_device_event_post_failures_by_type, 0,
         sizeof(usb_device_event_post_failures_by_type));
  usb_device_last_failed_event_type = 0U;
  usb_device_last_failed_event_status = TX_SUCCESS;
  usb_cdc_parameter_change_count = 0U;
  usb_cdc_dtr_asserted = UX_FALSE;
  Debug_UART_Log("USBX", "USB manager, event queue, RX/TX workers created");
  /* USER CODE END MX_USBX_Device_Init 2 */

  return ret;
}

/**
  * @brief  MX_USBX_Device_Stack_Init
  *         Intialization of USB Device.
  *         Initialize the device stack, register of device class stack
  *         Register of the usb device controller
  * @param  None
  * @retval ret
  */
UINT MX_USBX_Device_Stack_Init(void)
{
  UINT ret = UX_SUCCESS;
  UCHAR *device_framework_high_speed;
  UCHAR *device_framework_full_speed;
  ULONG device_framework_hs_length;
  ULONG device_framework_fs_length;
  ULONG string_framework_length;
  ULONG language_id_framework_length;
  UCHAR *string_framework;
  UCHAR *language_id_framework;

  /* USER CODE BEGIN MX_USBX_Device_Stack_Init 0 */
  Debug_UART_Log("USBX", "Initializing USBX device stack");

  /* USER CODE END MX_USBX_Device_Stack_Init 0 */
  /* Get Device Framework High Speed and get the length */
  device_framework_high_speed = USBD_Get_Device_Framework_Speed(USBD_HIGH_SPEED,
                                                                &device_framework_hs_length);

  /* Get Device Framework Full Speed and get the length */
  device_framework_full_speed = USBD_Get_Device_Framework_Speed(USBD_FULL_SPEED,
                                                                &device_framework_fs_length);

  /* Get String Framework and get the length */
  string_framework = USBD_Get_String_Framework(&string_framework_length);

  /* Get Language Id Framework and get the length */
  language_id_framework = USBD_Get_Language_Id_Framework(&language_id_framework_length);

  /* Install the device portion of USBX */
  if (ux_device_stack_initialize(device_framework_high_speed,
                                 device_framework_hs_length,
                                 device_framework_full_speed,
                                 device_framework_fs_length,
                                 string_framework,
                                 string_framework_length,
                                 language_id_framework,
                                 language_id_framework_length,
                                 UX_NULL) != UX_SUCCESS)
  {
    /* USER CODE BEGIN USBX_DEVICE_INITIALIZE_ERROR */
    Debug_UART_Log("USBX", "ERROR: ux_device_stack_initialize failed");
    return UX_ERROR;
    /* USER CODE END USBX_DEVICE_INITIALIZE_ERROR */
  }

  /* Initialize the cdc acm class parameters for the device */
  cdc_acm_parameter.ux_slave_class_cdc_acm_instance_activate   = USBD_CDC_ACM_Activate;
  cdc_acm_parameter.ux_slave_class_cdc_acm_instance_deactivate = USBD_CDC_ACM_Deactivate;
  cdc_acm_parameter.ux_slave_class_cdc_acm_parameter_change    = USBD_CDC_ACM_ParameterChange;

  /* USER CODE BEGIN CDC_ACM_PARAMETER */

  /* USER CODE END CDC_ACM_PARAMETER */

  /* Get cdc acm configuration number */
  cdc_acm_configuration_number = USBD_Get_Configuration_Number(CLASS_TYPE_CDC_ACM, 0);

  /* Find cdc acm interface number */
  cdc_acm_interface_number = USBD_Get_Interface_Number(CLASS_TYPE_CDC_ACM, 0);

  /* Initialize the device cdc acm class */
  if (ux_device_stack_class_register(_ux_system_slave_class_cdc_acm_name,
                                     ux_device_class_cdc_acm_entry,
                                     cdc_acm_configuration_number,
                                     cdc_acm_interface_number,
                                     &cdc_acm_parameter) != UX_SUCCESS)
  {
    /* USER CODE BEGIN USBX_DEVICE_CDC_ACM_REGISTER_ERROR */
    Debug_UART_Log("USBX", "ERROR: CDC ACM class registration failed");
    return UX_ERROR;
    /* USER CODE END USBX_DEVICE_CDC_ACM_REGISTER_ERROR */
  }

  /* Initialize and link controller HAL driver */
  ux_dcd_stm32_initialize((ULONG)USB1_OTG_HS, (ULONG)&hpcd_USB_OTG_HS1);
  /* USER CODE BEGIN MX_USBX_Device_Stack_Init_PostTreatment */
  Debug_UART_Log("USBX", "USBX device stack initialized");
  /* USER CODE END MX_USBX_Device_Stack_Init_PostTreatment */

  /* USER CODE BEGIN MX_USBX_Device_Stack_Init 1 */

  /* USER CODE END MX_USBX_Device_Stack_Init 1 */

  return ret;
}

/**
  * @brief  Function implementing app_ux_device_thread_entry.
  * @param  thread_input: User thread input parameter.
  * @retval none
  */
static VOID app_ux_device_thread_entry(ULONG thread_input)
{
  /* USER CODE BEGIN app_ux_device_thread_entry */
  App_USB_DeviceEvent_t event;
  UINT status;
  ULONG reported_post_failures = 0U;
  ULONG reported_parameter_changes = 0U;

  TX_PARAMETER_NOT_USED(thread_input);
  Debug_UART_Log("USBX", "USB device control thread running");
  Debug_UART_Log("USBX", "Waiting for USB-PD CAD attach event");

  for (;;)
  {
    if (tx_queue_receive(&usb_device_state_queue, &event,
                         TX_WAIT_FOREVER) != TX_SUCCESS)
    {
      Debug_UART_Log("USBX", "ERROR: device-state queue receive failed");
      Error_Handler();
    }

    if (usb_device_event_post_failures != reported_post_failures)
    {
      Debug_UART_Log("USBX",
                     "WARNING: event queue post failures=%lu (+%lu), last(type=%lu status=%lu), by-type(stop=%lu start=%lu activate=%lu deactivate=%lu health=%lu rx-error=%lu tx-error=%lu)",
                     (unsigned long)usb_device_event_post_failures,
                     (unsigned long)(usb_device_event_post_failures -
                                     reported_post_failures),
                     (unsigned long)usb_device_last_failed_event_type,
                     (unsigned long)usb_device_last_failed_event_status,
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_DEVICE_STOP],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_DEVICE_START],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_CDC_ACTIVATED],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_CDC_DEACTIVATED],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_CDC_DEBUG_PROBE],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_CDC_RX_ERROR],
                     (unsigned long)usb_device_event_post_failures_by_type[APP_USB_CDC_TX_ERROR]);
      reported_post_failures = usb_device_event_post_failures;
    }
    if (usb_cdc_parameter_change_count != reported_parameter_changes)
    {
      Debug_UART_Log("CDC", "CDC line parameters changed: total=%lu (+%lu), DTR=%u",
                     (unsigned long)usb_cdc_parameter_change_count,
                     (unsigned long)(usb_cdc_parameter_change_count -
                                     reported_parameter_changes),
                     (unsigned int)usb_cdc_dtr_asserted);
      reported_parameter_changes = usb_cdc_parameter_change_count;
    }

    if ((event.type == APP_USB_DEVICE_START) && (usb_device_started == 0U))
    {
      Debug_UART_Log("USBX", "Calling MX_USB1_OTG_HS_PCD_Init");
      MX_USB1_OTG_HS_PCD_Init();
      Debug_UART_Log("USBX", "PCD initialized; calling USBX stack init");

      if (MX_USBX_Device_Stack_Init() != UX_SUCCESS)
      {
        Debug_UART_Log("USBX", "ERROR: USBX stack initialization failed");
        Error_Handler();
      }

      Debug_UART_Log("USBX", "Starting USB peripheral");
      if (HAL_PCD_Start(&hpcd_USB_OTG_HS1) != HAL_OK)
      {
        Debug_UART_Log("USBX", "ERROR: HAL_PCD_Start failed");
        Error_Handler();
      }

      usb_device_started = 1U;
      Debug_UART_Log("USBX", "USB peripheral started; waiting for enumeration");
    }
    else if ((event.type == APP_USB_DEVICE_STOP) && (usb_device_started != 0U))
    {
      Debug_UART_Log("USBX", "Stopping USB device");
      app_usb_cdc_stop_health_timer();
      USB_CDC_Transport_BeginStop();
      (void)ux_device_stack_disconnect();

      status = USB_CDC_Transport_WaitStopped(
          APP_USB_WORKER_STOP_WAIT_TICKS);
      if (status != TX_SUCCESS)
      {
        Debug_UART_Log("USBX", "WARNING: CDC workers stop wait returned %u",
                       (unsigned int)status);
      }

      (void)HAL_PCD_Stop(&hpcd_USB_OTG_HS1);

      if (MX_USBX_Device_Stack_DeInit() != UX_SUCCESS)
      {
        Debug_UART_Log("USBX", "ERROR: USBX stack deinitialization failed");
        Error_Handler();
      }

      (void)HAL_PCD_DeInit(&hpcd_USB_OTG_HS1);
      usb_cdc_active = 0U;
      usb_cdc_current_instance = UX_NULL;
      usb_cdc_dtr_asserted = UX_FALSE;
      TOF_App_SetMapEnabled(0U);
      TOF_App_SetDatasetStreamEnabled(0U);
      usb_device_started = 0U;
      Debug_UART_Log("USBX", "USB device stopped");
    }
    else if ((event.type == APP_USB_CDC_ACTIVATED) &&
             (usb_device_started != 0U) && (usb_cdc_active == 0U))
    {
      USB_CDC_Transport_SetHostReady(usb_cdc_dtr_asserted);
      status = USB_CDC_Transport_Start(
          (UX_SLAVE_CLASS_CDC_ACM *)(uintptr_t)event.value);
      if (status == TX_SUCCESS)
      {
        usb_cdc_active = 1U;
        usb_cdc_current_instance =
            (UX_SLAVE_CLASS_CDC_ACM *)(uintptr_t)event.value;
        usb_cdc_probe_sent = 0U;
        usb_cdc_recovery_count = 0U;
        (void)app_usb_cdc_start_health_timer();
        Debug_UART_Log("CDC", "CDC ACM activated; RX/TX data plane enabled");
      }
      else
      {
        Debug_UART_Log("CDC", "ERROR: data-plane start failed: %u",
                       (unsigned int)status);
      }
    }
    else if (event.type == APP_USB_CDC_DEACTIVATED)
    {
      app_usb_cdc_stop_health_timer();
      app_usb_device_stop_data_plane();
      usb_cdc_current_instance = UX_NULL;
      usb_cdc_dtr_asserted = UX_FALSE;
      USB_CDC_Transport_SetHostReady(UX_FALSE);
      TOF_App_SetMapEnabled(0U);
      TOF_App_SetDatasetStreamEnabled(0U);
      Debug_UART_Log("CDC", "CDC ACM deactivated; RX/TX data plane idle");
    }
    else if (event.type == APP_USB_CDC_DEBUG_PROBE)
    {
      ULONG diagnostic_flags;
      USB_CDC_TransportStatus_t transport_status;

      if ((usb_cdc_active != 0U) &&
          (USB_CDC_Transport_IsReady() == UX_TRUE))
      {
        if ((usb_cdc_probe_sent == 0U) &&
            (Firmware_Update_IsActive() == 0U))
        {
          usb_cdc_probe_sent = 1U;
          Debug_UART_Log("CDC",
                         "3-second health probe: transport online; CDC kept UI-only");
        }

        diagnostic_flags = USB_CDC_Transport_TakeDiagnosticFlags();
        if (diagnostic_flags != 0U)
        {
          USB_CDC_Transport_GetStatus(&transport_status);
          Debug_UART_Log(
              "CDC",
              "diagnostic flags=0x%08lX sync=%lu TX(drop=%lu unavailable=%lu slots=%lu queue=%lu timeout=%lu errors=%lu last=%lu) RX(drop=%lu slots=%lu queue=%lu errors=%lu last=%lu)",
              (unsigned long)diagnostic_flags,
              (unsigned long)transport_status.worker_sync_failures,
              (unsigned long)transport_status.tx_packets_dropped,
              (unsigned long)transport_status.tx_unavailable_drops,
              (unsigned long)transport_status.tx_slot_exhaustions,
              (unsigned long)transport_status.tx_queue_failures,
              (unsigned long)transport_status.tx_callback_timeouts,
              (unsigned long)transport_status.tx_errors,
              (unsigned long)transport_status.tx_last_error,
              (unsigned long)transport_status.rx_packets_dropped,
              (unsigned long)transport_status.rx_slot_exhaustions,
              (unsigned long)transport_status.rx_queue_failures,
              (unsigned long)transport_status.rx_errors,
              (unsigned long)transport_status.rx_last_error);

          if ((diagnostic_flags &
               (USB_CDC_DIAG_TX_CALLBACK_TIMEOUT |
                USB_CDC_DIAG_TX_TRANSFER_ERROR)) != 0U)
          {
            app_usb_device_restart_data_plane(
                (UINT)transport_status.tx_last_error);
          }
          else if ((diagnostic_flags &
                    USB_CDC_DIAG_RX_TRANSFER_ERROR) != 0U)
          {
            app_usb_device_restart_data_plane(
                (UINT)transport_status.rx_last_error);
          }
          else if ((diagnostic_flags &
                    USB_CDC_DIAG_WORKER_SYNC_FAILURE) != 0U)
          {
            /* A failed ThreadX event/semaphore/queue primitive can strand a
             * worker even when USBX itself reported no transfer error. */
            app_usb_device_restart_data_plane(TX_GROUP_ERROR);
          }
        }
      }
    }
    else if (event.type == APP_USB_CDC_RX_ERROR)
    {
      Debug_UART_Log("CDC", "RX worker reported USBX status=%lu",
                     (unsigned long)event.value);
    }
    else if (event.type == APP_USB_CDC_TX_ERROR)
    {
      Debug_UART_Log("CDC", "TX worker reported USBX status=%lu",
                     (unsigned long)event.value);
    }
  }
  /* USER CODE END app_ux_device_thread_entry */
}

/**
  * @brief  MX_USBX_Device_Stack_DeInit
  *         Unitialization of USB Device.
  *         uninitialize the device stack, unregister of device class stack
  *         unregister of the usb device controller
  * @retval ret
  */
UINT MX_USBX_Device_Stack_DeInit(void)
{
  UINT ret = UX_SUCCESS;

  /* USER CODE BEGIN MX_USBX_Device_Stack_DeInit_PreTreatment_0 */
  /* USER CODE END MX_USBX_Device_Stack_DeInit_PreTreatment_0 */

  /* Unregister USB device controller. */

  if (_ux_dcd_stm32_uninitialize((ULONG)USB1_OTG_HS, (ULONG)&hpcd_USB_OTG_HS1) != UX_SUCCESS)
  {
    return UX_ERROR;
  }

  /* Unregister CDC ACM class. */
  if (ux_device_stack_class_unregister(_ux_system_slave_class_cdc_acm_name,
                                     ux_device_class_cdc_acm_entry) != UX_SUCCESS)
  {
    return UX_ERROR;
  }

  /* The code below is required for uninstalling the device portion of USBX.  */
  if (ux_device_stack_uninitialize() != UX_SUCCESS)
  {
    return UX_ERROR;
  }

  /* USER CODE BEGIN MX_USBX_Device_Stack_DeInit_PreTreatment_1 */
  /* USER CODE END MX_USBX_Device_Stack_DeInit_PreTreatment_1 */

  /* USER CODE BEGIN MX_USBX_Device_Stack_DeInit_PostTreatment */
  /* USER CODE END MX_USBX_Device_Stack_DeInit_PostTreatment */

  return ret;
}

/* USER CODE BEGIN 1 */
UINT App_USBX_Device_RequestStart(void)
{
  return app_usb_device_post_event(APP_USB_DEVICE_START, 0U);
}

UINT App_USBX_Device_RequestStop(void)
{
  return app_usb_device_post_event(APP_USB_DEVICE_STOP, 0U);
}

UINT App_USBX_Device_NotifyCdcActivated(VOID *cdc_acm_instance)
{
  return app_usb_device_post_event(APP_USB_CDC_ACTIVATED,
                                   (ULONG)(uintptr_t)cdc_acm_instance);
}

UINT App_USBX_Device_NotifyCdcDeactivated(VOID *cdc_acm_instance)
{
  return app_usb_device_post_event(APP_USB_CDC_DEACTIVATED,
                                   (ULONG)(uintptr_t)cdc_acm_instance);
}

UINT App_USBX_Device_NotifyCdcParameterChange(VOID *cdc_acm_instance)
{
  UX_SLAVE_CLASS_CDC_ACM *cdc_acm =
      (UX_SLAVE_CLASS_CDC_ACM *)cdc_acm_instance;
  UINT dtr_asserted = UX_FALSE;

  if (cdc_acm != UX_NULL)
  {
    dtr_asserted = (cdc_acm->ux_slave_class_cdc_acm_data_dtr_state != 0U)
                       ? UX_TRUE
                       : UX_FALSE;
  }

  usb_cdc_dtr_asserted = dtr_asserted;
  USB_CDC_Transport_SetHostReady(dtr_asserted);
  if (dtr_asserted == UX_FALSE)
  {
    /* Windows keeps an enumerated CDC device configured after the COM handle
     * closes.  DTR is the session boundary: stop high-rate producers before
     * an unread endpoint can strand or fill the asynchronous TX data plane.
     * ToF acquisition/processing intentionally continues in the background. */
    TOF_App_SetMapEnabled(0U);
    TOF_App_SetDatasetStreamEnabled(0U);
  }

  /* Hosts commonly emit a burst of class-control requests while opening a
   * COM port. Retain a cumulative counter instead of consuming lifecycle-
   * manager queue entries. The manager reports the delta and DTR state from
   * task context on its next event. */
  TX_INTERRUPT_SAVE_AREA
  TX_DISABLE
  ++usb_cdc_parameter_change_count;
  TX_RESTORE
  return TX_SUCCESS;
}

UINT App_USBX_Device_ReportRxError(UINT usb_status)
{
  return app_usb_device_post_event(APP_USB_CDC_RX_ERROR,
                                   (ULONG)usb_status);
}

UINT App_USBX_Device_ReportTxError(UINT usb_status)
{
  return app_usb_device_post_event(APP_USB_CDC_TX_ERROR,
                                   (ULONG)usb_status);
}

static UINT app_usb_device_post_event(App_USB_DeviceEventType_t type,
                                      ULONG value)
{
  App_USB_DeviceEvent_t event;
  UINT status;

  event.type = (ULONG)type;
  event.value = value;
  status = tx_queue_send(&usb_device_state_queue, &event, TX_NO_WAIT);
  if (status != TX_SUCCESS)
  {
    TX_INTERRUPT_SAVE_AREA
    TX_DISABLE
    ++usb_device_event_post_failures;
    if ((ULONG)type < (ULONG)APP_USB_DEVICE_EVENT_COUNT)
    {
      ++usb_device_event_post_failures_by_type[type];
    }
    usb_device_last_failed_event_type = (ULONG)type;
    usb_device_last_failed_event_status = (ULONG)status;
    TX_RESTORE
  }
  return status;
}

static void app_usb_device_stop_data_plane(void)
{
  UINT status;

  if (usb_cdc_active == 0U)
  {
    return;
  }

  USB_CDC_Transport_BeginStop();
  status = USB_CDC_Transport_WaitStopped(APP_USB_WORKER_STOP_WAIT_TICKS);
  if (status != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "WARNING: CDC worker stop returned %u",
                   (unsigned int)status);
  }
  usb_cdc_active = 0U;
}

static void app_usb_cdc_probe_timer_entry(ULONG timer_input)
{
  (void)timer_input;
  /* Timer callbacks must stay non-blocking. The USB manager performs the
   * readiness check and enqueues the diagnostic packet in thread context. */
  (void)app_usb_device_post_event(APP_USB_CDC_DEBUG_PROBE, 0U);
}

static UINT app_usb_cdc_start_health_timer(void)
{
  UINT status;

  status = tx_timer_deactivate(&usb_cdc_probe_timer);
  if (status == TX_SUCCESS)
  {
    status = tx_timer_change(&usb_cdc_probe_timer,
                             APP_USB_CDC_PROBE_DELAY_TICKS,
                             APP_USB_CDC_HEALTH_PERIOD_TICKS);
  }
  if (status == TX_SUCCESS)
  {
    status = tx_timer_activate(&usb_cdc_probe_timer);
  }
  if (status != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "ERROR: health timer start failed: status=%u",
                   (unsigned int)status);
  }
  return status;
}

static void app_usb_cdc_stop_health_timer(void)
{
  UINT status = tx_timer_deactivate(&usb_cdc_probe_timer);

  if (status != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "WARNING: health timer stop failed: status=%u",
                   (unsigned int)status);
  }
}

static void app_usb_device_restart_data_plane(UINT cause)
{
  UX_SLAVE_CLASS_CDC_ACM *instance = usb_cdc_current_instance;
  UINT status;

  if ((usb_cdc_active == 0U) || (usb_device_started == 0U) ||
      (instance == UX_NULL))
  {
    return;
  }

  app_usb_cdc_stop_health_timer();
  app_usb_device_stop_data_plane();

  if ((usb_cdc_recovery_count >= APP_USB_CDC_MAX_RECOVERIES) ||
      (USB_CDC_LL_IsConfigured(instance) == UX_FALSE))
  {
    Debug_UART_Log("CDC",
                   "ERROR: data-plane recovery stopped: cause=%u attempts=%u configured=%u",
                   (unsigned int)cause,
                   (unsigned int)usb_cdc_recovery_count,
                   (unsigned int)USB_CDC_LL_IsConfigured(instance));
    return;
  }

  USB_CDC_Transport_SetHostReady(usb_cdc_dtr_asserted);
  status = USB_CDC_Transport_Start(instance);
  if (status == TX_SUCCESS)
  {
    ++usb_cdc_recovery_count;
    usb_cdc_active = 1U;
    usb_cdc_probe_sent = 0U;
    (void)app_usb_cdc_start_health_timer();
    Debug_UART_Log("CDC",
                   "data plane recovered: cause=%u attempt=%u new session active",
                   (unsigned int)cause,
                   (unsigned int)usb_cdc_recovery_count);
  }
  else
  {
    Debug_UART_Log("CDC", "ERROR: data-plane restart failed: cause=%u status=%u",
                   (unsigned int)cause, (unsigned int)status);
  }
}

/* USER CODE END 1 */
