#ifndef NPU_SHARED_MEMORY_H
#define NPU_SHARED_MEMORY_H

/* SRAM3 is opened to Non-Secure code by the Secure NPU bootstrap.  Large
 * transient buffers live here so the SRAM2 C heap remains large enough for
 * the VL53L9 transform library.  The section is NOLOAD and is cleared once at
 * Non-Secure startup. */
#define NPU_SHARED_BSS \
  __attribute__((section(".npu_shared_bss"), aligned(64)))

void NPU_SharedMemory_Clear(void);

#endif /* NPU_SHARED_MEMORY_H */
