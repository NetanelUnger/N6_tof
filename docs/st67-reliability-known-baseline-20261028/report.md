# ST67 CP3: reproducible B52 baseline established through USB

2026-10-28 UTC. This checkpoint establishes a known image; it does not claim
ST67 reliability improvements or final P0/P7 acceptance.

## Provenance search and safe continuation

The user identified Flow13; the actual host is NATISFLOW13. The earlier scoped
search covered 86 signed package headers (highest version50), two N6 worktrees,
Git refs/reflogs, recent project outputs and nine N6 assistant-session summaries.
The extended scan examined all timestamps: 1,451 N6 .bin/.elf/.n6fw files,
3,553,568,443 bytes, zero read errors, no compiled `Firmware version: 51`.
Saved-project inventory names only the already-searched N6 root. No unrelated
private content, authentication files, private-key contents, forbidden ACL paths,
or downloaded workspace-token JSON contents were inspected.

CLI version51 is a compiled string, not Secure metadata; both independently
reported51. Therefore a metadata-only rename of the located package50 is not
supported. The exact51 source/configuration/image remains unavailable.

## Slot inspection and retained failure

Native production-code tests exercise both confirmed A51/B51 states, require
wrong-slot rejection before erase, accept and abort the opposite manifest, and
compare every modeled NOR byte plus erase/write counters. NS XMODEM receives
exactly two128-byte SOH packets followed by CAN/CAN: no Write/Finalize/reset.
Existing Secure/FSBL and drain regressions also pass; PKA/NOR/CMSE/HAL are mocked.

Offline signatures/hash/vectors were verified for two diagnostic256-byte52
headers. Their referenced payloads were historical49/50 and were NEVER installed
as52; full temporary diagnostic packages were removed, only noninstallable
headers remain in task evidence. The real52 baseline below was freshly compiled.

On USB, authenticated A52 header was parameter-rejected; B52 header returned ACK
and direct Secure `Begin accepted; session=1`, then CAN/CAN returned normal CLI.
This identifies A as confirmed and B as inactive through the existing opposite-
slot policy; it is not a raw PC/metadata-bank/whole-NOR read. The diagnostic
runner is retained as FAIL/INCOMPLETE because a redundant deferred NS success
log did not arrive. Its direct Secure acceptance, wire ACK and cancellation are
retained unchanged. Separate old-manifest rejection then proved CONFIRMED51.
No image bytes/EOT/reset were sent in these four diagnostic transactions.

Later UART counters show80 dropped/queue-full/pool-full, zero UART transport,
HAL, timeout or internal errors. No initial UART counter was captured for the
group, so an exact drop delta or sole cause is not claimed. Missing deferred
text is not treated as Secure failure, and the failed test was not overwritten.

USB30s preflight PASS max64.004ms; postflight30s PASS max62.615ms. Running51
SPI fault count8 (previousCP1 count3), stable across each measured30s window;
last tick3943075, source1 phase2 len332 HALerror4 SR00be0040. NCPreset0,
allocationfail0, NPUerrors0. The intervening faults are unresolved.

## Actual baseline package and USB installation

Source `5432d4ae2b10ef7ecdfaedad586038792f0a4db5`,
`feature/n6-xip-ota-usb`. Existing Build-Xip builds all contexts, validates ABI,
heap, vectors, version and signature. The task wrapper removes historical
per-call safe.directory overrides and binds the original Tools directory; all
Git reads are ordinary already-trusted feature-worktree operations. No Git
trust, ownership, ACL or security setting was changed. All20 CP0 inventoried
source files are byte-identical after temporary build headers were restored.

Build: `.local-dependencies/xip/v52-B-st67-known-baseline/build.json`.
Package: `N6-XIP-B-v52.n6fw`,485472bytes,
SHA256 `8e1266cfde906c545277d9eb9a0fb01ef986202bb44b9e161510fbbdbb8df36b`.
Resource diagnostics/watchdogON, NCPpreserveON, settings persistenceON,
Cloud auto-mapOFF, fault probeOFF, RXexperimentOFF, runtime debug/CLI diagnostics
OFF as tracked. GuardedRAM heap395592 and XIP heap852488bytes exceed preserved
369072-byte gate; not runtime worst-case stack/heap proof. Offline FSBL/Secure
raw hashes match the savedB50 set; neither was programmed.

The existing Send-Xmodem.ps1 transferred only this fresh NonSecure package over
CN8. Fresh Secure CONFIRMED51 proof preceded transmission. Original protocol
limits remained10s start/10s block/30s finalize/two retries. Finalization PASS,
18.854s; automatic USB disconnect and reboot observed. FSBL reports pendingB52
with confirmedA51, signature/hash accepted, trialB52 and VTOR0x70280400. After
the existing50-second observation window, old-header rejection independently
proved Secure CONFIRMED52. Quiet runtime logging was not mistaken for missing
confirmation; no SkipBootVerification/AllowVersionJump was used.

Final first snapshot: ToFready, NPUerrors0, SPI/NCP/allocfail0, imagesNONE,
datasetOFF, saved Wi-Fi/Cloud settings generation2 and pairing retained, UART
queues/drops0. This is a restarted known baseline; zero counters do not mean the
previous intermittent SPI problem is fixed. Control/image/HIL100/endurance
gates remain to be measured on52.

A51 remains the previous on-board image under the existing ConfirmBoot swap;
its exact host artifact is still absent. This preserves the normal one-update
rollback basis without manufacturing an artifact51 or erasing the active image.
No physical rollback/power-cut/cold-power test or fresh whole-NOR backup is
claimed. Before any subsequent update targetingA, preserve/identifyA51 recovery
or explicitly choose a tested known replacement; do not silently discard it.

## Conclusions and next steps

1. Missing51 provenance is no longer a blocker to measuring this fresh knownB52
   baseline. It remains a historical attribution and host-recovery limitation.
2. P0-01 can be completed for52 using build.json hashes; P0-02/04/05 still need
   exact baseline compatibility/profile/acceptance records. P1 implementation
   remains gated on P0; native audit work is separate from hardware acceptance.
3. No cable/jumper/power action is required. Next: HIL100, bounded control and
   single-image profiles, acceptance worksheet; retain every incomplete run.
4. Firmware reliability code, bootloader, Secure, NCP firmware, credentials,
   ACLs and server were not changed. No commit/push/deployment occurred.
