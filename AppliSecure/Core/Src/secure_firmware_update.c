#include "secure_firmware_update.h"

#include <arm_cmse.h>
#include <string.h>

#include "firmware_crypto.h"
#include "main.h"
#include "secure_nsc.h"
#include "stm32_extmem.h"
#include "stm32_extmem_conf.h"

#define SECURE_UPDATE_CHUNK_MAX        (1024U)
#define SECURE_UPDATE_ERASE_SIZE       (FW_METADATA_SECTOR_SIZE)
#define NONSECURE_RAM_START            (0x24100000UL)
#define NONSECURE_RAM_END              (0x24200000UL)

typedef struct
{
  uint32_t active;
  uint32_t session;
  uint32_t starting_sequence;
  uint32_t target_slot;
  uint32_t bytes_erased;
  uint32_t bytes_written;
  FW_UpdateManifest_t manifest;
  FW_SHA256_Context_t sha256;
} SecureFirmwareUpdateContext_t;

XSPI_HandleTypeDef hxspi2;

static SecureFirmwareUpdateContext_t secure_update;
static uint32_t secure_update_next_session;
static uint32_t secure_flash_ready;
static uint8_t secure_flash_buffer[SECURE_UPDATE_CHUNK_MAX];
static FW_BootRecord_t secure_record_0;
static FW_BootRecord_t secure_record_1;
static FW_BootRecord_t secure_verify_record;
static FW_BootRecord_t secure_work_record;

static int32_t secure_flash_initialize(void);
static uint32_t secure_metadata_load(FW_BootRecord_t *record,
                                     uint32_t *source_index);
static uint32_t secure_metadata_commit(FW_BootRecord_t *record,
                                       uint32_t previous_index);
static uint32_t secure_validate_stm32_image(uint32_t slot_offset,
                                           uint32_t expected_size);
static void secure_update_clear(void);

static int32_t secure_flash_initialize(void)
{
  XSPIM_CfgTypeDef manager = {0};

  (void)memset(&hxspi2, 0, sizeof(hxspi2));
  hxspi2.Instance = XSPI2;
  hxspi2.Init.FifoThresholdByte = 4U;
  hxspi2.Init.MemoryMode = HAL_XSPI_SINGLE_MEM;
  hxspi2.Init.MemoryType = HAL_XSPI_MEMTYPE_MACRONIX;
  hxspi2.Init.MemorySize = HAL_XSPI_SIZE_512MB;
  hxspi2.Init.ChipSelectHighTimeCycle = 2U;
  hxspi2.Init.FreeRunningClock = HAL_XSPI_FREERUNCLK_DISABLE;
  hxspi2.Init.ClockMode = HAL_XSPI_CLOCK_MODE_0;
  hxspi2.Init.WrapSize = HAL_XSPI_WRAP_NOT_SUPPORTED;
  hxspi2.Init.ClockPrescaler = 0U;
  hxspi2.Init.SampleShifting = HAL_XSPI_SAMPLE_SHIFT_NONE;
  hxspi2.Init.DelayHoldQuarterCycle = HAL_XSPI_DHQC_ENABLE;
  hxspi2.Init.ChipSelectBoundary = HAL_XSPI_BONDARYOF_NONE;
  hxspi2.Init.MaxTran = 0U;
  hxspi2.Init.Refresh = 0U;
  hxspi2.Init.MemorySelect = HAL_XSPI_CSSEL_NCS1;

  if (HAL_XSPI_Init(&hxspi2) != HAL_OK)
  {
    return SECURE_FW_INIT_ERROR_XSPI;
  }

  manager.nCSOverride = HAL_XSPI_CSSEL_OVR_NCS1;
  manager.IOPort = HAL_XSPIM_IOPORT_2;
  manager.Req2AckTime = 1U;
  if (HAL_XSPIM_Config(&hxspi2, &manager,
                       HAL_XSPI_TIMEOUT_DEFAULT_VALUE) != HAL_OK)
  {
    return SECURE_FW_INIT_ERROR_XSPIM;
  }

  if (EXTMEM_Init(EXTMEMORY_1,
                  HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_XSPI2)) != EXTMEM_OK)
  {
    return SECURE_FW_INIT_ERROR_EXTMEM;
  }
  return 0;
}

