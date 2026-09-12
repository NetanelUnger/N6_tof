#ifndef RPS_MODEL_WEIGHTS_H
#define RPS_MODEL_WEIGHTS_H

#include <stddef.h>
#include <stdint.h>

#define RPS_MODEL_WEIGHTS_SIZE (55425UL)
#define RPS_MODEL_WEIGHTS_NPU_ADDRESS (0x24350000UL)

extern const uint8_t rps_model_weights[RPS_MODEL_WEIGHTS_SIZE];

#endif /* RPS_MODEL_WEIGHTS_H */
