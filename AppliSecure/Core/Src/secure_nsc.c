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

/* A12 was signed against the former movable veneers at3400FF40. Preserve that
 * exact seven-entry ABI while fixing the canonical ABI at the installed B11
 * addresses3400F600. Both paths SG into the SAME CMSE-sanitized implementation;
 * no additional Secure service or permission is introduced. Keep this in the
 * existing translation unit so generated CubeIDE makefiles cannot omit it. */
#if defined(__GNUC__)
#define A12_COMPAT_GATE(name, target) \
  ".global a12_compat_" #name "\n" \
  ".type a12_compat_" #name ",%function\n" \
  ".thumb_func\n" \
  "a12_compat_" #name ":\n" \
  "sg\n" \
  "b.w " #target "\n" \
  ".size a12_compat_" #name ",.-a12_compat_" #name "\n"
__asm__(
  ".pushsection .nsc_a12_compat,\"ax\",%progbits\n"
  ".balign 32\n"
  A12_COMPAT_GATE(SECURE_FirmwareUpdateConfirmBoot, __acle_se_SECURE_FirmwareUpdateConfirmBoot)
  A12_COMPAT_GATE(SECURE_FirmwareUpdateWrite, __acle_se_SECURE_FirmwareUpdateWrite)
  /* Refer to an ordinary alias defined in the clock implementation's own
   * translation unit. GNU ld CMSE scanning otherwise processes its special
   * __acle_se_ symbol twice (definition + cross-object reference), PR-style
   * duplicate-stub assertion in binutils2.44 cmse_scan. */
  A12_COMPAT_GATE(SECURE_SystemCoreClockUpdate, a12_clock_cmse_target)
  A12_COMPAT_GATE(SECURE_FirmwareUpdateBegin, __acle_se_SECURE_FirmwareUpdateBegin)
  A12_COMPAT_GATE(SECURE_FirmwareUpdateFinalize, __acle_se_SECURE_FirmwareUpdateFinalize)
  A12_COMPAT_GATE(SECURE_FirmwareUpdateAbort, __acle_se_SECURE_FirmwareUpdateAbort)
  A12_COMPAT_GATE(SECURE_RegisterCallback, __acle_se_SECURE_RegisterCallback)
  ".balign 32,0\n"
  ".popsection\n"
);
#undef A12_COMPAT_GATE
#endif
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
     * the flash gate owns the Secure timebase until executable mapping returns. */
    status = SecureFirmwareUpdate_EnterFlash();
    if (status != SECURE_FW_UPDATE_OK) return status;
    status = SecureFirmwareUpdate_Begin(manifest, session);
    SecureFirmwareUpdate_LeaveFlash();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateWrite(
      uint32_t session, const uint8_t *data, uint32_t length)
  {
    uint32_t status;

    status = SecureFirmwareUpdate_EnterFlash();
    if (status != SECURE_FW_UPDATE_OK) return status;
    status = SecureFirmwareUpdate_Write(session, data, length);
    SecureFirmwareUpdate_LeaveFlash();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateFinalize(uint32_t session)
  {
    uint32_t status;

    status = SecureFirmwareUpdate_EnterFlash();
    if (status != SECURE_FW_UPDATE_OK) return status;
    status = SecureFirmwareUpdate_Finalize(session);
    SecureFirmwareUpdate_LeaveFlash();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateAbort(uint32_t session)
  {
    uint32_t status;

    status = SecureFirmwareUpdate_EnterFlash();
    if (status != SECURE_FW_UPDATE_OK) return status;
    status = SecureFirmwareUpdate_Abort(session);
    SecureFirmwareUpdate_LeaveFlash();
    return status;
  }

  CMSE_NS_ENTRY uint32_t SECURE_FirmwareUpdateConfirmBoot(void)
  {
    uint32_t status;

    status = SecureFirmwareUpdate_EnterFlash();
    if (status != SECURE_FW_UPDATE_OK) return status;
    status = SecureFirmwareUpdate_ConfirmBoot();
    SecureFirmwareUpdate_LeaveFlash();
    return status;
  }

/**
  * @}
  */

/**
  * @}
  */
/* USER CODE END Non_Secure_CallLib */