int32_t SecureFirmwareUpdate_Init(void)
{
  int32_t crypto_status;
  int32_t flash_status;

  secure_update_clear();
  flash_status = secure_flash_initialize();
  if (flash_status != SECURE_FW_INIT_OK)
  {
    secure_flash_ready = 0U;
    return flash_status;
  }
  crypto_status = FW_Crypto_Init();
  if (crypto_status != FW_CRYPTO_INIT_OK)
  {
    secure_flash_ready = 0U;
    return (crypto_status == FW_CRYPTO_INIT_ERROR_RNG) ?
           SECURE_FW_INIT_ERROR_RNG : SECURE_FW_INIT_ERROR_PKA;
  }
  secure_flash_ready = 1U;
  return SECURE_FW_INIT_OK;
}

static uint32_t secure_metadata_load(FW_BootRecord_t *record,
                                     uint32_t *source_index)
{
  uint32_t valid_0;
  uint32_t valid_1;

  if ((record == NULL) || (source_index == NULL) ||
      (secure_flash_ready == 0U))
  {
    return SECURE_FW_UPDATE_ERROR_UNAVAILABLE;
  }

  valid_0 = (EXTMEM_Read(EXTMEMORY_1, FW_METADATA_0_OFFSET,
                         (uint8_t *)&secure_record_0,
                         sizeof(secure_record_0)) == EXTMEM_OK) ?
            FW_BootRecordIsValid(&secure_record_0) : 0U;
  valid_1 = (EXTMEM_Read(EXTMEMORY_1, FW_METADATA_1_OFFSET,
                         (uint8_t *)&secure_record_1,
                         sizeof(secure_record_1)) == EXTMEM_OK) ?
            FW_BootRecordIsValid(&secure_record_1) : 0U;

  if ((valid_0 == 0U) && (valid_1 == 0U))
  {
    FW_BootRecordMakeDefault(record);
    *source_index = UINT32_MAX;
  }
  else if ((valid_1 != 0U) &&
           ((valid_0 == 0U) ||
            (FW_BootRecordIsNewer(secure_record_1.sequence,
                                  secure_record_0.sequence) != 0U)))
  {
    *record = secure_record_1;
    *source_index = 1U;
  }
  else
  {
    *record = secure_record_0;
    *source_index = 0U;
  }
  return SECURE_FW_UPDATE_OK;
}

static uint32_t secure_metadata_commit(FW_BootRecord_t *record,
                                       uint32_t previous_index)
{
  uint32_t target_index = (previous_index == 0U) ? 1U : 0U;
  uint32_t target_offset = (target_index == 0U) ?
                           FW_METADATA_0_OFFSET : FW_METADATA_1_OFFSET;

  if ((record == NULL) || (secure_flash_ready == 0U))
  {
    return SECURE_FW_UPDATE_ERROR_UNAVAILABLE;
  }

  FW_BootRecordSeal(record);
  if ((EXTMEM_EraseSector(EXTMEMORY_1, target_offset,
                          FW_METADATA_SECTOR_SIZE) != EXTMEM_OK) ||
      (EXTMEM_Write(EXTMEMORY_1, target_offset, (const uint8_t *)record,
                    sizeof(*record)) != EXTMEM_OK) ||
      (EXTMEM_Read(EXTMEMORY_1, target_offset,
                   (uint8_t *)&secure_verify_record,
                   sizeof(secure_verify_record)) != EXTMEM_OK) ||
      (FW_BootRecordIsValid(&secure_verify_record) == 0U) ||
      (memcmp(record, &secure_verify_record, sizeof(*record)) != 0))
  {
    return SECURE_FW_UPDATE_ERROR_FLASH;
  }
  return SECURE_FW_UPDATE_OK;
}

