#include "firmware_boot.h"

#include <stdio.h>
#include <string.h>

#include "firmware_crypto.h"
#include "firmware_update_format.h"
#include "stm32_extmem.h"
#include "stm32_extmem_conf.h"

#define NONSECURE_RAM_START (0x24100000UL)
#define NONSECURE_RAM_END   (0x24200000UL)

static uint32_t boot_nonsecure_source = FW_SLOT_A_OFFSET;
static FW_BootRecord_t boot_record_0;
static FW_BootRecord_t boot_record_1;
static FW_BootRecord_t boot_verify_record;
static FW_BootRecord_t boot_work_record;

static void boot_metadata_load(FW_BootRecord_t *record,
                               uint32_t *source_index);
static int32_t boot_metadata_commit(FW_BootRecord_t *record,
                                    uint32_t previous_index);
static int32_t boot_verify_slot_mapped(uint32_t slot,
                                      uint32_t version,
                                      const FW_UpdateManifest_t *manifest);
static uint32_t boot_validate_stm32_image(uint32_t mapped_address,
                                         uint32_t expected_size);
static int32_t boot_map_and_verify(uint32_t slot, uint32_t version,
                                   const FW_UpdateManifest_t *manifest);

static void boot_metadata_load(FW_BootRecord_t *record,
                               uint32_t *source_index)
{
  uint32_t valid_0;
  uint32_t valid_1;

  valid_0 = (EXTMEM_Read(EXTMEMORY_1, FW_METADATA_0_OFFSET,
                         (uint8_t *)&boot_record_0,
                         sizeof(boot_record_0)) == EXTMEM_OK) ?
            FW_BootRecordIsValid(&boot_record_0) : 0U;
  valid_1 = (EXTMEM_Read(EXTMEMORY_1, FW_METADATA_1_OFFSET,
                         (uint8_t *)&boot_record_1,
                         sizeof(boot_record_1)) == EXTMEM_OK) ?
            FW_BootRecordIsValid(&boot_record_1) : 0U;

  if ((valid_0 == 0U) && (valid_1 == 0U))
  {
    FW_BootRecordMakeDefault(record);
    *source_index = UINT32_MAX;
  }
  else if ((valid_1 != 0U) &&
           ((valid_0 == 0U) ||
            (FW_BootRecordIsNewer(boot_record_1.sequence,
                                  boot_record_0.sequence) != 0U)))
  {
    *record = boot_record_1;
    *source_index = 1U;
  }
  else
  {
    *record = boot_record_0;
    *source_index = 0U;
  }
}

static int32_t boot_metadata_commit(FW_BootRecord_t *record,
                                    uint32_t previous_index)
{
  uint32_t target_index = (previous_index == 0U) ? 1U : 0U;
  uint32_t target_offset = (target_index == 0U) ?
                           FW_METADATA_0_OFFSET : FW_METADATA_1_OFFSET;

  FW_BootRecordSeal(record);
  if ((EXTMEM_EraseSector(EXTMEMORY_1, target_offset,
                          FW_METADATA_SECTOR_SIZE) != EXTMEM_OK) ||
      (EXTMEM_Write(EXTMEMORY_1, target_offset, (const uint8_t *)record,
                    sizeof(*record)) != EXTMEM_OK) ||
      (EXTMEM_Read(EXTMEMORY_1, target_offset,
                   (uint8_t *)&boot_verify_record,
                   sizeof(boot_verify_record)) != EXTMEM_OK) ||
      (FW_BootRecordIsValid(&boot_verify_record) == 0U) ||
      (memcmp(record, &boot_verify_record, sizeof(*record)) != 0))
  {
    return -1;
  }
  return 0;
}

