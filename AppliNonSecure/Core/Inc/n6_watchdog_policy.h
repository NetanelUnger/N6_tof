#ifndef N6_WATCHDOG_POLICY_H
#define N6_WATCHDOG_POLICY_H
#include <stdint.h>
/* All values use unsigned elapsed ticks; budgets must stay below 2^31. */
enum { N6H_UART_TX, N6H_UART_CONTROL, N6H_CLI, N6H_TOF_ACQUIRE,
       N6H_TOF_PROCESS, N6H_DISPLAY, N6H_RADIO, N6H_WIFI_CONTROL,
       N6H_CLOUD, N6H_COUNT };
typedef struct { uint32_t last, count; } N6H_Progress;
static inline uint32_t N6H_Expired(uint32_t now,uint32_t last,uint32_t budget)
{ return (uint32_t)(now-last)>budget; }
static inline uint32_t N6H_BadMask(const N6H_Progress p[N6H_COUNT],
    const uint32_t budgets[N6H_COUNT],uint32_t required,uint32_t now)
{
  uint32_t bad=0U;
  for(uint32_t i=0;i<N6H_COUNT;i++)
    if((required&(1UL<<i)) && (!p[i].count || N6H_Expired(now,p[i].last,budgets[i])))
      bad|=1UL<<i;
  return bad;
}
/* Arming expires at the deadline, requires a healthy ready supervisor and
 * inactive updater. A busy update invalidates rather than defers an arm. */
static inline uint32_t N6H_ArmValid(uint32_t kind,uint32_t now,uint32_t armed,
    uint32_t expiry,uint32_t healthy,uint32_t update_busy)
{ return kind && healthy && !update_busy && (uint32_t)(now-armed)<expiry; }
#endif