uint32_t SecureFirmwareUpdate_Begin(const FW_UpdateManifest_t *manifest_ns,
                                    uint32_t *session_ns)
{
  FW_BootRecord_t *current = &secure_work_record;
  FW_UpdateManifest_t manifest;
  int32_t crypto_status;
  uint32_t source_index;

  Secure_Trace("[SECURE-UPDATE] Begin entered\r\n");
  Secure_TraceHex("[SECURE-UPDATE] HAL tick = ", HAL_GetTick());

  if ((manifest_ns == NULL) || (session_ns == NULL) ||
      (secure_flash_ready == 0U) || (secure_update.active != 0U))
  {
    Secure_Trace("[SECURE-UPDATE] Begin rejected by entry state check\r\n");
    return (secure_flash_ready == 0U) ?
           SECURE_FW_UPDATE_ERROR_UNAVAILABLE :
           SECURE_FW_UPDATE_ERROR_STATE;
  }
  if ((cmse_check_address_range((void *)manifest_ns, sizeof(manifest),
                                CMSE_NONSECURE | CMSE_MPU_READ) == NULL) ||
      (cmse_check_address_range((void *)session_ns, sizeof(*session_ns),
                                CMSE_NONSECURE | CMSE_MPU_READWRITE) == NULL))
  {
    Secure_Trace("[SECURE-UPDATE] Begin rejected by CMSE range check\r\n");
    return SECURE_FW_UPDATE_ERROR_PARAMETER;
  }

  Secure_Trace("[SECURE-UPDATE] CMSE ranges accepted; copying manifest\r\n");
  (void)memcpy(&manifest, manifest_ns, sizeof(manifest));
  Secure_TraceHex("[SECURE-UPDATE] manifest magic = ", manifest.magic);
  Secure_TraceHex("[SECURE-UPDATE] manifest version = ",
                  manifest.firmware_version);
  Secure_TraceHex("[SECURE-UPDATE] image size = ", manifest.image_size);
  if (FW_ManifestIsWellFormed(&manifest) == 0U)
  {
    Secure_Trace("[SECURE-UPDATE] manifest structure invalid\r\n");
    return SECURE_FW_UPDATE_ERROR_AUTHENTICATION;
  }
  Secure_Trace("[SECURE-UPDATE] manifest structure valid; hashing and starting PKA ECDSA verify\r\n");
  Secure_TraceHex("[SECURE-UPDATE] PKA CR before verify = ", PKA->CR);
  Secure_TraceHex("[SECURE-UPDATE] PKA SR before verify = ", PKA->SR);
  Secure_TraceHex("[SECURE-UPDATE] RNG CR before verify = ", RNG->CR);
  Secure_TraceHex("[SECURE-UPDATE] RNG SR before verify = ", RNG->SR);
  crypto_status = FW_Crypto_VerifyManifest(&manifest);
  Secure_TraceHex("[SECURE-UPDATE] crypto verify returned = ",
                  (uint32_t)crypto_status);
  Secure_TraceHex("[SECURE-UPDATE] PKA CR after verify = ", PKA->CR);
  Secure_TraceHex("[SECURE-UPDATE] PKA SR after verify = ", PKA->SR);
  if (crypto_status != 0)
  {
    Secure_Trace("[SECURE-UPDATE] signature authentication failed\r\n");
    return SECURE_FW_UPDATE_ERROR_AUTHENTICATION;
  }
  Secure_Trace("[SECURE-UPDATE] signature accepted; loading boot metadata\r\n");
  if (secure_metadata_load(current, &source_index) != SECURE_FW_UPDATE_OK)
  {
    Secure_Trace("[SECURE-UPDATE] boot metadata read failed\r\n");
    return SECURE_FW_UPDATE_ERROR_FLASH;
  }
  if (current->state != FW_BOOT_STATE_CONFIRMED)
  {
    Secure_TraceHex("[SECURE-UPDATE] boot state is not confirmed: ",
                    current->state);
    return SECURE_FW_UPDATE_ERROR_STATE;
  }
  if (manifest.firmware_version <= current->confirmed_version)
  {
    Secure_TraceHex("[SECURE-UPDATE] confirmed version = ",
                    current->confirmed_version);
    return SECURE_FW_UPDATE_ERROR_VERSION;
  }

  secure_update.target_slot = (current->confirmed_slot == FW_SLOT_A) ?
                              FW_SLOT_B : FW_SLOT_A;
  if (FW_SlotOffset(secure_update.target_slot) == UINT32_MAX)
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_PARAMETER;
  }

  secure_update_next_session++;
  if (secure_update_next_session == 0U)
  {
    secure_update_next_session = 1U;
  }
  secure_update.active = 1U;
  secure_update.session = secure_update_next_session;
  secure_update.starting_sequence = current->sequence;
  secure_update.bytes_erased = 0U;
  secure_update.bytes_written = 0U;
  secure_update.manifest = manifest;
  FW_SHA256_Init(&secure_update.sha256);
  *session_ns = secure_update.session;
  Secure_TraceHex("[SECURE-UPDATE] Begin accepted; session = ",
                  secure_update.session);
  return SECURE_FW_UPDATE_OK;
}

