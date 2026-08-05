/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    Secure/Src/secure_nsc.c
  * @author  MCD Application Team
  * @brief   This file contains the non-secure callable APIs (secure world)
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

/* USER CODE BEGIN Non_Secure_CallLib */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "secure_nsc.h"
#include "secure_firmware_update.h"
/** @addtogroup STM32N6xx_HAL_Examples

  * @{
  */

/** @addtogroup Templates
  * @{
  */

/* Global variables ----------------------------------------------------------*/
void *pSecureFaultCallback = NULL;   /* Pointer to secure fault callback in Non-secure */
void *pSecureErrorCallback = NULL;   /* Pointer to secure error callback in Non-secure */

/* Private typedef -----------------------------------------------------------*/
/* Private define ------------------------------------------------------------*/
/* Private macro -------------------------------------------------------------*/
/* Private variables ---------------------------------------------------------*/
/* Private function prototypes -----------------------------------------------*/
/* Private functions ---------------------------------------------------------*/

/**
  * @brief  Secure registration of non-secure callback.
  * @param  CallbackId  callback identifier
  * @param  func        pointer to non-secure function
  * @retval None
  */
  CMSE_NS_ENTRY void SECURE_RegisterCallback(SECURE_CallbackIDTypeDef CallbackId, void *func)
  {
      if(func != NULL)
      {
        switch(CallbackId)
        {
          case SECURE_FAULT_CB_ID:           /* SecureFault Interrupt occurred */
          pSecureFaultCallback = func;
          break;
          case IAC_ERROR_CB_ID:             /* Illegal Access Interrupt occurred */
          pSecureErrorCallback = func;
          break;
          default:
          /* unknown */
          break;
        }
      }
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateBegin(
      const FW_UpdateManifest_t *manifest, uint32_t *session)
  {
    uint32_t status;

    /* Secure SysTick is intentionally suspended while NonSecure owns the CPU.
     * Every updater operation below uses HAL drivers with bounded timeouts, so
     * restore the Secure HAL timebase only for the duration of the NSC call. */
    HAL_ResumeTick();
    status = SecureFirmwareUpdate_Begin(manifest, session);
    HAL_SuspendTick();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateWrite(
      uint32_t session, const uint8_t *data, uint32_t length)
  {
    uint32_t status;

    HAL_ResumeTick();
    status = SecureFirmwareUpdate_Write(session, data, length);
    HAL_SuspendTick();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateFinalize(uint32_t session)
  {
    uint32_t status;

    HAL_ResumeTick();
    status = SecureFirmwareUpdate_Finalize(session);
    HAL_SuspendTick();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateAbort(uint32_t session)
  {
    uint32_t status;

    HAL_ResumeTick();
    status = SecureFirmwareUpdate_Abort(session);
    HAL_SuspendTick();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateConfirmBoot(void)
  {
    uint32_t status;

    HAL_ResumeTick();
    status = SecureFirmwareUpdate_ConfirmBoot();
    HAL_SuspendTick();
    return status;
  }

/**
  * @}
  */

/**
  * @}
  */
/* USER CODE END Non_Secure_CallLib */

