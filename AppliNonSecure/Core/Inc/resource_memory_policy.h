#ifndef N6_RESOURCE_MEMORY_POLICY_H
#define N6_RESOURCE_MEMORY_POLICY_H
#include <stdint.h>
#include <stddef.h>
#include "app_features.h"
/* Admission target, not a claim of measured worst-case. Unknown legacy stack
 * envelopes add208bytes IRQ/FP/RTOS context +128 uncertainty, then >=10%,64align.
 * Known aggregate/high-water must replace the envelope if it is greater.
 */
#define N6_STACK_CONTEXT_BYTES 208U
#define N6_STACK_UNCERTAINTY_BYTES 128U
#define N6_STACK_TARGET_BYTES(base) ((uint32_t)((((((uint64_t)(base)+336ULL)*110ULL+99ULL)/100ULL)+63ULL)&~63ULL))
#if (N6_RESOURCE_DIAGNOSTICS == 1U)
#define N6_STACK_BYTES(base) N6_STACK_TARGET_BYTES(base)
#else
#define N6_STACK_BYTES(base) (base)
#endif
#define N6_CAPACITY_BYTES(base) ((uint32_t)((((((uint64_t)(base))*110ULL+99ULL)/100ULL)+63ULL)&~63ULL))
static inline int N6_CheckedMultiply(size_t a,size_t b,size_t *out)
{
  if (!out || (b && a>SIZE_MAX/b))return 0;
  *out=a*b;return 1;
}
static inline int N6_CheckedStackBytes(size_t base,uint32_t *out)
{
  /* Bound before integer scaling and alignment; ThreadX ULONG is32bit. */
  if (!out || base>((UINT32_MAX-63ULL)*100ULL/110ULL)-336ULL)return 0;
  *out=N6_STACK_TARGET_BYTES(base);return 1;
}
static inline int N6_CheckedHeapMove(uintptr_t current,uintptr_t bottom,uintptr_t limit,ptrdiff_t delta,uintptr_t *out)
{
  if(!out||bottom>limit||current<bottom||current>limit)return 0;
  if(delta>=0){uintptr_t n=(uintptr_t)delta;if(n>limit-current)return 0;*out=current+n;}
  else{uintptr_t n=(uintptr_t)(-(delta+1))+1U;if(n>current-bottom)return 0;*out=current-n;}
  return 1;
}
#endif
