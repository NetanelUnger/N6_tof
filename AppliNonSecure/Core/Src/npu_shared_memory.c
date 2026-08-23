#include "npu_shared_memory.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "main.h"

extern uint8_t __snpu_shared_bss[];
extern uint8_t __enpu_shared_bss[];

void NPU_SharedMemory_Clear(void)
{
  size_t length = (size_t)(__enpu_shared_bss - __snpu_shared_bss);

  memset(__snpu_shared_bss, 0, length);
  __DSB();
}
