#include "firmware_crypto.h"

#include <string.h>

#include "firmware_signing_public_key.h"
#include "stm32n6xx_hal.h"

#define FW_ROTR32(value, bits) (((value) >> (bits)) | ((value) << (32U - (bits))))

static const uint32_t fw_sha256_k[64] =
{
  0x428A2F98UL, 0x71374491UL, 0xB5C0FBCFUL, 0xE9B5DBA5UL,
  0x3956C25BUL, 0x59F111F1UL, 0x923F82A4UL, 0xAB1C5ED5UL,
  0xD807AA98UL, 0x12835B01UL, 0x243185BEUL, 0x550C7DC3UL,
  0x72BE5D74UL, 0x80DEB1FEUL, 0x9BDC06A7UL, 0xC19BF174UL,
  0xE49B69C1UL, 0xEFBE4786UL, 0x0FC19DC6UL, 0x240CA1CCUL,
  0x2DE92C6FUL, 0x4A7484AAUL, 0x5CB0A9DCUL, 0x76F988DAUL,
  0x983E5152UL, 0xA831C66DUL, 0xB00327C8UL, 0xBF597FC7UL,
  0xC6E00BF3UL, 0xD5A79147UL, 0x06CA6351UL, 0x14292967UL,
  0x27B70A85UL, 0x2E1B2138UL, 0x4D2C6DFCUL, 0x53380D13UL,
  0x650A7354UL, 0x766A0ABBUL, 0x81C2C92EUL, 0x92722C85UL,
  0xA2BFE8A1UL, 0xA81A664BUL, 0xC24B8B70UL, 0xC76C51A3UL,
  0xD192E819UL, 0xD6990624UL, 0xF40E3585UL, 0x106AA070UL,
  0x19A4C116UL, 0x1E376C08UL, 0x2748774CUL, 0x34B0BCB5UL,
  0x391C0CB3UL, 0x4ED8AA4AUL, 0x5B9CCA4FUL, 0x682E6FF3UL,
  0x748F82EEUL, 0x78A5636FUL, 0x84C87814UL, 0x8CC70208UL,
  0x90BEFFFAUL, 0xA4506CEBUL, 0xBEF9A3F7UL, 0xC67178F2UL
};

static const uint8_t fw_p256_prime[32] =
{
  0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x01,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};

static const uint8_t fw_p256_abs_a[32] =
{
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03
};

static const uint8_t fw_p256_gx[32] =
{
  0x6B, 0x17, 0xD1, 0xF2, 0xE1, 0x2C, 0x42, 0x47,
  0xF8, 0xBC, 0xE6, 0xE5, 0x63, 0xA4, 0x40, 0xF2,
  0x77, 0x03, 0x7D, 0x81, 0x2D, 0xEB, 0x33, 0xA0,
  0xF4, 0xA1, 0x39, 0x45, 0xD8, 0x98, 0xC2, 0x96
};

static const uint8_t fw_p256_gy[32] =
{
  0x4F, 0xE3, 0x42, 0xE2, 0xFE, 0x1A, 0x7F, 0x9B,
  0x8E, 0xE7, 0xEB, 0x4A, 0x7C, 0x0F, 0x9E, 0x16,
  0x2B, 0xCE, 0x33, 0x57, 0x6B, 0x31, 0x5E, 0xCE,
  0xCB, 0xB6, 0x40, 0x68, 0x37, 0xBF, 0x51, 0xF5
};

static const uint8_t fw_p256_order[32] =
{
  0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
  0xBC, 0xE6, 0xFA, 0xAD, 0xA7, 0x17, 0x9E, 0x84,
  0xF3, 0xB9, 0xCA, 0xC2, 0xFC, 0x63, 0x25, 0x51
};

static RNG_HandleTypeDef fw_rng;
static PKA_HandleTypeDef fw_pka;
static uint32_t fw_pka_ready;

static uint32_t fw_load_be32(const uint8_t *input)
{
  return ((uint32_t)input[0] << 24U) | ((uint32_t)input[1] << 16U) |
         ((uint32_t)input[2] << 8U) | (uint32_t)input[3];
}

