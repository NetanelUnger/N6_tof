# Platform upgrade — 2026-10-21

M1 and M2 implemented and checked; M3–M7 remain open. Two-model NPU HIL remains M6. The original user plan remains
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

## M2 — host and firmware contract completed, full NPU verification deferred to M6

The project wizard now opens a Tk class/label/profile editor; Stage 02 uses the
same service for project datasets. Add/rename/merge/retire/split operations keep
stable class UUIDs separate from output indices. Immutable label snapshots,
sample-specific identity (not depth hash alone), provenance/history and durable
manifest transactions preserve original sensor files. Deleted/split samples
remain unlabeled until explicit review; no labels are invented. Existing human
rejections are preserved. Display-only renames refresh model/display metadata
without modifying TFLite bytes or requiring retraining; Stage 08 regenerates
the display definitions before new firmware packaging.

Supported input profiles: existing RPS silhouette and full-field spatial depth.
Schema-3/model-contract-v1 binds classes/output order, profile/preprocessing,
project semantics, uint8 input/int8 output quantization and exact model hash.
Stage 08 rejects incompatible contracts before installation and generates C
definitions. Source/runtime output counts and boundary types have compile-time
assertions. N6DF v4 carries bounded score counts and the complete contract ID;
legacy v1–v3 input remains supported. See n6df-classification-contract.md.

22 host tests PASS, including a two-class configuration through the UI service,
display-only contract refresh, original byte preservation, interrupted commits,
strict decoder checks, production C publisher fixtures for two/four classes and
byte-exact C/Python spatial preprocessing. BAT-launched Tk class UI passes six
actions. Legacy synthetic CRC/preprocessing and native BLE result sender pass.
Reusable UI check: training/scripts/check_class_workflow.py. Local evidence:
training/reports/platform_upgrade_20261021/m2*.json and m2*.log, shared C fixtures
in its fixtures/ directory. These are host/native checks, not HIL.

First guarded build passed the 368640-byte plan gate but left only 144 bytes
margin, below the protected 432-byte baseline. It was not loaded. Optimizing
only the cold CLI status formatter for size and shortening diagnostic text
produced 497176 bytes / C heap 369104 / margin 464. No budgets, queues, pools,
stacks, sensor/NPU optimization or transport timeouts were enlarged/relaxed.
Final source boundary assertions add no runtime code; a final build validates
them before RAM use. Candidate/build records are under ignored diagnostics
platform-upgrade-20261021/m2-candidate[-size2]/. No firmware load or Flash write
occurred during M2. No CubeMX Generate Code is required.

M3 begins next. M4/M5 transport capture and M6 two-model NPU HIL remain open.
The independent legacy wireless RPS viewer remains RPS-specific and fails
closed for general inference; it cannot substitute for a training record.

Final M2 protected build: 15.703 s; ELF cc8070778d3d8d39f8dfee9a733b0dfa4f7a90a544216d6437189e12c2c86915; binary 3d781da9a0a308ff8826fe530029214419efb2a8c0b78d799a7b3314485bf447. Heap 369104, margin 464; no hardware load.

## M3 - shared source and lossless USB capture completed

Serial access is confined to UsbSampleSource. The existing 01_CAPTURE.bat
opens a Tk source/session selector and supports bounded unattended collection.
The shared source/store contract preserves original N6DF bytes, numeric u16 mm
NPZ/PNG, separate preview, exact received tensor or explicit absence, source
model contract/inference, original device time and host reception clocks.
CRC validation precedes atomic publication. File hashes, immutable metadata,
SQLite deduplication and recovery are checked on reopen. A RAM-only once-per-
MCU-boot UUID plus native frame counter, original device timestamp and channel
distinguish resets from retries. Label revisions preserve that source identity.
Project copies retain explicit origin association. PREPARE requires an explicit
host-preprocessing override for absent/incompatible source tensors.

27 host/native regression tests pass; actual Tk Start/record/close controls pass
with a fixture adapter. Real USB HIL through BAT committed20 unique unlabeled
samples, reception span4.921s, all original CRCs/file hashes and source-contract
exact tensors verified on reopen. Static scene tests transport/computation, not
classification accuracy. The initial command failed only while printing its
completed report through cp1252; existing records and runtime were inspected
before proceeding, with no repeated collection. Reports now save before ASCII-
safe printing. No hardware operation has an uncertain outcome.

