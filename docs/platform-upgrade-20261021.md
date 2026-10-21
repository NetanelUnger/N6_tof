# Platform upgrade — 2026-10-21

M1 implemented and checked. M2–M7 NOT RUN. The original user plan remains
unchanged at `training/PLATFORM_UPGRADE_PLAN_HE.md` (initially untracked).

## Baseline

Firmware checkout `main`, starting HEAD `50461ba70ec56683a728d0cf5641f694103e82ae`,
remote `https://github.com/NetanelUnger/N6_tof.git`. The only preexisting Git
change was the untracked upgrade plan; no reset/stash/clean was used.
Source firmware version 11; NCP contract T01/SDK 2.0.106.
NUCLEO-N657X0-Q ST-LINK `000C00344142501620353451`, V3J17M11 detected.
Only COM6 is present. Read-only UART `a` had no reply in a two-second window;
CN8 CDC absent. Live MCU/NCP/ToF state is NOT VERIFIED. No reset/load/write was
performed. Exclusive project lease acquired/released; all owned handles closed.
The existing 2026-10-17 Stage 11 report is historical (100 frames, score delta
3, no CRC errors), not acceptance of this upgrade.

Sibling web checkout clean at `8d8d80c43c012cdc1e5bc2b33f1afc28b1d1db9e`;
remote `NetanelUnger/Web_N6_ST67W611M1_VL53L9CX`. Existing Azure `/api/health`
returned HTTP 200 / N6 Cloud Relay / ok. No deployment or server mutation.
The software-engineering skill was not in the executor catalog. Repository
AGENTS.md and operational documentation govern this implementation.

## M1 implementation and evidence

`00_PROJECT.bat` opens a real Tk wizard with create/open/duplicate/display-name
edit/import actions; unattended commands invoke the same ProjectService.
Existing Python stages resolve the selected project, or an explicit `--project`
override, through common.py. Config/data/review/models/generated/reports/state
are isolated under `training/projects/<slug>`. The shared venv/tools stay in
training. Local projects and transaction backups are ignored by Git.

Schema 1 carries persistent UUIDs for projects/classes, explicit output indices,
the frozen RPS input/preprocessing/profile, model template, capture settings and
acceptance thresholds. Derived configs are content addressed. Display-only
project rename retains the same config path/semantic identity and does not
require retraining. Stage manifests and deployment fingerprints bind project
and configuration identity. Imported/cloned historical acceptance becomes stale.

Creation/import stages a complete tree and verifies copied SHA-256 values before
atomic publication. The original RPS data/artifacts remain in their original
folders as the recoverable backup. Edit transactions retain old/new manifests;
durable journals roll forward interrupted publication/edit/selection on the next
wizard startup. OS locking prevents simultaneous editors. This does not claim
disk power-loss durability beyond fsync + atomic filesystem replacement.

Eight service tests PASS: two-project isolation/reopen/switch; preserved RPS
import; duplicate identity/bytes; display rename/config retention; interrupted
publish; interrupted edit; invalid path/derived config rejection; transient
Windows sharing violation retry. Real BAT-launched Tk window/button automation
created two temporary projects and selected the first: PASS. This is widget UI
automation, without native mouse/keyboard or screenshot/visual assertions.
`99_STATUS_RESUME.bat --project m1-check-20261021 --non-interactive` PASS.
Missing unattended wizard action exits 2 without waiting: PASS.
Existing synthetic N6DF CRC/framing/preprocessing checks PASS before/after.

The first real-tree publish hit Dropbox WinError 32. Retained journal and bounded
same-operation retries recovered it; the failure remains recorded separately
from the passing retry. Raw data and source config were not modified.
Machine-readable evidence/logs: `training/reports/platform_upgrade_20261021/` and
`training/reports/platform_upgrade_baseline_20261021.json` (local/ignored).

## Remaining scope

M2 class mutation/general firmware contract/spatial profile, M3 sample adapters,
M4 BLE training protocol, M5 persistent cloud, M6 two-model NPU comparison and M7
packaging/platform runner remain open. The current wizard intentionally exposes
the existing RPS profile; it does not claim arbitrary class/architecture firmware
support. Unattended support is currently verified for project/status stages;
remaining legacy capture/review/release prompts are not accepted as unattended.
Do not automatically invoke bootstrap/factory/persistent installation. No
firmware source, Flash, settings, credentials, bonding or security changes in M1.
No CubeMX Generate Code is required for these host-only changes.

## M1 final validation

The real imported RPS dataset also passed `03_VALIDATE.bat --project rps
--non-interactive`: 972 records, 970 usable, 2 existing review rejections,
4 relabelings, zero errors/warnings. All 970 retain exact device tensors.
No original metadata, label decisions or samples were changed.
Reproducible host/UI workflow check: run
`training/.venv/Scripts/python.exe -B training/scripts/check_project_workflow.py`.
It uses temporary UI fixtures and an isolated empty status project; no hardware.

Follow-up read-only SWD HOTPLUG preflight connected to the verified ST-LINK:
device ID 0x486, STM32N657 Rev B, 3.28 V. No reset/load was requested. Debug
access is available; this is not proof of the boot jumper position or a live
ToF/NCP application. The lease was acquired/released and handles closed.
The absence of CDC is not currently classified as a physical-action blocker.

## Live baseline and M2 checkpoint

M1 pushed to `main` as `7db2fb3ebcf055a6f19e14585da87fba3acd1d7a`;
remote SHA matched. GitHub reported zero check runs/Actions runs for that SHA;
this repository has no CI workflow. Local test evidence is reported separately.

One protected current-source v11 RAM candidate built in 41.437 s and loaded
through the supported loader in 23.687 s. Exact ELF SHA-256:
`ef5a1d45606fd5a58f30718c3f3fa4741a623b8a0f361c24d2097292dfccada3`.
Temporary build flags: W61_CONFIG_PRESERVE=1, APP_DEMO_BLE_ONLY=1;
settings writes/transition stay 0. No signing, version change or external NOR
write was requested. Original source defaults and ordinary Debug ELF/bin/map
were restored and checked against their original hashes. The ordinary Debug
binary remains config-preserve OFF and must not replace this guarded RAM image.

The loader's FSBL observed confirmed slot B/version 11, metadata sequence 27.
USB CDC reappeared as COM8/N6TOF001. Runtime version 11, ToF ready and advancing
at about 4 fps, Neural-ART ready with progressing runs and zero inference errors,
radio ready, zero SPI/queue/recovery/allocation errors. BLE advertising is command
ACK evidence only; disconnected, no pairing requested. Static-scene results do
not establish per-class accuracy. Runtime status/build/load evidence is retained
under `.local-dependencies/diagnostics/platform-upgrade-20261021/baseline/`.
The guarded image is 497216 bytes and leaves only 369072 bytes C heap, 432 above
the enforced 368640 minimum. New firmware must pass that same gate; no budgets
were increased. All owned serial handles closed; lease released after the check.

M2 is in progress, not accepted: class/label identity/provenance and model-contract
drafts have small-fixture host checks (3 class checks and one two/four-output
contract check). Later class-editor and acceptance-preservation additions are
untested. Drafts are preserved without installation under ignored
`.local-dependencies/diagnostics/platform-upgrade-20261021/m2-draft/RESUME.txt`.
M2 firmware/profile/protocol integration and M3–M7 remain open. There is no
pending approval or identified physical-action blocker at this checkpoint.
