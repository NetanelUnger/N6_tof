#ifndef FIRMWARE_UPDATE_H
#define FIRMWARE_UPDATE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int32_t Firmware_Update_Start(void);
void Firmware_Update_Feed(const uint8_t *data, size_t length,
                          uint32_t now_ms);
void Firmware_Update_Poll(uint32_t now_ms);
void Firmware_Update_Cancel(void);
uint32_t Firmware_Update_IsActive(void);
void Firmware_Update_ConfirmBoot(void);

#ifdef __cplusplus
}
#endif

#endif /* FIRMWARE_UPDATE_H */
