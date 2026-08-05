#ifndef FIRMWARE_BOOT_H
#define FIRMWARE_BOOT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int32_t Firmware_Boot_Prepare(void);
uint32_t Firmware_Boot_GetNonSecureSourceOffset(void);

#ifdef __cplusplus
}
#endif

#endif /* FIRMWARE_BOOT_H */
