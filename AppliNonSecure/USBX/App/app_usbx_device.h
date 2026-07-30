/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    app_usbx_device.h
  * @author  MCD Application Team
  * @brief   USBX Device applicative header file
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
/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __APP_USBX_DEVICE_H__
#define __APP_USBX_DEVICE_H__

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "ux_api.h"
#include "ux_device_cdc_acm.h"
#include "ux_device_descriptors.h"
#include "app_azure_rtos_config.h"
#include "ux_dcd_stm32.h"
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/

#define UX_DEVICE_APP_THREAD_STACK_SIZE   1024
#define UX_DEVICE_APP_THREAD_PRIO         10

/* USER CODE BEGIN EC */

/*
 * CubeMX currently generates a 1 KiB USB device control-thread stack.  That is
 * not enough once the STM32N6 HAL PCD initialization and the UART diagnostics
 * execute on this thread; ThreadX reports STKOF while entering
 * MX_USB1_OTG_HS_PCD_Init().  Keep the override in a USER CODE block so a
 * future Generate Code operation preserves it.
 */
#undef UX_DEVICE_APP_THREAD_STACK_SIZE
#define UX_DEVICE_APP_THREAD_STACK_SIZE   (16U * 1024U)

/* Keep the lifecycle manager above the RX/TX workers (priority 9).  A lower
 * ThreadX number is a higher priority. */
#undef UX_DEVICE_APP_THREAD_PRIO
#define UX_DEVICE_APP_THREAD_PRIO         8U

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
UINT MX_USBX_Device_Init(VOID *memory_ptr);
UINT MX_USBX_Device_Stack_Init(void);
UINT MX_USBX_Device_Stack_DeInit(void);

/* USER CODE BEGIN EFP */
UINT App_USBX_Device_RequestStart(void);
UINT App_USBX_Device_RequestStop(void);
UINT App_USBX_Device_NotifyCdcActivated(VOID *cdc_acm_instance);
UINT App_USBX_Device_NotifyCdcDeactivated(VOID *cdc_acm_instance);
UINT App_USBX_Device_NotifyCdcParameterChange(VOID *cdc_acm_instance);
UINT App_USBX_Device_ReportRxError(UINT usb_status);
UINT App_USBX_Device_ReportTxError(UINT usb_status);

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

#ifndef UX_DEVICE_APP_THREAD_NAME
#define UX_DEVICE_APP_THREAD_NAME  "USBX Device App Main Thread"
#endif

#ifndef UX_DEVICE_APP_THREAD_PREEMPTION_THRESHOLD
#define UX_DEVICE_APP_THREAD_PREEMPTION_THRESHOLD  UX_DEVICE_APP_THREAD_PRIO
#endif

#ifndef UX_DEVICE_APP_THREAD_TIME_SLICE
#define UX_DEVICE_APP_THREAD_TIME_SLICE  TX_NO_TIME_SLICE
#endif

#ifndef UX_DEVICE_APP_THREAD_START_OPTION
#define UX_DEVICE_APP_THREAD_START_OPTION  TX_AUTO_START
#endif

/* USER CODE BEGIN 1 */

/* USER CODE END 1 */

#ifdef __cplusplus
}
#endif
#endif /* __APP_USBX_DEVICE_H__ */
