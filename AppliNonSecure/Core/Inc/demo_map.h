#ifndef DEMO_MAP_H
#define DEMO_MAP_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
/* Absolute deadlines; no catch-up burst and no dependence on sensor frames.
 * Sequence advances for every scheduled slot, even if publication is busy. */
typedef struct {
  uint32_t fps, destination, epoch, next_ms, sequence, accepted, skipped;
  uint32_t late_slots, max_late_ms, last_ms;
} DemoMap_Status;
static inline void DemoMap_Start(DemoMap_Status *s, uint32_t fps,
                                 uint32_t destination, uint32_t now)
{
  uint32_t epoch=s->epoch+1U; if(!epoch)epoch=1U;
  *s=(DemoMap_Status){.fps=fps,.destination=destination,.epoch=epoch,
    .next_ms=now+(fps ? 1000U/fps : 0U)};
}
static inline uint32_t DemoMap_Due(DemoMap_Status *s,uint32_t now)
{
  if(!s->fps || (int32_t)(now-s->next_ms)<0)return 0U;
  uint32_t period=1000U/s->fps,late=now-s->next_ms,slots=late/period+1U;
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
