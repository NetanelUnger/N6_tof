# Quiet customer demo — 2026-10-24

The working checkout is `n6-xip-ota-usb`, branch `feature/n6-xip-ota-usb`.
A45 was installed over CN8 USB; the preceding B44 image remains available.
The primary `project` checkout was not modified except for the shared temporary
hardware lease, which is released after validation.

Application output is controlled in `AppliNonSecure/Core/Inc/config.h`:

- `N6_DEBUG_OUTPUT_ENABLED=0`: suppress ordinary UART logging, Non-Secure
  startup traces, ToF text, ST67 logging and optional NCP traces.
- `N6_CLI_DIAGNOSTICS_ENABLED=0`: suppress `[CLI-RESULT] state=accepted` and
  unsolicited/per-command `[RADIO-SERVICE]` diagnostics on all CLI routes.

Explicit command responses, errors, emergency fault reporting and the existing
FSBL/Secure boot diagnostics remain available. Watchdog and resource collection
remain enabled in the XIP build. `debug info` cannot override compile-time OFF.
No IOC, generated peripheral setup, linker, vendor or Secure interface changes;
no Generate Code is required. Custom application sources and configuration
headers contain the changes.

BLE and Cloud final result records are protocol messages: the website uses them
to release command admission. They remain on the wire. The companion website's
`TerminalOutput` hides these records only after raw protocol processing; the
filter handles fragmented notifications. This local website change has not
been published, so an older deployed site can still show the final record.

Build with PowerShell 7 from this checkout:

```powershell
./Tools/Build-Xip.ps1 -Slot A -FirmwareVersion 45 -Label demo-quiet-release
```

The immutable output exists at
`.local-dependencies/xip/v45-A-demo-quiet-release`; choose a fresh label for a
new build. A future installed release must use a new increasing version and
the inactive physical slot. Do not blindly reinstall this A45 package over A45.
The build helper temporarily selects the release version and restores the
tracked version header afterward; that header alone is not the installed version.

Build/sign/package checks passed; the package is 487680 bytes. USB transfer
received EOT ACK and rebooted automatically. A second explicit `reboot yes`
returned to version45. USB `version` produced only its echo, version line and
prompt. ToF was ready/advancing, NPU ready with errors0/inference3ms. UART
queued/sent0, ST67 submitted0, six seconds of passive application UART silence.
The existing build emits vendor, resource-instrumentation and RWX linker
warnings; compilation/linking/signing nevertheless succeeded.

Native CLI reply-failure, radio-service-state and XMODEM timeout regressions
passed. Website production build and eight command-progress/display tests
passed. Fresh BLE/Cloud hardware traffic, optical display, extended soak and a
clean-machine installation were not tested as part of this cleanup.

During postflight, `update status` was mistakenly treated as a status query;
the parser starts XMODEM for any `update` argument. No package bytes were sent.
The receiver was cancelled, the CLI recovered, and the explicit reboot and
successful final checks followed. Use `version`, `tof status`, `RPS STATUS`
and `debug uart` for read-only checks; do not use `update status`.

Retained evidence: `usb-install.log`, `reboot-request.json`, `verification.json`
and `build.json` in the immutable output directory. `verification.json` also
records the new configuration hash, because the build helper's tracked-source
enumeration does not yet include newly created untracked files.