An isolated copy labels the20 new samples as a workflow fixture: VALIDATE992,
990 usable,0errors/warnings; PREPARE693/150/147 with unchanged quality gates and
intact group splits. Original20 remain unlabeled. Existing real RPS data supplies
class balance; the test labels do not establish optical truth. Active RPS also
passes VALIDATE with unlabeled integrity checks.

Protected M3 RAM image ELF d450f373623279560be66e779c549871a9a652fa4e0d8fa05780742690ab275d,
binary495536 bytes, heap370704 (margin2064; required baseline432). Earlier
below-baseline-margin candidates were never loaded. Size optimization is limited
to cold CLI parsing/status formatting; no budgets, pools, queues, stacks or
timeouts were raised. Source defaults and ordinary Debug artifacts are restored.
RAM loader passed; datasetoff/CLOUD route restored, NPUerrors0, all handles and
hardware lease released. No NOR/settings/signing/version/WindowsPair changes.
Evidence: training/reports/platform_upgrade_20261021/m3*.json/log; raw20 under
ignored projects/rps/data/raw/platform-usb-20261021; local protected build/load
records under ignored diagnostics/platform-upgrade-20261021/m3-candidate-size5.

M4 begins next; BLE/Cloud choices currently fail closed until their adapters
and capability checks are implemented. M4-M7 are not accepted by this report.

## M4 - nonbonded BLE collection completed

The same capture window adds BLE discovery/address selection and capability
checks. BleSampleSource uses the existing N6 CLI/ToF GATT UUIDs, bounded2-record
host queue, and TofFrameAssembler. A documented format5 carries a complete
lossless N6DF4 record inside existing version3 ToF fragments. Firmware uses the
same encoder as USB and the existing9072-byte radio snapshot/notification pump,
with generation/route fencing and no added MCU buffer or enlarged budget.
The outer NPU fields remain absent; the complete general inference/contract is
inside N6DF. A new capability query must explicitly advertise format5 support.
The desktop workflow and bounded unattended BAT collection share storage and
labeling. Unsupported Cloud remains explicit until M5.

Host/native coverage30 checks: production C encoder for2/4classes, preserved
Cloud/USB/BLE route ownership, actual callback decoding, shared C fixture byte
equality, CRC/order rejection and partial-disconnect discard. The Tk fixture
workflow remains PASS. Portable fixture/provenance: training/testdata/.

Final exact-candidate HIL PASS:20 real records, owned software disconnect,
reconnect,5 more, 45.156s total (limit120). All25 reopen with verified
original N6DF CRCs, numeric bytes, file hashes and source-contract exact tensors.
Two distinct connection/session IDs share one MCU boot identity;25unique sample
IDs. CRC/callback/queue-drop errors0; PairFalse/Windows pairedfalse. Static scene
is transport/computational evidence, not task accuracy. Existing assembler
fixture separately proves partial records cannot cross a disconnect.

First attempt FAIL1/20: the adapter incorrectly polled complete BytesIO packets
as a serial stream;46host decode timeouts, outerCRCerrors0. Records/reports
retained. Direct datagram decoding fixes it without raising timeouts. Intermediate
20+5 PASS45.219s. Final diff review found an overly broad route-release change;
native C assertions now preserve unrelated Cloud ownership, and the corrected
image was rebuilt, reloaded and retested20+5 before acceptance.

Final protected ELF bd50befb4e57d12adcd108740b0413e607eccff0793123a94f49a70c646bf94a,
binary495976, heap370256/margin1616 (baseline requirement432). Source/default
Debug restored. Datasetoff, pre-test CLOUD route restored after existing BLE
connection setup releases it, NPUerrors0/SPI faults0, BLEdisconnected. All owned
handles and lease released. No Flash/settings/credentials/signing/version/Pair/
cache changes or CubeMX generation. Local evidence m4*.json/log under the same
reports folder; protected build/load under ignored m4-candidate-final diagnostics.

M5-M7 remain open. The legacy browser/viewer does not interpret training format5
as a display image. New server training receivers must precede Cloud senders.

## M5 - receiver deployed; sender/client ready; real export approval BLOCKED

