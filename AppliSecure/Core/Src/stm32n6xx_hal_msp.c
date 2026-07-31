/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file         stm32n6xx_hal_msp.c
  * @brief        This file provides code for the MSP Initialization
  *               and de-Initialization codes.
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
#include "main.h"
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN TD */

/* USER CODE END TD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN Define */

/* USER CODE END Define */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN Macro */

/* USER CODE END Macro */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* External functions --------------------------------------------------------*/
/* USER CODE BEGIN ExternalFunctions */

/* USER CODE END ExternalFunctions */

/* USER CODE BEGIN 0 */

/* USER CODE END 0 */
/**
  * Initializes the Global MSP.
  */
void HAL_MspInit(void)
{

  /* USER CODE BEGIN MspInit 0 */

  /* USER CODE END MspInit 0 */

  /* System interrupt init*/

  HAL_PWREx_EnableVddIO2();

  HAL_PWREx_EnableVddIO3();

  HAL_PWREx_EnableVddIO4();

  /* USER CODE BEGIN MspInit 1 */

  /* USER CODE END MspInit 1 */
}

/* USER CODE BEGIN 1 */

void HAL_XSPI_MspInit(XSPI_HandleTypeDef *hxspi)
{
  if ((hxspi != NULL) && (hxspi->Instance == XSPI2))
  {
    /* FSBL already configured the secure GPION pins and IC3 clock.  Re-enable
     * only the peripherals here; reprogramming the shared clock tree while
     * the Non-Secure application is live would be unsafe. */
    __HAL_RCC_XSPIM_CLK_ENABLE();
    __HAL_RCC_XSPI2_CLK_ENABLE();
  }
}

void HAL_XSPI_MspDeInit(XSPI_HandleTypeDef *hxspi)
{
  if ((hxspi != NULL) && (hxspi->Instance == XSPI2))
  {
    __HAL_RCC_XSPI2_CLK_DISABLE();
    __HAL_RCC_XSPIM_CLK_DISABLE();
  }
}

void HAL_PKA_MspInit(PKA_HandleTypeDef *hpka)
{
  if ((hpka != NULL) && (hpka->Instance == PKA))
  {
    __HAL_RCC_PKA_CLK_ENABLE();
  }
}

void HAL_PKA_MspDeInit(PKA_HandleTypeDef *hpka)
{
  if ((hpka != NULL) && (hpka->Instance == PKA))
  {
    __HAL_RCC_PKA_CLK_DISABLE();
  }
}

/* USER CODE END 1 */
