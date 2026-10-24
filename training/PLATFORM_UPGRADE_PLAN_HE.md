# TRAINING Platform Upgrade Plan: BAT-Based Workflow

Date: 2026-10-21. Status: overall direction approved; milestones are not yet implemented.

## 1. Objective and Customer Experience

Extend the rock-paper-scissors workflow into a platform for different classification projects. Customers launch BAT files from `training`, answer questions in small desktop windows, collect and label samples, train a model, and build NPU firmware. Do not require manual JSON editing, source changes, or shell commands.

Existing BAT files remain the entry points. Interactive windows and automated mode must share application logic so checks exercise the actual product workflow. Each stage displays the active project, intended action, result, and next BAT file.

Initial scope: classification of individual depth frames, one active model on the device, multiple projects on the computer, and defined preprocessing and model templates. Temporal sequences, multiple-object detection, and concurrent models are future extensions. Configurable class counts do not imply support for arbitrary architectures.

## 2. Existing Foundation and Gaps

- `config/classes.json` and the training network output count already use configuration.
- `scripts/common.py` currently points to shared training directories.
- `scripts/01_capture.py` is directly coupled to Serial; separate the sample source.
- Firmware in `rps_ai.h/.c` and parts of N6DF assume four classes.
- Current preprocessing selects a nearby object and produces a silhouette. Make this an explicit profile rather than applying it to every new task.
- USB N6DF includes depth and the exact NPU input tensor. The wireless image stream is not a complete training record; verify compatibility before substituting formats.
- The website and server reside in sibling repository `Web_N6_ST67W611M1_VL53L9CX`. The relay keeps state in memory and depends on an open workspace. Independent, persistent cloud collection requires an extension.
- Reuse existing training, quantization, code generation, integration, HIL, and A/B update stages.

## 3. Planned BAT Interface

Entries marked new are implementation deliverables, not existing files at the time of writing.

| File | Responsibility after the upgrade |
|---|---|
| `00_SETUP.bat` | Prepare dependencies and check the environment |
| `00_PROJECT.bat` - new | Wizard to create, select, and edit projects and classes |
| `01_CAPTURE.bat` | Select USB / BLE / Cloud and collect into the same dataset |
| `02_REVIEW_DATASET.bat` | Review, correct labels, move samples between classes, and reject samples |
| `03_VALIDATE.bat` | Validate dataset integrity, data contract, and project association |
| `04_PREPARE.bat` | Prepare inputs and split by session or capture group |
| `05_TRAIN.bat` | Train using the active project |
| `06_QUANTIZE.bat` | Quantize and check accuracy loss |
| `07_GENERATE_N6.bat` | Compile for Neural-ART and check resource budgets |
| `08_INTEGRATE_MODEL.bat` | Automatically integrate the model and its contract into firmware |
| `09_BOOTSTRAP_NPU_SWD.bat` | Retain its existing role; use only when the Secure boot chain requires it |
| `10_LOAD_RAM.bat` | Load the candidate into RAM through the authorized hardware workflow |
| `11_HIL.bat` | Compare real device inference with host inference on the same input |
| `12_FLASH_RELEASE.bat` | Package or install through the existing A/B workflow |
| `90_PLATFORM_CHECK.bat` - new | Short automated upgrade check and summary report |
| `99_STATUS_RESUME.bat` | Project status, stale artifacts, and the appropriate next stage |

BAT files must forward arguments and return meaningful exit codes. Planned `--non-interactive` mode disables `pause`, prompts, and windows. Missing input returns BLOCKED with a reason instead of waiting. This mode does not bypass hardware authorization or approval for persistent installation.

## 4. Milestone 1 - Projects and Configuration Wizard

