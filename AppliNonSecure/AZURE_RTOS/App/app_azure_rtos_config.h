
/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    app_azure_rtos_config.h
  * @author  MCD Application Team
  * @brief   app_azure_rtos config header file
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
#ifndef APP_AZURE_RTOS_CONFIG_H
#define APP_AZURE_RTOS_CONFIG_H
#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "app_features.h"

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* Using static memory allocation via threadX Byte memory pools */

#define USE_STATIC_ALLOCATION                    1

#define TX_APP_MEM_POOL_SIZE                     160 * 1024

#define UX_APP_MEM_POOL_SIZE                     32768

#define USBPD_DEVICE_APP_MEM_POOL_SIZE              5000

/* USER CODE BEGIN EC */

/* The normal application threads reserve about 124 KiB of pool-backed stacks.
 * When the radio build is selected, its ST driver code also consumes the same
 * SRAM2 image/heap region.  Return another 8 KiB to the VL53L9 C heap; radio
 * tasks and transport allocations use the isolated SRAM4 pool below. */
#undef TX_APP_MEM_POOL_SIZE
#if (APP_ST67W6X_ENABLED == 1U)
#define TX_APP_MEM_POOL_SIZE                     (151U * 1024U)
#else
#define TX_APP_MEM_POOL_SIZE                     (159U * 1024U)
#endif

#define TX_RADIO_MEM_POOL_SIZE                   (64U * 1024U)

/* Allow for the 32 KiB USBX system arena plus the 16 KiB USB control-thread
 * stack, byte-pool bookkeeping, and about 8 KiB of parent-pool headroom. */
#undef UX_APP_MEM_POOL_SIZE
#define UX_APP_MEM_POOL_SIZE                     (56U * 1024U)

/* Queue storage, control blocks and the enlarged USB-PD CAD-thread stack. */
#undef USBPD_DEVICE_APP_MEM_POOL_SIZE
#define USBPD_DEVICE_APP_MEM_POOL_SIZE            (16U * 1024U)

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

#ifdef __cplusplus
}
#endif
#endif /* APP_AZURE_RTOS_CONFIG_H */