Sibling receiver commits7b404b9 and5905a7d are pushed. Exact final head
5905a7df14e1b2c486577297e4d741e82011ce3e passed GitHub Actions39641798300
(build, fixture, publish and existing Azure deployment). Live existing endpoint
returns health/capabilities/auth200 and browserAttached=false using the existing
workspace file. No new credentials or infrastructure were provisioned.
Ten local real-HTTP/process-restart/access/rate/volume/idempotence checks and
80 existing host protocol tests pass. Local restart fixtures are not HIL.

TRAINING Cloud setup now selects an existing HTTPS endpoint/workspace/device,
creates bounded recoverably idempotent sessions or resumes one, verifies every
downloaded record and advances the cursor only after durable local commit.
Interrupted local commits/replays deduplicate without token copies. All durable
Cloud samples are retained; live-scene similarity/host FPS filtering does not
discard already accepted server records. One server capture stays one split
group across downloader reconnects. Closing TRAINING preserves bounded server
capture. Transport-specific setup shares the existing capture window.

The firmware uses existing paired device authorization and a browser-independent
control endpoint. The existing radio snapshot carries complete N6DF4, remains
pinned until a matching stored/frame/time/boot/full-wire-CRC ACK, and retries
identical bytes on an unknown reply. Native production C state checks prove
retention, matching ACK release, local duration/count bounds and preservation of
newer USB/BLE ownership. No new payload buffer/queue or budget enlargement.
Existing legacy display codecs remain sender encoded. New record packing is
explicitly documented in AGENTS.md. No CubeMX/TrustZone/linker/XIP changes.

Host/native test coverage36 passes (34-suite plus5 focused Cloud tests including
two additional creation-recovery cases). Three existing native CLI reply/lease
scripts and the actual Tk fixture workflow pass. Memory failures367408/367792/
368464 were retained and NEVER loaded. Size optimization of cold CLI/startup
and bounded text/JSON routines yields heap369232/margin592, above required432.
Sensor/NPU/radio loops, pools/stacks and deadlines remain unchanged.

Protected BLE-only candidate8d90f4848653f6422468a550685dadb30a6256581f47505e83591b390d1a8c7b
is built/not loaded. Protected Wi-Fi candidate
7dc25492d394cf4ef775bcc09367254260c37b3c81c997cc55dd3520a31a7509 loaded
successfully with existing saved Wi-Fi/Cloud configuration; IPv4/pairing and
sensor/radio readiness were observed. Both have heap369232 and binary496952.
NCP preserve1/settings writes0/transition0; source defaults and ordinary Debug
artifacts restored. Existing plaintext device Cloud demo mode was not changed;
the TRAINING client uses verified HTTPS without redirects or TLS bypass.

The subsequent command to collect20 real sensor samples was DENIED BEFORE
PROCESS START by automatic approval review. Exact target:
natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net. Review reason:
upgrade/server authorization did not explicitly authorize exporting actual
sensor payload and device/workspace association to that destination. No retry
or indirect execution was attempted. No new training capture session, local
Cloud sample folder or collection report was created. User export approval is
pending in the parent thread. Treat the20-sample Wi-Fi/cursor-resume check as
BLOCKED/NOT_RUN, never PASS based on fixtures or mere Wi-Fi readiness.

Cleanup confirmed Cloud disabled/HTTPinactive, Wi-Fidisconnected/noIP, imageNONE,
datasetoff and trainingattempts0. Sensor remainsready. All owned serial handles
and hardware lease are released. Live RAM is the Wi-Fi candidate above in this
quiesced runtime state. No Flash/install/settings/credentials/WindowsPair/cache
changes. Existing legacy relay requests during authorized Wi-Fi startup were
rejected as workspaceinactive; do not claim that the denied collection ran.

Recovery: obtain explicit approval for20 actual depth/tensor/device-project
records to the named NatiLab endpoint. Inspect blocker/current outcomes first,
reacquire the lease, restore saved-profile RAM operation as needed, and perform
one bounded denied-operation retry under the new evidence. Do not repeat it
without new approval. Preserve existing candidate/build/failed-test records.
M6(two-model training/integration/100frames each) and M7(exact-bound packaging,
90_PLATFORM_CHECK and workflow guide) remain NOT_RUN in dependency order.

Local evidence: training/reports/platform_upgrade_20261021/m5*.json/log and
ignored diagnostics/platform-upgrade-20261021/m5-*; demo-target.json designates
the existing4-class RPS model before M6. The user requests a separate XIP branch
only after this upgrade; no branch, memory-map or OTP work was started here.
