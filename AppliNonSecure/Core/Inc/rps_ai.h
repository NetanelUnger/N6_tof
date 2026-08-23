#ifndef RPS_AI_H
#define RPS_AI_H

#include <stdint.h>

typedef enum
{
  RPS_AI_CLASS_NONE = 0,
  RPS_AI_CLASS_ROCK = 1,
  RPS_AI_CLASS_PAPER = 2,
  RPS_AI_CLASS_SCISSORS = 3,
  RPS_AI_CLASS_COUNT = 4
} RPS_AI_Class_t;

typedef struct
{
  uint32_t enabled;
  uint32_t ready;
  uint32_t last_frame;
  uint32_t runs;
  uint32_t errors;
  uint32_t inference_ms;
  int32_t last_error;
  uint16_t confidence_per_mille;
  uint8_t class_id;
  int8_t scores[RPS_AI_CLASS_COUNT];
} RPS_AI_Status_t;

int RPS_AI_Init(void);
int RPS_AI_ProcessDepth(const float *depth, uint8_t width, uint8_t height,
                        uint32_t frame_id);
void RPS_AI_SetEnabled(uint32_t enabled);
void RPS_AI_GetStatus(RPS_AI_Status_t *status);
const char *RPS_AI_ClassName(uint8_t class_id);
const char *RPS_AI_ClassDisplayName(uint8_t class_id);

#endif /* RPS_AI_H */