- [ ] Create `00_PROJECT.bat` and a small Python wizard using the existing UI framework.
- [ ] Support creation, opening, duplication, and persistence of the active project selection.
- [ ] Separate config, data, review, models, generated, reports, and state per project.
- [ ] Define a versioned schema: project ID, classes with stable IDs, input profile, preprocessing, model template, capture settings, and acceptance criteria.
- [ ] Import existing RPS as the first profile without losing existing data or artifacts.
- [ ] Update existing scripts to accept a shared project context.
- [ ] Generate derived files from configuration; avoid scattered source-text substitutions.
- [ ] Keep a backup and a recoverable change transaction, including interruption recovery.
- [ ] Invalidate artifacts according to configuration changes. A display-name change does not require retraining if semantics and outputs remain unchanged, but must update the relevant display metadata or package.

**Automated check:** Use the wizard application service to create two temporary projects, close and reopen them, switch between them, and check isolation and RPS import. Exercise creation and selection once through UI automation; service checks alone must not be reported as UI verification. No HIL is needed here.

**Exit criterion:** Select a project and continue through existing BAT files without manually editing files.

## 5. Milestone 2 - Classes, Labels, and a General Model Contract

- [ ] Support renaming, adding, merging, deleting, and splitting classes through the UI.
- [ ] Separate stable class IDs from network output indices and keep an explicit mapping.
- [ ] Renaming preserves sample identity; merging records the mapping. Deletion asks for a destination or leaves samples unlabeled. Splitting leaves samples for review rather than inventing labels.
- [ ] Store label provenance and revision history separately from original sensor data.
- [ ] Define a model contract: classes and output order, input shape, preprocessing, quantization details, model hash, and contract version. Generate C definitions and host/display metadata from it.
- [ ] Generalize score counts, names, and decoders in firmware and protocols, with explicit bounds and legacy input compatibility. Reject incompatible device contracts.
- [ ] Support the original RPS profile and an additional depth profile that preserves spatial information according to configuration.
- [ ] Ensure host and firmware preprocessing agree.

**Automated check:** On a small temporary dataset, exercise rename, merge, deletion to unlabeled, and a split pending review. Verify counts and original data are preserved and generated class mappings agree. Reject incompatible contracts before training or installation.

**Exit criterion:** Configure a two-class task alongside four-class RPS without manually editing class counts or names in source. Full NPU validation follows in M6.

## 6. Milestone 3 - Shared Sample Source and USB Preservation

- [ ] Move Serial access out of the labeling UI into a sample-source adapter.
- [ ] Define open, read, stop, status, and error interfaces for every adapter.
- [ ] Store a versioned sample record: device, session/boot identity, frame ID, source and reception timestamps, channel, units, sensor data, format/quantization, model contract, and inference result.
- [ ] Preserve the exact tensor when transmitted and explicitly record its absence. Do not present a host-reconstructed tensor as one received from the device.
- [ ] Preserve numeric training data and a separate preview. Default to lossless capture. JPEG or lossy quantization requires a profile that explicitly selects and records that choice.
- [ ] Commit records only after integrity validation. Use device+session+frame+channel identity to detect duplicates across restarts and counter resets.
- [ ] Allow unlabeled collection followed by later review.

**Short HIL:** Collect 20 USB samples from the connected sensor, save and reopen them, and verify CRCs, counts, frame identity, and metadata. Label a test copy and verify it enters VALIDATE/PREPARE. A static scene is allowed; do not require hand movement or a new object. For transport checks, disable only content-similarity filtering while retaining identity and integrity checks.

**Exit criterion:** The existing USB workflow operates through the new layer and the same BAT entry point.

## 7. Milestone 4 - BLE Capture in the Same Window

- [ ] Add BLE selection and device discovery to `01_CAPTURE.bat`.
- [ ] Reuse existing GATT and frame assembly implementations rather than adding another radio mechanism.
- [ ] Add a versioned training record or documented protocol extension. Carry numeric data and contract identifiers; do not assume the display message contains complete N6DF data.
- [ ] Advertise device capabilities and select only supported capture modes.
- [ ] Bound queues and rates, report accepted/rejected records, and discard partial samples on disconnect.
- [ ] Use existing/nonbonded GATT access according to the project workflow. Do not invoke Windows Pair or delete pairing to run a check.