static void fw_store_be32(uint8_t *output, uint32_t value)
{
  output[0] = (uint8_t)(value >> 24U);
  output[1] = (uint8_t)(value >> 16U);
  output[2] = (uint8_t)(value >> 8U);
  output[3] = (uint8_t)value;
}

static void fw_sha256_transform(FW_SHA256_Context_t *context,
                                const uint8_t block[64])
{
  uint32_t words[64];
  uint32_t a, b, c, d, e, f, g, h;

  for (uint32_t i = 0U; i < 16U; ++i)
  {
    words[i] = fw_load_be32(&block[i * 4U]);
  }
  for (uint32_t i = 16U; i < 64U; ++i)
  {
    uint32_t s0 = FW_ROTR32(words[i - 15U], 7U) ^
                  FW_ROTR32(words[i - 15U], 18U) ^
                  (words[i - 15U] >> 3U);
    uint32_t s1 = FW_ROTR32(words[i - 2U], 17U) ^
                  FW_ROTR32(words[i - 2U], 19U) ^
                  (words[i - 2U] >> 10U);
    words[i] = words[i - 16U] + s0 + words[i - 7U] + s1;
  }

  a = context->state[0]; b = context->state[1];
  c = context->state[2]; d = context->state[3];
  e = context->state[4]; f = context->state[5];
  g = context->state[6]; h = context->state[7];

  for (uint32_t i = 0U; i < 64U; ++i)
  {
    uint32_t sum1 = FW_ROTR32(e, 6U) ^ FW_ROTR32(e, 11U) ^
                    FW_ROTR32(e, 25U);
    uint32_t choose = (e & f) ^ ((~e) & g);
    uint32_t temp1 = h + sum1 + choose + fw_sha256_k[i] + words[i];
    uint32_t sum0 = FW_ROTR32(a, 2U) ^ FW_ROTR32(a, 13U) ^
                    FW_ROTR32(a, 22U);
    uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    uint32_t temp2 = sum0 + majority;

    h = g; g = f; f = e; e = d + temp1;
    d = c; c = b; b = a; a = temp1 + temp2;
  }

  context->state[0] += a; context->state[1] += b;
  context->state[2] += c; context->state[3] += d;
  context->state[4] += e; context->state[5] += f;
  context->state[6] += g; context->state[7] += h;
}

void FW_SHA256_Init(FW_SHA256_Context_t *context)
{
  if (context == NULL)
  {
    return;
  }
  context->state[0] = 0x6A09E667UL;
  context->state[1] = 0xBB67AE85UL;
  context->state[2] = 0x3C6EF372UL;
  context->state[3] = 0xA54FF53AUL;
  context->state[4] = 0x510E527FUL;
  context->state[5] = 0x9B05688CUL;
  context->state[6] = 0x1F83D9ABUL;
  context->state[7] = 0x5BE0CD19UL;
  context->total_bytes = 0U;
  context->block_used = 0U;
}

void FW_SHA256_Update(FW_SHA256_Context_t *context,
                      const void *data, size_t length)
{
  const uint8_t *input = (const uint8_t *)data;

  if ((context == NULL) || ((data == NULL) && (length != 0U)))
  {
    return;
  }

  context->total_bytes += length;
  while (length != 0U)
  {
    size_t available = sizeof(context->block) - context->block_used;
    size_t chunk = (length < available) ? length : available;
    (void)memcpy(&context->block[context->block_used], input, chunk);
    context->block_used += (uint32_t)chunk;
    input += chunk;
    length -= chunk;

    if (context->block_used == sizeof(context->block))
    {
      fw_sha256_transform(context, context->block);
      context->block_used = 0U;
    }
  }
}

