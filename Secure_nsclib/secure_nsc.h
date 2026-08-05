/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    Secure_nsclib/secure_nsc.h
  * @author  MCD Application Team
  * @brief   Header for secure non-secure callable APIs list
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

/* USER CODE BEGIN Non_Secure_CallLib_h */
/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef SECURE_NSC_H
#define SECURE_NSC_H

/* Includes ------------------------------------------------------------------*/
#include <stdint.h>
#include "firmware_update_format.h"

/* Exported types ------------------------------------------------------------*/
/**
  * @brief  non-secure callback ID enumeration definition
  */
typedef enum
{
SECURE_FAULT_CB_ID     = 0x00U, /*!< System secure fault callback ID */
  IAC_ERROR_CB_ID       = 0x01U  /*!< Illegal access secure error callback ID */
} SECURE_CallbackIDTypeDef;

typedef enum
{
  SECURE_FW_UPDATE_OK = 0U,
  SECURE_FW_UPDATE_ERROR_PARAMETER = 1U,
  SECURE_FW_UPDATE_ERROR_STATE = 2U,
  SECURE_FW_UPDATE_ERROR_AUTHENTICATION = 3U,
  SECURE_FW_UPDATE_ERROR_VERSION = 4U,
  SECURE_FW_UPDATE_ERROR_FLASH = 5U,
  SECURE_FW_UPDATE_ERROR_VERIFY = 6U,
  SECURE_FW_UPDATE_ERROR_SIZE = 7U,
  SECURE_FW_UPDATE_ERROR_UNAVAILABLE = 8U
} SECURE_FirmwareUpdateStatus_t;
/* Exported constants --------------------------------------------------------*/
/* Exported macro ------------------------------------------------------------*/
/* Exported functions ------------------------------------------------------- */
void SECURE_RegisterCallback(SECURE_CallbackIDTypeDef CallbackId, void *func);
uint32_t SECURE_FirmwareUpdateBegin(const FW_UpdateManifest_t *manifest,
                                    uint32_t *session);
uint32_t SECURE_FirmwareUpdateWrite(uint32_t session, const uint8_t *data,
                                    uint32_t length);
uint32_t SECURE_FirmwareUpdateFinalize(uint32_t session);
uint32_t SECURE_FirmwareUpdateAbort(uint32_t session);
uint32_t SECURE_FirmwareUpdateConfirmBoot(void);

#endif /* SECURE_NSC_H */
/* USER CODE END Non_Secure_CallLib_h */