uint32_t SecureFirmwareUpdate_Write(uint32_t session,
                                    const uint8_t *data_ns,
                                    uint32_t length)
{
  uint32_t slot_offset;
  uint32_t written = 0U;

  if ((secure_update.active == 0U) ||
      (session != secure_update.session))
  {
    return SECURE_FW_UPDATE_ERROR_STATE;
  }
  if ((data_ns == NULL) || (length == 0U) ||
      (length > SECURE_UPDATE_CHUNK_MAX) ||
      (length > (secure_update.manifest.image_size -
                 secure_update.bytes_written)) ||
      (cmse_check_address_range((void *)data_ns, length,
                                CMSE_NONSECURE | CMSE_MPU_READ) == NULL))
  {
    return SECURE_FW_UPDATE_ERROR_PARAMETER;
  }

  (void)memcpy(secure_flash_buffer, data_ns, length);
  slot_offset = FW_SlotOffset(secure_update.target_slot);
  while (written < length)
  {
    uint32_t image_offset = secure_update.bytes_written + written;
    uint32_t writable;
    uint32_t chunk;

    if (image_offset == secure_update.bytes_erased)
    {
      if ((secure_update.bytes_erased >= FW_SLOT_SIZE) ||
          (EXTMEM_EraseSector(EXTMEMORY_1,
                              slot_offset + secure_update.bytes_erased,
                              SECURE_UPDATE_ERASE_SIZE) != EXTMEM_OK))
      {
        secure_update_clear();
        return SECURE_FW_UPDATE_ERROR_FLASH;
      }
      secure_update.bytes_erased += SECURE_UPDATE_ERASE_SIZE;
    }

    writable = secure_update.bytes_erased - image_offset;
    chunk = ((length - written) < writable) ?
            (length - written) : writable;
    if (EXTMEM_Write(EXTMEMORY_1, slot_offset + image_offset,
                     &secure_flash_buffer[written], chunk) != EXTMEM_OK)
    {
      secure_update_clear();
      return SECURE_FW_UPDATE_ERROR_FLASH;
    }
    written += chunk;
  }
  FW_SHA256_Update(&secure_update.sha256, secure_flash_buffer, length);
  secure_update.bytes_written += length;
  (void)memset(secure_flash_buffer, 0, length);
  return SECURE_FW_UPDATE_OK;
}

static uint32_t secure_validate_stm32_image(uint32_t slot_offset,
                                           uint32_t expected_size)
{
  uint32_t magic;
  uint32_t signed_size;
  uint32_t msp;
  uint32_t reset_handler;

  if ((EXTMEM_Read(EXTMEMORY_1, slot_offset, (uint8_t *)&magic,
                   sizeof(magic)) != EXTMEM_OK) ||
      (EXTMEM_Read(EXTMEMORY_1, slot_offset + FW_STM32_IMAGE_SIZE_OFFSET,
                   (uint8_t *)&signed_size, sizeof(signed_size)) != EXTMEM_OK) ||
      (EXTMEM_Read(EXTMEMORY_1, slot_offset + FW_STM32_IMAGE_VECTOR_OFFSET,
                   (uint8_t *)&msp, sizeof(msp)) != EXTMEM_OK) ||
      (EXTMEM_Read(EXTMEMORY_1,
                   slot_offset + FW_STM32_IMAGE_VECTOR_OFFSET + 4U,
                   (uint8_t *)&reset_handler,
                   sizeof(reset_handler)) != EXTMEM_OK))
  {
    return 0U;
  }

  if ((magic != FW_STM32_IMAGE_MAGIC) ||
      (expected_size < FW_STM32_IMAGE_PREFIX_SIZE) ||
      (expected_size > FW_SLOT_SIZE) ||
      (signed_size > (FW_SLOT_SIZE - FW_STM32_IMAGE_PREFIX_SIZE)) ||
      (signed_size != (expected_size - FW_STM32_IMAGE_PREFIX_SIZE)) ||
      (msp <= NONSECURE_RAM_START) || (msp > NONSECURE_RAM_END) ||
      ((msp & 0x7U) != 0U) || ((reset_handler & 1U) == 0U) ||
      ((reset_handler & ~1UL) < NONSECURE_RAM_START) ||
      ((reset_handler & ~1UL) >= NONSECURE_RAM_END))
  {
    return 0U;
  }
  return 1U;
}

