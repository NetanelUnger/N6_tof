#ifndef SECURE_FIRMWARE_UPDATE_H
#define SECURE_FIRMWARE_UPDATE_H

#include <stdint.h>

#include "firmware_update_format.h"

#ifdef __cplusplus
extern "C" {
#endif

int32_t SecureFirmwareUpdate_Init(void);
uint32_t SecureFirmwareUpdate_Begin(const FW_UpdateManifest_t *manifest_ns,
                                    uint32_t *session_ns);
uint32_t SecureFirmwareUpdate_Write(uint32_t session,
                                    const uint8_t *data_ns,
                                    uint32_t length);
uint32_t SecureFirmwareUpdate_Finalize(uint32_t session);
uint32_t SecureFirmwareUpdate_Abort(uint32_t session);
uint32_t SecureFirmwareUpdate_ConfirmBoot(void);

#ifdef __cplusplus
}
#endif

#endif /* SECURE_FIRMWARE_UPDATE_H */
