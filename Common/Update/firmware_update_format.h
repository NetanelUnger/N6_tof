#ifndef FIRMWARE_UPDATE_FORMAT_H
#define FIRMWARE_UPDATE_FORMAT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The board carries a 64 MiB MX25UM51245G mapped at 0x70000000.  The boot
 * chain remains fixed; only the Non-Secure application is updated in place. */
#define FW_FLASH_BASE_ADDRESS             (0x70000000UL)
#define FW_SLOT_A_OFFSET                  (0x00180000UL)
#define FW_SLOT_B_OFFSET                  (0x00280000UL)
#define FW_SLOT_SIZE                      (0x00100000UL)
#define FW_METADATA_0_OFFSET              (0x003E0000UL)
#define FW_METADATA_1_OFFSET              (0x003F0000UL)
#define FW_METADATA_SECTOR_SIZE           (0x00010000UL)

#define FW_UPDATE_MANIFEST_MAGIC          (0x5055364EUL) /* "N6UP" */
#define FW_UPDATE_MANIFEST_VERSION        (1U)
#define FW_UPDATE_TARGET_STM32N657        (0x4E363537UL)
#define FW_UPDATE_IMAGE_NONSECURE         (1UL)
#define FW_UPDATE_MANIFEST_SIZE           (256U)

#define FW_BOOT_RECORD_MAGIC              (0x5242364EUL) /* "N6BR" */
#define FW_BOOT_RECORD_VERSION            (1UL)
#define FW_BOOT_RECORD_SIZE               (1024U)

#define FW_SLOT_A                         (0UL)
#define FW_SLOT_B                         (1UL)
#define FW_SLOT_NONE                      (0xFFFFFFFFUL)

#define FW_BOOT_STATE_CONFIRMED            (1UL)
#define FW_BOOT_STATE_PENDING              (2UL)
#define FW_BOOT_STATE_TRIAL                (3UL)

#define FW_STM32_IMAGE_MAGIC               (0x324D5453UL) /* "STM2" */
#define FW_STM32_IMAGE_SIZE_OFFSET         (108U)
#define FW_STM32_IMAGE_PREFIX_SIZE         (0x240U)
#define FW_STM32_IMAGE_VECTOR_OFFSET       (0x400U)

typedef struct
{
  uint32_t magic;
  uint16_t format_version;
  uint16_t header_size;
  uint32_t target_id;
  uint32_t image_type;
  uint32_t image_size;
  uint32_t firmware_version;
  uint32_t flags;
  uint8_t image_sha256[32];
  uint8_t signature_r[32];
  uint8_t signature_s[32];
  uint8_t reserved[132];
} FW_UpdateManifest_t;

/* Two independent 64 KiB erase sectors hold alternating records.  A record is
 * committed only after its CRC has been written and read back successfully. */
typedef struct
{
  uint32_t magic;
  uint32_t format_version;
  uint32_t sequence;
  uint32_t state;
  uint32_t confirmed_slot;
  uint32_t confirmed_version;
  uint32_t pending_slot;
  uint32_t pending_version;
  FW_UpdateManifest_t confirmed_manifest;
  FW_UpdateManifest_t pending_manifest;
  uint8_t reserved[476];
  uint32_t crc32;
} FW_BootRecord_t;

typedef char FW_UpdateManifest_size_must_be_256[
    (sizeof(FW_UpdateManifest_t) == FW_UPDATE_MANIFEST_SIZE) ? 1 : -1];
typedef char FW_BootRecord_size_must_be_1024[
    (sizeof(FW_BootRecord_t) == FW_BOOT_RECORD_SIZE) ? 1 : -1];

uint32_t FW_CRC32(const void *data, size_t length);
uint32_t FW_ManifestIsWellFormed(const FW_UpdateManifest_t *manifest);
uint32_t FW_BootRecordIsValid(const FW_BootRecord_t *record);
uint32_t FW_BootRecordIsNewer(uint32_t left_sequence,
                              uint32_t right_sequence);
uint32_t FW_SlotOffset(uint32_t slot);
void FW_BootRecordMakeDefault(FW_BootRecord_t *record);
void FW_BootRecordSeal(FW_BootRecord_t *record);

#ifdef __cplusplus
}
#endif

#endif /* FIRMWARE_UPDATE_FORMAT_H */
