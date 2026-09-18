#ifndef FIRMWARE_UPDATE_H
#define FIRMWARE_UPDATE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t (*Firmware_Update_Write_t)(const void *data, size_t length,
                                           void *context);

int32_t Firmware_Update_Start(Firmware_Update_Write_t write,
                              void *write_context,
                              const char *transport_name);
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