uint32_t SecureFirmwareUpdate_Finalize(uint32_t session)
{
  FW_SHA256_Context_t readback_sha;
  FW_BootRecord_t *current = &secure_work_record;
  uint8_t stream_digest[32];
  uint8_t readback_digest[32];
  uint32_t source_index;
  uint32_t slot_offset;
  uint32_t remaining;
  uint32_t address;

  if ((secure_update.active == 0U) ||
      (session != secure_update.session))
  {
    return SECURE_FW_UPDATE_ERROR_STATE;
  }
  if (secure_update.bytes_written != secure_update.manifest.image_size)
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_SIZE;
  }

  FW_SHA256_Final(&secure_update.sha256, stream_digest);
  if (FW_ConstantTimeEqual(stream_digest,
                           secure_update.manifest.image_sha256,
                           sizeof(stream_digest)) == 0U)
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_VERIFY;
  }

  slot_offset = FW_SlotOffset(secure_update.target_slot);
  FW_SHA256_Init(&readback_sha);
  remaining = secure_update.manifest.image_size;
  address = slot_offset;
  while (remaining != 0U)
  {
    uint32_t chunk = (remaining < sizeof(secure_flash_buffer)) ?
                     remaining : sizeof(secure_flash_buffer);
    if (EXTMEM_Read(EXTMEMORY_1, address, secure_flash_buffer,
                    chunk) != EXTMEM_OK)
    {
      secure_update_clear();
      return SECURE_FW_UPDATE_ERROR_FLASH;
    }
    FW_SHA256_Update(&readback_sha, secure_flash_buffer, chunk);
    address += chunk;
    remaining -= chunk;
  }
  FW_SHA256_Final(&readback_sha, readback_digest);
  if ((FW_ConstantTimeEqual(readback_digest,
                            secure_update.manifest.image_sha256,
                            sizeof(readback_digest)) == 0U) ||
      (secure_validate_stm32_image(slot_offset,
                                   secure_update.manifest.image_size) == 0U) ||
      (FW_Crypto_VerifyManifest(&secure_update.manifest) != 0))
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_VERIFY;
  }

  if ((secure_metadata_load(current, &source_index) !=
       SECURE_FW_UPDATE_OK) ||
      (current->state != FW_BOOT_STATE_CONFIRMED) ||
      (current->sequence != secure_update.starting_sequence) ||
      (secure_update.manifest.firmware_version <=
       current->confirmed_version))
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_STATE;
  }

  current->sequence++;
  current->state = FW_BOOT_STATE_PENDING;
  current->pending_slot = secure_update.target_slot;
  current->pending_version = secure_update.manifest.firmware_version;
  current->pending_manifest = secure_update.manifest;
  if (secure_metadata_commit(current, source_index) !=
      SECURE_FW_UPDATE_OK)
  {
    secure_update_clear();
    return SECURE_FW_UPDATE_ERROR_FLASH;
  }

  secure_update_clear();
  return SECURE_FW_UPDATE_OK;
}

uint32_t SecureFirmwareUpdate_Abort(uint32_t session)
{
  if (secure_update.active == 0U)
  {
    return SECURE_FW_UPDATE_OK;
  }
  if (session != secure_update.session)
  {
    return SECURE_FW_UPDATE_ERROR_STATE;
  }
  secure_update_clear();
  return SECURE_FW_UPDATE_OK;
}

uint32_t SecureFirmwareUpdate_ConfirmBoot(void)
{
  FW_BootRecord_t *current = &secure_work_record;
  FW_UpdateManifest_t previous_manifest;
  uint32_t source_index;
  uint32_t previous_slot;
  uint32_t previous_version;

  if (secure_flash_ready == 0U)
  {
    return SECURE_FW_UPDATE_ERROR_UNAVAILABLE;
  }
  if (secure_metadata_load(current, &source_index) != SECURE_FW_UPDATE_OK)
  {
    return SECURE_FW_UPDATE_ERROR_FLASH;
  }
  if (current->state == FW_BOOT_STATE_CONFIRMED)
  {
    return SECURE_FW_UPDATE_OK;
  }
  if (current->state != FW_BOOT_STATE_TRIAL)
  {
    return SECURE_FW_UPDATE_ERROR_STATE;
  }

  previous_slot = current->confirmed_slot;
  previous_version = current->confirmed_version;
  previous_manifest = current->confirmed_manifest;
  current->sequence++;
  current->state = FW_BOOT_STATE_CONFIRMED;
  current->confirmed_slot = current->pending_slot;
  current->confirmed_version = current->pending_version;
  current->confirmed_manifest = current->pending_manifest;
  current->pending_slot = previous_slot;
  current->pending_version = previous_version;
  current->pending_manifest = previous_manifest;
  return secure_metadata_commit(current, source_index);
}

static void secure_update_clear(void)
{
  (void)memset(&secure_update, 0, sizeof(secure_update));
  (void)memset(secure_flash_buffer, 0, sizeof(secure_flash_buffer));
}