**Short HIL:** Receive and save 20 real samples, perform one software disconnect owned by the test, reconnect, and receive 5 more. Verify sessions do not mix and partial samples are not saved. Do not require the optical scene to match a USB sample captured at a different time. Compare decoder bytes using a shared fixture without hardware.

**Exit criterion:** Customers collect and label BLE samples using the same window and dataset format as USB.

## 8. Milestone 5 - Cloud Collection and Persistent Storage

- [ ] Add guided endpoint, device, and authorization setup in the capture window.
- [ ] Add persistent sample and metadata storage with project/device association and access control.
- [ ] Create capture sessions bounded by duration, rate, and volume that do not depend on an open browser.
- [ ] Acknowledge reception only after storage and deduplicate retransmissions.
- [ ] Let TRAINING download samples, resume interrupted downloads, and label locally.
- [ ] Distinguish stored, sent-but-unacknowledged, and missing data during an outage. Continuous offline collection and device-side storage are outside the first release.
- [ ] Check server/device compatibility before capture. Document deployment order: compatible receivers before firmware sending a new format. Implement cloud changes in the sibling website repository.

**Short automated check:** A temporary local server stores a fixture, restarts, and returns the same sample. Retrying does not create duplicates; access to another project is rejected. This check is not HIL.

**Short HIL:** Receive 20 samples from a real device through Wi-Fi and the configured endpoint without an active browser. Download them through TRAINING and verify integrity and association. Resume once from the last cursor and verify no duplicates. Missing endpoint or authorization means BLOCKED, not PASS based on a fixture. Do not restart a production server to test persistence.

**Exit criterion:** Samples persist while the client is closed and remain available for later labeling through BAT.

## 9. Milestone 6 - Training, Integration, and NPU Verification

- [ ] Move stages 03-08 and 99 to the project context and shared contract.
- [ ] Preserve session/group splits to prevent train/test leakage.
- [ ] Record dataset, label, configuration, and model hashes plus tool versions per run.
- [ ] Train for the configured class count and generate all integration definitions.
- [ ] Enforce existing Flash, RAM, weight, and heap budgets. Do not increase budgets merely to pass a check; explain overflows and stop before release.
- [ ] Adapt Stage 11 to the general contract while preserving comparisons of inputs and scores belonging to the same frame.
- [ ] Demonstrate RPS and another classifier with a different number of classes.

**Automated checks:** Perform short training on an existing/dedicated test dataset, quantization, code generation, and integration. Synthetic data may validate the pipeline but cannot establish real-world accuracy.

**Focused HIL:** For each of the two models, run existing Stage 11 once with 100 frames on the exact RAM candidate. Check CRCs, frame/inference progression, and tensor/score agreement with TFLite using project thresholds. Report a static scene as a coverage limitation without requiring someone to move a hand. Do not claim recognition quality for every class has been demonstrated.

**Exit criterion:** Two different models execute on the actual NPU with correct contracts and names and matching host/device results. Restore the candidate designated in advance as the demo target when finished.

## 10. Milestone 7 - Packaging, Demo, and Workflow Completion

- [ ] Bind Stage 12 to the HIL report for the exact model, firmware, and project.
- [ ] Preserve A/B updates, signing, and increasing version policy; package code and weights together.
- [ ] Add `90_PLATFORM_CHECK.bat` with project/transport selection and automated mode.
- [ ] Produce JSON and a readable report containing PASS / FAIL / BLOCKED / NOT RUN per stage, artifact identities, sample counts, durations, and failure reasons. Failure or blockage returns a nonzero exit code. Do not print secrets, tokens, or key contents.
- [ ] Run a short automated UI workflow: open the wizard, select a project, change labels on test samples, and continue through BAT. Direct Python execution alone is insufficient to verify the customer workflow.
- [ ] Update `training/README_HE.md` with the file-by-file operating guide and screenshots where useful. Update engineering documentation according to repository rules during implementation.