static uint32_t boot_validate_stm32_image(uint32_t mapped_address,
                                         uint32_t expected_size)
{
  uint32_t magic = *(const uint32_t *)mapped_address;
  uint32_t signed_size = *(const uint32_t *)(mapped_address +
                                             FW_STM32_IMAGE_SIZE_OFFSET);
  uint32_t msp = *(const uint32_t *)(mapped_address +
                                    FW_STM32_IMAGE_VECTOR_OFFSET);
  uint32_t reset_handler = *(const uint32_t *)(mapped_address +
                                              FW_STM32_IMAGE_VECTOR_OFFSET + 4U);

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

static int32_t boot_verify_slot_mapped(uint32_t slot,
                                      uint32_t version,
                                      const FW_UpdateManifest_t *manifest)
{
  uint32_t slot_offset = FW_SlotOffset(slot);
  uint32_t mapped_address;
  int32_t crypto_result;
  FW_SHA256_Context_t sha;
  uint8_t digest[32];

  if (slot_offset == UINT32_MAX)
  {
    return -1;
  }
  mapped_address = FW_FLASH_BASE_ADDRESS + slot_offset;
  (void)printf("[FSBL] verifying slot %lu/v%lu at 0x%08lX\r\n",
               (unsigned long)slot, (unsigned long)version,
               (unsigned long)mapped_address);

  /* Version zero is the factory/development image that predates the A/B
   * metadata.  It is accepted only in slot A and only after strict STM32
   * header/vector bounds checks. */
  if (version == 0U)
  {
    uint32_t factory_size = *(const uint32_t *)(
        mapped_address + FW_STM32_IMAGE_SIZE_OFFSET);
    if (slot != FW_SLOT_A)
    {
      return -2;
    }
    if (factory_size > (FW_SLOT_SIZE - FW_STM32_IMAGE_PREFIX_SIZE))
    {
      return -3;
    }
    if (boot_validate_stm32_image(
            mapped_address,
            factory_size + FW_STM32_IMAGE_PREFIX_SIZE) == 0U)
    {
      return -3;
    }
    (void)printf("[FSBL] factory image header accepted: %lu bytes\r\n",
                 (unsigned long)(factory_size + FW_STM32_IMAGE_PREFIX_SIZE));
    return 0;
  }

  if ((manifest == NULL) || (manifest->firmware_version != version))
  {
    return -4;
  }

  (void)printf("[FSBL] authenticating pending manifest: image=%lu bytes\r\n",
               (unsigned long)manifest->image_size);
  crypto_result = FW_Crypto_VerifyManifest(manifest);
  (void)printf("[FSBL] manifest signature verification returned %ld\r\n",
               (long)crypto_result);
  if ((crypto_result != 0) ||
      (boot_validate_stm32_image(mapped_address,
                                 manifest->image_size) == 0U))
  {
    return -4;
  }
  (void)printf("[FSBL] signed STM32 image header accepted; hashing candidate\r\n");

  FW_SHA256_Init(&sha);
  FW_SHA256_Update(&sha, (const void *)mapped_address,
                   manifest->image_size);
  FW_SHA256_Final(&sha, digest);
  if (FW_ConstantTimeEqual(digest, manifest->image_sha256,
                           sizeof(digest)) == 0U)
  {
    (void)printf("[FSBL] candidate image hash rejected\r\n");
    return -5;
  }
  (void)printf("[FSBL] candidate image hash accepted\r\n");
  return 0;
}

static int32_t boot_map_and_verify(uint32_t slot, uint32_t version,
                                   const FW_UpdateManifest_t *manifest)
{
  int32_t result;

  if (EXTMEM_MemoryMappedMode(EXTMEMORY_1, EXTMEM_ENABLE) != EXTMEM_OK)
  {
    (void)printf("[FSBL] ERROR: external NOR map enable failed\r\n");
    return -1;
  }
  result = boot_verify_slot_mapped(slot, version, manifest);
  if (EXTMEM_MemoryMappedMode(EXTMEMORY_1, EXTMEM_DISABLE) != EXTMEM_OK)
  {
    (void)printf("[FSBL] ERROR: external NOR map disable failed\r\n");
    return -2;
  }
  (void)printf("[FSBL] slot %lu verification result=%ld\r\n",
               (unsigned long)slot, (long)result);
  return result;
}

int32_t Firmware_Boot_Prepare(void)
{
  FW_BootRecord_t *current = &boot_work_record;
  uint32_t source_index;

  boot_metadata_load(current, &source_index);
  boot_nonsecure_source = FW_SlotOffset(current->confirmed_slot);
  if (boot_nonsecure_source == UINT32_MAX)
  {
    return -1;
  }

  (void)printf("[FSBL] update metadata: seq=%lu state=%lu confirmed=%lu/v%lu "
               "pending=%lu/v%lu\r\n",
               (unsigned long)current->sequence,
               (unsigned long)current->state,
               (unsigned long)current->confirmed_slot,
               (unsigned long)current->confirmed_version,
               (unsigned long)current->pending_slot,
               (unsigned long)current->pending_version);

  if (current->state == FW_BOOT_STATE_TRIAL)
  {
    /* The trial application reset before confirming itself.  The confirmed
     * slot was never overwritten, so rollback is deterministic. */
    current->sequence++;
    current->state = FW_BOOT_STATE_CONFIRMED;
    current->pending_slot = FW_SLOT_NONE;
    current->pending_version = 0U;
    (void)memset(&current->pending_manifest, 0,
                 sizeof(current->pending_manifest));
    if (boot_metadata_commit(current, source_index) != 0)
    {
      return -2;
    }
    (void)printf("[FSBL] unconfirmed trial detected; rolling back to slot %lu\r\n",
                 (unsigned long)current->confirmed_slot);
    return boot_map_and_verify(current->confirmed_slot,
                               current->confirmed_version,
                               &current->confirmed_manifest);
  }

  if (current->state == FW_BOOT_STATE_PENDING)
  {
    if ((current->pending_version <= current->confirmed_version) ||
        (current->pending_manifest.firmware_version !=
         current->pending_version) ||
        (boot_map_and_verify(current->pending_slot,
                             current->pending_version,
                             &current->pending_manifest) != 0))
    {
      current->sequence++;
      current->state = FW_BOOT_STATE_CONFIRMED;
      current->pending_slot = FW_SLOT_NONE;
      current->pending_version = 0U;
      (void)memset(&current->pending_manifest, 0,
                   sizeof(current->pending_manifest));
      if (boot_metadata_commit(current, source_index) != 0)
      {
        return -3;
      }
      (void)printf("[FSBL] rejected pending firmware; using confirmed slot %lu\r\n",
                   (unsigned long)current->confirmed_slot);
      return boot_map_and_verify(current->confirmed_slot,
                                 current->confirmed_version,
                                 &current->confirmed_manifest);
    }

    current->sequence++;
    current->state = FW_BOOT_STATE_TRIAL;
    if (boot_metadata_commit(current, source_index) != 0)
    {
      return -4;
    }
    boot_nonsecure_source = FW_SlotOffset(current->pending_slot);
    (void)printf("[FSBL] authenticated firmware v%lu; trial boot from slot %lu\r\n",
                 (unsigned long)current->pending_version,
                 (unsigned long)current->pending_slot);
    return 0;
  }

  if (boot_map_and_verify(current->confirmed_slot,
                          current->confirmed_version,
                          &current->confirmed_manifest) == 0)
  {
    return 0;
  }

  /* After a successful update confirmation, pending_* retains the previous
   * confirmed image as an emergency fallback. */
  if (((current->pending_slot == FW_SLOT_A) ||
       (current->pending_slot == FW_SLOT_B)) &&
      (boot_map_and_verify(current->pending_slot,
                           current->pending_version,
                           &current->pending_manifest) == 0))
  {
    uint32_t failed_slot = current->confirmed_slot;
    current->sequence++;
    current->confirmed_slot = current->pending_slot;
    current->confirmed_version = current->pending_version;
    current->confirmed_manifest = current->pending_manifest;
    current->pending_slot = FW_SLOT_NONE;
    current->pending_version = 0U;
    (void)memset(&current->pending_manifest, 0,
                 sizeof(current->pending_manifest));
    if (boot_metadata_commit(current, source_index) != 0)
    {
      return -5;
    }
    boot_nonsecure_source = FW_SlotOffset(current->confirmed_slot);
    (void)printf("[FSBL] confirmed slot %lu failed authentication; "
                 "recovered slot %lu\r\n",
                 (unsigned long)failed_slot,
                 (unsigned long)current->confirmed_slot);
    return 0;
  }

  return -6;
}

uint32_t Firmware_Boot_GetNonSecureSourceOffset(void)
{
  return boot_nonsecure_source;
}
