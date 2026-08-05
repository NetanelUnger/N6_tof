#ifndef FIRMWARE_CRYPTO_H
#define FIRMWARE_CRYPTO_H

#include <stddef.h>
#include <stdint.h>

#include "firmware_update_format.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
  uint32_t state[8];
  uint64_t total_bytes;
  uint8_t block[64];
  uint32_t block_used;
} FW_SHA256_Context_t;

#define FW_CRYPTO_INIT_OK          (0)
#define FW_CRYPTO_INIT_ERROR_RNG   (-1)
#define FW_CRYPTO_INIT_ERROR_PKA   (-2)

void FW_SHA256_Init(FW_SHA256_Context_t *context);
void FW_SHA256_Update(FW_SHA256_Context_t *context,
                      const void *data, size_t length);
void FW_SHA256_Final(FW_SHA256_Context_t *context, uint8_t digest[32]);
void FW_SHA256(const void *data, size_t length, uint8_t digest[32]);
uint32_t FW_ConstantTimeEqual(const void *left, const void *right,
                              size_t length);

int32_t FW_Crypto_Init(void);
int32_t FW_Crypto_VerifyManifest(const FW_UpdateManifest_t *manifest);

#ifdef __cplusplus
}
#endif

#endif /* FIRMWARE_CRYPTO_H */