**Acceptance:** The complete workflow is accessible through BAT files. Packaging checks use package-only mode. Persistent installation is a separate authorized Stage 12 operation with an explicitly selected version; do not flash automatically as part of smoke checks. Once installation is authorized, perform one transfer and verify the version/model after boot without repeating stability or fault-injection campaigns.

## 11. Automated Checks - Short and Unattended During Execution

### Preconditions and Automation Boundaries

- Run automated preflight for board availability, ports, ST tools, firmware capabilities, BLE/cloud connectivity, and existing authorization. Respect an existing lease and do not disconnect another user's client.
- Support runner-controlled lease acquisition and automatic release in `finally`. The current lease utility expects `release` on stdin, so adapt it or manage its existing interface explicitly.
- RAM loading requires a board already prepared for DEV mode and valid loading authorization. A script cannot move a jumper or connect a cable; unmet physical prerequisites return BLOCKED.
- This document specifies future work. It does not authorize reset, flashing, pairing, cloud deployment, or credential changes now. Honor authorization already granted within the execution workflow.
- After one-time preparation, checks require no questions, clicks, hand movements, code entry, or `pause`. Timeouts produce reports rather than waiting for a person.
- Release COM/GATT/debugger handles, stop capture sessions owned by the check, and restore runtime settings it changed. Record and report the final state even after failure.

### Budget and Scope

| Check | Planned maximum scope |
|---|---|
| Configuration/labeling/contract | Small fixture set; no hardware |
| USB | 20 samples; up to 60 seconds |
| BLE | 20+5 samples and one reconnect; up to 120 seconds |
| Cloud | 20 samples and one resumed download; up to 120 seconds |
| NPU | Stage 11 once per model, 100 frames; up to 180 seconds per run |

These are smoke-check time limits, not product throughput guarantees. Do not hide timeouts by automatically reducing coverage or changing thresholds. Classify infrastructure failures separately from data/model failures. Report training, compilation, and loading durations separately and give them environment-specific timeouts.

Do not repeat hour-long/overnight soaks, recovery campaigns, dozens of reconnects, or power-cut tests. Previous stability checks provide context, not proof of a new feature. Broaden checks only when a change affects a sensitive mechanism or a new failure justifies it. Run affected checks after changes and the integrated workflow once at completion. A passing result remains applicable while its relevant artifacts remain unchanged.

### Accurate Reporting

Report host checks, simulation, and HIL separately. Static-scene inference checks establish execution and computational agreement, not real-world task accuracy. Evaluate model quality on a separate labeled dataset. A person need not be present during integration checks to establish that the pipeline works.

## 12. Extensions After the Demo Release

Cloud-assisted labeling, sample selection for retraining, a cloud training worker, and fleet performance metrics will build on the contracts and metadata above. Keep cloud model suggestions separate from approved labels. Do not infer class splits or semantic correctness from confidence scores alone.

In the first release, training and compilation continue on the customer's computer through BAT; the cloud connection supports collection. Cloud training is not a prerequisite for completing the demo.

## 13. Implementer Completion Checklist

- [ ] M1-M7 completed with artifacts and a report for each milestone.
- [ ] The general workflow does not depend on RPS names or four classes.
- [ ] Every stage runs through BAT in guided and automated modes.
- [ ] USB, BLE, and cloud feed the same dataset and labeling interface.
- [ ] Customers change settings and labels without editing source or configuration files.
- [ ] Contract/model changes cannot silently reuse stale artifacts.
- [ ] Short HIL demonstrates real capture and two models executing on the NPU without human operation during execution. Coverage limits and blockers are reported explicitly rather than marked PASS.
- [ ] Update packages reference the correct model and report; persistent installation status is reported separately.
- [ ] Stability testing was not expanded without a new, documented reason.
