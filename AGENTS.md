# Instructions for Codex and future agents

Read this file and [README.md](README.md) before changes. Read only the relevant
sections of [engineering-reference.md](docs/engineering-reference.md) when
changing firmware, hardware tools, memory, transports or generated code.
Do not load [CHANGELOG.md](CHANGELOG.md) or the
[archived checkpoints](docs/agents-history-20261116.md) during routine discovery;
use them only for a specific historical question. To append a changelog entry,
inspect only its top insertion area.

## Current scope — 2026-11-16

- This is the primary STM32N6 repository, `N6/project`, on `main`. The guarded
  RAM tooling and compact demo workflow were imported from `D:\N6_AI_TEST`.
- Preserve the existing four-class RPS model and normal firmware defaults.
  Importing the workflow does not install the AA model, copy training data,
  change persistence defaults or establish the current board state.
- The separate `danger-demo` AA-battery/empty-hand pilot at roughly 20 cm is
  **complete; do not collect, retrain or optimize it unless explicitly asked**.
  Its model/data/reload artifacts remain in `D:\N6_AI_TEST`; the
  [historical handoff](docs/danger-demo-ram_HE.md) records its result and limits.
- Main-checkout settings writes/transition remain enabled. Protected RAM
  candidates require both disabled; the loader refuses otherwise. NCP
  preservation is enabled for the candidate and normal defaults are restored.
  [Preparation and reload](docs/ram-demo-loader_HE.md).
- RAM disappears on reset/power loss. Do not infer current Flash slots from
  this file, the source version or archived checkpoints. Preserved XIP
  packages/evidence remain under `.local-dependencies/xip`.

## Working rules

- Preserve existing user edits and data. Keep captures append-only; retain
  failure evidence and distinguish PASS, FAIL, BLOCKED and NOT RUN.
- Explain in clear Hebrew what changed, why, what was checked and any remaining
  limitation. Do not claim hardware success from a build or mocked test.
- **English only in code:** identifiers, comments, docstrings, generated code,
  runtime class labels, logs, errors, CLI/terminal output and code examples
  must use English. Keep Hebrew for user-facing explanations and prose
  documentation only. Do not embed Hebrew display labels into firmware output.
- When asked for a quick demonstration, keep scope bounded by the [30-minute demo](README.md#demo-30-minutes).
  If a prerequisite blocks it, report that prerequisite; do not start a larger
  provisioning, reliability or accuracy campaign.
- Hardware actions require an intended hardware step, a matching board identity
  and the existing exclusive hardware lease. Never steal a lease or retry an
  uncertain reset/load before inspecting its outcome. Disconnect the user's BLE
  client intentionally and close COM terminals before collection/loading.
- Do not pair N6 in Windows, erase Bluetooth caches, expose credentials, alter
  OTP/debug security or erase NOR as a workaround. Keep password input hidden.

## RAM and persistent updates

- DEV: BOOT0=1–2, BOOT1=2–3. Flash boot: both 1–2. RAM loading itself does
  not imply no persistent writes: FSBL trial/rollback/fallback selection can
  commit boot metadata, and application/NCP startup can persist settings.
- For protected RAM demonstrations use [Tools/load_checked_ram.py](Tools/load_checked_ram.py),
  directly with frozen inputs or via `training/10_LOAD_RAM.bat`.
  Preserve DEV PC/BOOTSR verification, the `boot_metadata_commit` hardware
  breakpoint, confirmed-state check, full SRAM readback, failure parking,
  artifact hashes, settings flags and the 369072-byte heap floor.
  [Exact procedure and limits](docs/ram-demo-loader_HE.md).
- `--keep-network` retains saved Wi-Fi/Cloud intent plus BLE; the default is
  BLE only. A Cloud terminal needs an open Workspace. USB collection needs
  BLE released; one remote image destination owns the stream at a time.
- Never use bootstrap, factory provisioning, a signed USB update or the legacy
  unguarded debugger as a shortcut for the no-persistence demo.
- Persistent updates are separate: verified inactive slot, strictly increasing
  version, exact signed package, SHA-256/ECDSA, atomic metadata, confirmation
  and rollback. Keep XSPI2, PKA, keys and metadata Secure; never overwrite the
  active image or split model weights out of the signed firmware.

## Firmware invariants

- `N6.ioc` is the CubeMX source of truth. Prefer USER CODE blocks. After an IOC
  change, state that Generate Code is needed and audit all manual deviations
  in [the preservation table](docs/engineering-reference.md#31-known-cubemx-managed-changes-outside-user-code).
  C-only, documentation and Python-tool edits do not require Generate Code.
- Build the changed context. FSBL/Secure, startup, linker, TrustZone or shared
  interfaces require all affected contexts. Clean Non-Secure after `ux_user.h`
  changes. Sign the exact final image only for a persistent release.
- Preserve SAU/RIF/GPIO/NVIC ownership, cached vectors and vendor-source paths
  under `ThirdParty`. Review the detailed Flash map before address changes.
- Preserve memory gates, SRAM3/4 reservations and NPU cache attributes. Never
  shrink stacks or loosen latency/CRC/heap/HIL gates to make a test pass.
- Retain single owners, bounded callbacks/queues/timeouts and generation fences
  for I3C, USB, SPI, BLE and Cloud. Never format logs or block in an ISR.
  Keep each CLI session separate and one frame-matched image destination.
- After significant interface or loading-flow changes, update README and add
  a concise changelog entry. Run relevant host checks; hardware tests only
  when the task authorizes and requires them.

## Required demo handoff

Close every demonstration with four concrete facts: the model/project and
recorded result; exact artifact/report locations; the command and prerequisites
for reloading; and what remains outside scope. For the completed AA pilot,
retain the agreed closing statement:
**הדמו הושלם; אין צורך להמשיך לשפר דיוק.**
