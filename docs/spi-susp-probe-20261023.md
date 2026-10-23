# Bounded SUSP discriminating test

Hardware state before the probe: A30 signed USB update/boot/confirmation passed;
PC701CFC0C/VTOR70180400, HIL100 exact tensors/NPU100/maxdelta2/27.531s.
Radio pool observed minimum improved5764->15180, peak59772->50356, free/used
9.64%->30.15%, by moving the9408byte project Radio Manager stack into unused
APP_RAM4. Bank sizes, controller/security permissions and vendor allocator remain
unchanged. PSP15sample maxima and wrapped pool observations are not full WC,
fragmentation or all-thread high-water proof.

The old A21 MASRX-only experiment observed automatic SPI SUSP and a500ms DMA
timeout, followed by two15s Cloud retries. A23 then overflowed its768byte worker
while formatting a diagnostic. B25 moved formatting to Radio, and B29 corrected
resource initialization and UART sink status. An OTA with no SUSP cannot establish
that the task-side service resumes a real suspended transaction.

The new explicit `radio flow-test` diagnostic arms once. Outside firmware updates,
on the next active full-duplex DMA transfer>=256bytes, it uses the target HAL's
`HAL_DMAEx_Suspend` on RX DMA, with the existing5ms HAL timeout. A second fixed
100000-iteration maximum waits for SPI SUSP. It records SR and remaining DMA
bytes, resumes that same descriptor with `HAL_DMAEx_Resume`, and leaves SPI SUSP
untouched. The ordinary task-side service must observe drained RX FIFO and clear
SPI SUSPC. It must then reach the ordinary completion callback with no transfer
failure. Only Radio formats the scalar evidence. No RXDR CPU reads, DMA restart,
clock changes, cache policy changes, fault/IRQ logging or NOR writes are injected.

The existing500ms DMA deadline is now anchored before HAL transfer start using
ThreadX ticks, so diagnostic time does not restart/extend it. Native tests cover
elapsed-before-wait, already-expired nonblocking check and wraparound. The helper
refuses arming during an updater session and never executes the hold while one
is active. It is unsupported outside the RX-backpressure build; the CLI command
is present only in the explicit resource diagnostic profile. Normal builds do
not arm it or allocate its state. No provider HAL file was modified.

Primary ST source reviewed2026-10-23: [DMA extension suspend/resume APIs](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Src/stm32n6xx_hal_dma_ex.c)
finish the current burst before suspension and resume the descriptor. This uses
DMA APIs, not `HAL_SPI_DMAPause`, which [ST's SPI HAL](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/main/Src/stm32n6xx_hal_spi.c)
marks unsupported. The target repository's own HAL source remains authoritative
for its5ms bound and register definitions; it was inspected without replacing it.

Acceptance requires actual captured SR.SUSP=1 with remaining bytes, resume count
increase, successful completion and valid subsequent radio command. If SUSP is
not observed it is NOT_EXERCISED. A failed hold/resume returns to existing bounded
SPI abort/recovery; do not repeat blindly. First exercise with harmless radio
traffic and no NOR update. Then complete an authenticated OTA on the tested
runtime, recording every block/timeout/retry and actual image confirmation.
An injected event proves this recovery path, not the original physical cause of
rare DMA starvation. These hardware probe/OTA results are still pending here.
