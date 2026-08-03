/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           :  extmem.c
  * @version        : 1.0.0
  * @brief          : This file implements the external memory manager
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
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
#include "extmem.h"
#include "stm32_boot_lrun.h"

/* USER CODE BEGIN Includes */

#include <stdio.h>
#include "firmware_boot.h"

/* USER CODE END Includes */

/* USER CODE BEGIN PV */
/* Private variables ---------------------------------------------------------*/

/* STM32 image header v2.3: the signed area size is stored at byte offset 108.
 * The file starts 0x240 bytes before that signed area.  The vector table is
 * aligned independently at offset 0x400 and is already included in img_size. */
#define HEADER_V2_3_IMG_SIZE_OFFSET 108U
#define HEADER_V2_3_FILE_PREFIX_SIZE 0x240U

/* USER CODE END PV */

/* USER CODE BEGIN PFP */
/* Private function prototypes -----------------------------------------------*/

/* USER CODE END PFP */

/*
 * -- Insert your variables declaration here --
 */
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/*
 * -- Insert your external function declaration here --
 */
/* USER CODE BEGIN 1 */

/* USER CODE END 1 */

/**
  * Init Secure Manager API
  * @retval None
  */
void MX_EXTMEM_Init(void)
{

  /* USER CODE BEGIN MX_EXTMEM_Init_PreTreatment */
    
  /* USER CODE END MX_EXTMEM_Init_PreTreatment */

  EXTMEM_Init(EXTMEMORY_1, HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_XSPI2));
//  EXTMEM_Init(EXTMEMORY_2, HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_XSPI1));

  /* USER CODE BEGIN MX_EXTMEM_Init_PostTreatment */

  /* USER CODE END MX_EXTMEM_Init_PostTreatment */
}

/**
  * @brief Return the complete signed image size (header and payload).
  * @param img_addr Memory-mapped address of the signed image header.
  * @retval Number of bytes to copy into internal RAM.
  */
uint32_t BOOT_GetApplicationSize(uint32_t img_addr)
{
  uint32_t img_size;

  img_size = *(const uint32_t *)(img_addr + HEADER_V2_3_IMG_SIZE_OFFSET);
  (void)printf("[FSBL] image @ 0x%08lX: magic=0x%08lX, signed-size=0x%08lX, "
               "vectors=0x%08lX/0x%08lX\r\n",
               (unsigned long)img_addr,
               (unsigned long)*(const uint32_t *)img_addr,
               (unsigned long)img_size,
               (unsigned long)*(const uint32_t *)(img_addr + EXTMEM_HEADER_OFFSET),
               (unsigned long)*(const uint32_t *)(img_addr + EXTMEM_HEADER_OFFSET + 4U));
  return img_size + HEADER_V2_3_FILE_PREFIX_SIZE;
}

uint32_t BOOT_GetApplicationSourceAddressNS(void)
{
  return Firmware_Boot_GetNonSecureSourceOffset();
}

BOOTStatus_TypeDef BOOT_PrepareApplicationJump(void)
{
  if (EXTMEM_MemoryMappedMode(EXTMEMORY_1, EXTMEM_DISABLE) != EXTMEM_OK)
  {
    (void)printf("[FSBL] ERROR: failed to leave external NOR memory-mapped mode\r\n");
    return BOOT_ERROR_MAPPEDMODEFAIL;
  }

  (void)printf("[FSBL] external NOR unmapped for Secure update service\r\n");
  return BOOT_OK;
}

