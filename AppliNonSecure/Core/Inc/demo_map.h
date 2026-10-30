#ifndef DEMO_MAP_H
#define DEMO_MAP_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
/* Source ceiling matches the existing ToF target of 10 frames/s. Keep timer
 * periods below the signed half-wrap deadline horizon; cap demo pauses at 60s.
 * CLI units are always milliseconds: legacy 1/2 FPS operands are rejected. */
#define DEMO_MAP_MIN_INTERVAL_MS 100U
#define DEMO_MAP_MAX_INTERVAL_MS 60000U
static inline uint32_t DemoMap_ValidInterval(uint32_t interval_ms)
{
  return interval_ms >= DEMO_MAP_MIN_INTERVAL_MS && interval_ms <= DEMO_MAP_MAX_INTERVAL_MS;
}
/* Absolute deadlines; no catch-up burst and no dependence on sensor frames.
 * Sequence advances for every scheduled slot, even if publication is busy. */
typedef struct {
  uint32_t interval_ms, destination, epoch, next_ms, sequence, accepted, skipped;
  uint32_t late_slots, max_late_ms, last_ms;
  uint32_t publish_busy, publish_unavailable, publish_other;
} DemoMap_Status;
static inline void DemoMap_Start(DemoMap_Status *s, uint32_t interval_ms,
                                 uint32_t destination, uint32_t now)
{
  if(interval_ms && !DemoMap_ValidInterval(interval_ms))interval_ms=0U;
  uint32_t epoch=s->epoch+1U; if(!epoch)epoch=1U;
  *s=(DemoMap_Status){.interval_ms=interval_ms,.destination=destination,.epoch=epoch,
    .next_ms=now+interval_ms};
}
static inline uint32_t DemoMap_Due(DemoMap_Status *s,uint32_t now)
{
  if(!s->interval_ms || (int32_t)(now-s->next_ms)<0)return 0U;
  uint32_t period=s->interval_ms,late=now-s->next_ms,slots=late/period+1U;
  s->sequence+=slots;s->late_slots+=slots-1U;s->skipped+=slots-1U;
  s->last_ms=s->next_ms+(slots-1U)*period;s->next_ms+=slots*period;
  if(late>s->max_late_ms)s->max_late_ms=late;
  return 1U;
}
static inline void DemoMap_Fill(uint8_t *out,size_t pixels,uint32_t sequence)
{
  size_t hot=(sequence-1U)%pixels;
  for(size_t i=0;i<pixels;++i){float value=i==hot ? 3500.0f : 500.0f;
    memcpy(out+i*sizeof(float),&value,sizeof(value));}
}
#endif
