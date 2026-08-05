#include "firmware_update_format.h"

#include <string.h>

uint32_t FW_CRC32(const void *data, size_t length)
{
  const uint8_t *bytes = (const uint8_t *)data;
  uint32_t crc = 0xFFFFFFFFUL;

  if ((data == NULL) && (length != 0U))
  {
    return 0U;
  }

  while (length-- != 0U)
  {
    crc ^= *bytes++;
    for (uint32_t bit = 0U; bit < 8U; ++bit)
    {
      uint32_t mask = (uint32_t)(-(int32_t)(crc & 1UL));
      crc = (crc >> 1U) ^ (0xEDB88320UL & mask);
    }
  }
  return ~crc;
}

uint32_t FW_ManifestIsWellFormed(const FW_UpdateManifest_t *manifest)
{
  uint64_t encoded_size;

  if ((manifest == NULL) ||
      (manifest->magic != FW_UPDATE_MANIFEST_MAGIC) ||
      (manifest->format_version != FW_UPDATE_MANIFEST_VERSION) ||
      (manifest->header_size != FW_UPDATE_MANIFEST_SIZE) ||
      (manifest->target_id != FW_UPDATE_TARGET_STM32N657) ||
      (manifest->image_type != FW_UPDATE_IMAGE_NONSECURE) ||
      (manifest->flags != 0U) ||
      (manifest->firmware_version == 0U))
  {
    return 0U;
  }

  encoded_size = (uint64_t)manifest->image_size;
  if ((encoded_size < (uint64_t)(FW_STM32_IMAGE_VECTOR_OFFSET + 8U)) ||
      (encoded_size > (uint64_t)FW_SLOT_SIZE))
  {
    return 0U;
  }
  return 1U;
}

uint32_t FW_BootRecordIsValid(const FW_BootRecord_t *record)
{
  uint32_t expected_crc;

  if ((record == NULL) || (record->magic != FW_BOOT_RECORD_MAGIC) ||
      (record->format_version != FW_BOOT_RECORD_VERSION) ||
      ((record->state != FW_BOOT_STATE_CONFIRMED) &&
       (record->state != FW_BOOT_STATE_PENDING) &&
       (record->state != FW_BOOT_STATE_TRIAL)) ||
      ((record->confirmed_slot != FW_SLOT_A) &&
       (record->confirmed_slot != FW_SLOT_B)))
  {
    return 0U;
  }

  if ((record->state != FW_BOOT_STATE_CONFIRMED) &&
      ((record->pending_slot != FW_SLOT_A) &&
       (record->pending_slot != FW_SLOT_B)))
  {
    return 0U;
  }

  expected_crc = FW_CRC32(record, offsetof(FW_BootRecord_t, crc32));
  return (expected_crc == record->crc32) ? 1U : 0U;
}

uint32_t FW_BootRecordIsNewer(uint32_t left_sequence,
                              uint32_t right_sequence)
{
  return (((int32_t)(left_sequence - right_sequence)) > 0) ? 1U : 0U;
}

uint32_t FW_SlotOffset(uint32_t slot)
{
  if (slot == FW_SLOT_A)
  {
    return FW_SLOT_A_OFFSET;
  }
  if (slot == FW_SLOT_B)
  {
    return FW_SLOT_B_OFFSET;
  }
  return UINT32_MAX;
}

void FW_BootRecordMakeDefault(FW_BootRecord_t *record)
{
  if (record == NULL)
  {
    return;
  }

  (void)memset(record, 0, sizeof(*record));
  record->magic = FW_BOOT_RECORD_MAGIC;
  record->format_version = FW_BOOT_RECORD_VERSION;
  record->sequence = 0U;
  record->state = FW_BOOT_STATE_CONFIRMED;
  record->confirmed_slot = FW_SLOT_A;
  record->confirmed_version = 0U;
  record->pending_slot = FW_SLOT_NONE;
  record->pending_version = 0U;
  FW_BootRecordSeal(record);
}

void FW_BootRecordSeal(FW_BootRecord_t *record)
{
  if (record != NULL)
  {
    record->crc32 = FW_CRC32(record, offsetof(FW_BootRecord_t, crc32));
  }
}
