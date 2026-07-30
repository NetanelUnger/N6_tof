/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    ux_device_cdc_acm.c
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
#include "ux_device_cdc_acm.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "app_usbx_device.h"
#include "debug_uart.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN PV */
/* The USB manager owns the active CDC instance.  This callback layer only
 * publishes lifecycle events and exposes low-level worker-only I/O calls. */
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  USBD_CDC_ACM_Activate
  *         This function is called when insertion of a CDC ACM device.
  * @param  cdc_acm_instance: Pointer to the cdc acm class instance.
  * @retval none
  */
VOID USBD_CDC_ACM_Activate(VOID *cdc_acm_instance)
{
  /* USER CODE BEGIN USBD_CDC_ACM_Activate */
  if (App_USBX_Device_NotifyCdcActivated(cdc_acm_instance) != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "ERROR: failed to queue CDC activate event");
  }
  /* USER CODE END USBD_CDC_ACM_Activate */

  return;
}

/**
  * @brief  USBD_CDC_ACM_Deactivate
  *         This function is called when extraction of a CDC ACM device.
  * @param  cdc_acm_instance: Pointer to the cdc acm class instance.
  * @retval none
  */
VOID USBD_CDC_ACM_Deactivate(VOID *cdc_acm_instance)
{
  /* USER CODE BEGIN USBD_CDC_ACM_Deactivate */
  if (App_USBX_Device_NotifyCdcDeactivated(cdc_acm_instance) != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "ERROR: failed to queue CDC deactivate event");
  }
  /* USER CODE END USBD_CDC_ACM_Deactivate */

  return;
}

/**
  * @brief  USBD_CDC_ACM_ParameterChange
  *         This function is invoked to manage the CDC ACM class requests.
  * @param  cdc_acm_instance: Pointer to the cdc acm class instance.
  * @retval none
  */
VOID USBD_CDC_ACM_ParameterChange(VOID *cdc_acm_instance)
{
  /* USER CODE BEGIN USBD_CDC_ACM_ParameterChange */
  if (App_USBX_Device_NotifyCdcParameterChange(cdc_acm_instance) != TX_SUCCESS)
  {
    Debug_UART_Log("CDC", "ERROR: failed to queue CDC parameter event");
  }
  /* USER CODE END USBD_CDC_ACM_ParameterChange */

  return;
}

/* USER CODE BEGIN 1 */

UINT USB_CDC_LL_IsConfigured(UX_SLAVE_CLASS_CDC_ACM *instance)
{
  UX_SLAVE_DEVICE *device = &_ux_system_slave->ux_system_slave_device;

  return ((device->ux_slave_device_state == UX_DEVICE_CONFIGURED) &&
          (instance != UX_NULL)) ? UX_TRUE : UX_FALSE;
}

UINT USB_CDC_LL_StartCallbacks(
    UX_SLAVE_CLASS_CDC_ACM *instance,
    UINT (*write_callback)(UX_SLAVE_CLASS_CDC_ACM *, UINT, ULONG),
    UINT (*read_callback)(UX_SLAVE_CLASS_CDC_ACM *, UINT, UCHAR *, ULONG))
{
  UX_SLAVE_CLASS_CDC_ACM_CALLBACK_PARAMETER callbacks;

  if ((instance == UX_NULL) || (write_callback == UX_NULL) ||
      (read_callback == UX_NULL))
  {
    return UX_INVALID_PARAMETER;
  }

  if (USB_CDC_LL_IsConfigured(instance) == UX_FALSE)
  {
    return UX_ERROR;
  }

  callbacks.ux_device_class_cdc_acm_parameter_write_callback = write_callback;
  callbacks.ux_device_class_cdc_acm_parameter_read_callback = read_callback;
  return ux_device_class_cdc_acm_ioctl(
      instance, UX_SLAVE_CLASS_CDC_ACM_IOCTL_TRANSMISSION_START,
      &callbacks);
}

UINT USB_CDC_LL_StopCallbacks(UX_SLAVE_CLASS_CDC_ACM *instance)
{
  if (instance == UX_NULL)
  {
    return UX_INVALID_PARAMETER;
  }

  return ux_device_class_cdc_acm_ioctl(
      instance, UX_SLAVE_CLASS_CDC_ACM_IOCTL_TRANSMISSION_STOP, UX_NULL);
}

UINT USB_CDC_LL_WriteAsync(UX_SLAVE_CLASS_CDC_ACM *instance,
                           const void *buffer, ULONG length)
{
  if ((instance == UX_NULL) || (buffer == UX_NULL) || (length == 0U))
  {
    return UX_INVALID_PARAMETER;
  }

  if ((instance == UX_NULL) ||
      (USB_CDC_LL_IsConfigured(instance) == UX_FALSE))
  {
    return UX_ERROR;
  }

  return ux_device_class_cdc_acm_write_with_callback(
      instance, (UCHAR *)buffer, length);
}

/* USER CODE END 1 */