void FW_SHA256_Final(FW_SHA256_Context_t *context, uint8_t digest[32])
{
  uint64_t total_bits;
  uint8_t padding[72] = {0x80U};
  size_t padding_length;

  if ((context == NULL) || (digest == NULL))
  {
    return;
  }

  total_bits = context->total_bytes * 8ULL;
  padding_length = (context->block_used < 56U) ?
                   (56U - context->block_used) :
                   (120U - context->block_used);
  FW_SHA256_Update(context, padding, padding_length);

  for (uint32_t i = 0U; i < 8U; ++i)
  {
    context->block[56U + i] =
        (uint8_t)(total_bits >> (56U - (i * 8U)));
  }
  fw_sha256_transform(context, context->block);
  context->block_used = 0U;

  for (uint32_t i = 0U; i < 8U; ++i)
  {
    fw_store_be32(&digest[i * 4U], context->state[i]);
  }
  (void)memset(context, 0, sizeof(*context));
}

void FW_SHA256(const void *data, size_t length, uint8_t digest[32])
{
  FW_SHA256_Context_t context;
  FW_SHA256_Init(&context);
  FW_SHA256_Update(&context, data, length);
  FW_SHA256_Final(&context, digest);
}

uint32_t FW_ConstantTimeEqual(const void *left, const void *right,
                              size_t length)
{
  const uint8_t *a = (const uint8_t *)left;
  const uint8_t *b = (const uint8_t *)right;
  uint8_t difference = 0U;

  if ((left == NULL) || (right == NULL))
  {
    return 0U;
  }
  while (length-- != 0U)
  {
    difference |= (uint8_t)(*a++ ^ *b++);
  }
  return (difference == 0U) ? 1U : 0U;
}

int32_t FW_Crypto_Init(void)
{
  if (fw_pka_ready != 0U)
  {
    return FW_CRYPTO_INIT_OK;
  }

  /* STM32N6 PKA operation requires an initialized, clocked RNG even for
   * deterministic public-key operations such as ECDSA verification. */
  (void)memset(&fw_rng, 0, sizeof(fw_rng));
  fw_rng.Instance = RNG;
  fw_rng.Init.ClockErrorDetection = RNG_CED_ENABLE;
  if (HAL_RNG_Init(&fw_rng) != HAL_OK)
  {
    return FW_CRYPTO_INIT_ERROR_RNG;
  }

  (void)memset(&fw_pka, 0, sizeof(fw_pka));
  fw_pka.Instance = PKA;
  if (HAL_PKA_Init(&fw_pka) != HAL_OK)
  {
    return FW_CRYPTO_INIT_ERROR_PKA;
  }
  fw_pka_ready = 1U;
  return FW_CRYPTO_INIT_OK;
}

int32_t FW_Crypto_VerifyManifest(const FW_UpdateManifest_t *manifest)
{
  PKA_ECDSAVerifInTypeDef input = {0};
  uint8_t digest[32];

  if ((FW_ManifestIsWellFormed(manifest) == 0U) ||
      (FW_Crypto_Init() != 0))
  {
    return -1;
  }

  FW_SHA256(manifest, offsetof(FW_UpdateManifest_t, signature_r), digest);
  input.primeOrderSize = sizeof(fw_p256_order);
  input.modulusSize = sizeof(fw_p256_prime);
  input.coefSign = 1U;
  input.coef = fw_p256_abs_a;
  input.modulus = fw_p256_prime;
  input.basePointX = fw_p256_gx;
  input.basePointY = fw_p256_gy;
  input.pPubKeyCurvePtX = FW_SIGNING_PUBLIC_KEY_X;
  input.pPubKeyCurvePtY = FW_SIGNING_PUBLIC_KEY_Y;
  input.RSign = manifest->signature_r;
  input.SSign = manifest->signature_s;
  input.hash = digest;
  input.primeOrder = fw_p256_order;

  if (HAL_PKA_ECDSAVerif(&fw_pka, &input, 5000U) != HAL_OK)
  {
    (void)memset(digest, 0, sizeof(digest));
    return -2;
  }
  (void)memset(digest, 0, sizeof(digest));
  return (HAL_PKA_ECDSAVerif_IsValidSignature(&fw_pka) != 0U) ? 0 : -3;
}
