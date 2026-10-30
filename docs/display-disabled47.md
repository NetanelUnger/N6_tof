# Optional GC9A01 display — version 47

The sole application switch is in `AppliNonSecure/Core/Inc/config.h`:

```c
/* #define APP_GC9A01_DISPLAY_ENABLED */
```

Leave it commented to exclude the display. Uncomment and rebuild to restore it;
this is a presence-based `#ifdef`, so defining it to zero still enables it.
No display implementation was removed.

The disabled build excludes the ThreadX display task and its stack allocation,
driver/state buffers, ToF display handoff, SPI4 callbacks, initialization,
LCD GPIO configuration/writes, DMA channel5 and its interrupts. The watchdog
required-task mask excludes the missing task. CLI help, completion candidates,
MAP usage, screen commands and display status are also conditional.
Shared GPIOE/GPDMA clocks and SPI5 radio operation remain enabled.
Weak startup-vector aliases remain for disabled IRQs; their peripheral IRQs
are never enabled and their application handlers are absent.

No IOC edit or Generate Code is required. If regenerating later, review the
manual guards in main.c, stm32n6xx_hal_msp.c and stm32n6xx_it.c as documented in
AGENTS.md. Turning off application use does not electrically disconnect panel
power or backlight.

Validation: full signed XIP builds with the switch enabled and disabled pass.
Enabled build retains display task/SPI4/DMA symbols; disabled ELF has no
Display_App/GC9A01 implementation, display task, SPI4 handle or DMA5 handle.
Both native watchdog configurations pass all 13 test groups; the disabled
case confirms and feeds with no display heartbeat. Existing toolchain warnings
remain. Artifacts: `.local-dependencies/xip/v47-A-display-disabled`.

Hardware: signed A47 package (479072 bytes) installed via COM8/CN8 XMODEM,
with EOT ACK and automatic reboot. A subsequent `reboot yes` disconnected USB;
version47 persisted after enumeration. HELP and invalid MAP SCREEN usage contain
no display menu entry; ToF ready, NPU ready/errors0, radio/GATT ready and SPI
fault count0. Image route stays NONE and map off. B46 remains the fallback.
Evidence: usb-install.log, usb-postflight.json, usb-after-reboot.json and
verification.json in the artifact directory. No cold-power removal or full
long-duration soak was performed for this change.
