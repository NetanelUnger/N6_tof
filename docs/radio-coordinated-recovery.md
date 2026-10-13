# Coordinated ST67 recovery — 2026-10-10

## Morning BLE-only readiness: corrected one-hour PASS (2026-10-12)

The supervised corrected soak **PASS3600.545552s**, with exact monotonic start
563251.3046344/end566851.8501866 and counters frozen at the interval boundary:
**6920 actual NPU results,3673 CRC-complete54x42 images,5971 CLI PONG+complete
replies**. Counts exclude setup and terminal drain; entire run6939/3676/5972.
CLI p50/p95/p99/max **93.40/111.79/126.39/219.73ms**, unchanged1500ms bound.
Direct NPU/image receive-gap maxima **0.570112/1.023138s**, below3s/5s;
maximum event-loop lag19.755ms. CRC/parser/image-drop/I/O errors0, no UART
recovery event, no new NCP recovery or SPI fault. Model wire age max253ms,
strictly increasing frame/inference IDs in generation25,1765 matching image/
model frame IDs. Eleven periodic USB snapshots kept ToF advancing, BLE route,
WiFiIP0/CloudHTTP0/images0/errors0/pairing preserved. MTU247/public/pairFalse/
actual OS-pairedfalse. NPU unsubscribe3.2s silence/expiry/fresh resubscribe proof
passes; deployed parser's16 protocol regressions pass. Browser rendering was
not observed by the agent, so these are native receiver and parser proofs.
Evidence: ignored `coordinated-ble-rps-hour-20261012-retry1/{report,verified-summary}.json`.

The earlier hour completed21:48:46UTC with CLI/CRC/count gates passing, but
**continuous receive acceptance was rejected after analysis**: NPU gap4.790206s
and image gap5.178279s. The old post-await freshness watchdog missed queued
callback bursts. Its4.7MB report was synchronously serialized/rewritten after
each ping; the shared atomic writer can sleep during replacement retries.
Bursts of increasing device frames/runs support host-loop backlog; exact old
write timing was not recorded, so a specific Dropbox/Windows cause is unproven.
Raw old report remains unchanged; its verified summary records raw-pass versus
NOT_ACCEPTED continuity. The reported21:49UTC machine interruption occurred
**after** the first terminal timestamp; no unobserved time was credited.

The host harness now writes small periodic status on a dedicated thread,
writes the full trace once after hardware cleanup, directly checks receive gaps,
measures loop lag and records exact interval/end counts. A120.624s focused test
with a deliberate4.502756s host-writer delay PASS: NPU gap0.567935s/image1.018840s,
loop lag15.823ms, no hardware changes. Evidence:
`coordinated-ble-rps-writer-focused-20261012/report.json`.
Reusable source: `hil_tests/run_ble_npu_soak.py`; compilation/help checks pass,
and its implementation was exercised by the focused and corrected hour runs.
No firmware change, build, load/reset or new website deployment was needed.

Final read-only immutable vector/text/rodata/ARM audit matches protected RAM
`5689348E42076D018F4614AEAA17D17B0FCF173A478A1EDCF5C73C3832870B61`,
bin493212/heap373064/margin4424, preserve1/BLE-only1/writesOFF/header9.
Store slot0/gen1/flags31/705/CRC72B6B9AF/writes0/calls4/arm0/busy0/io0 and
Cloud pairing exactly match the pre-hour baseline. Final ToF123106->123223,
radio ready, WiFiIP0/intent0/CloudHTTP0/requests0, BLE advertising/disconnected,
imageNONE, fence/drain/notify/recovery0, NCP/SPI0. All owned BLE/USB/UART/debug/
collector/lease handles closed. Evidence:
`coordinated-ble-rps-hour-final-20261012-retry1/inspection.json`.

Production remains exact MAIN18cff111.../Actions38303887605 and staticSHA
dce21722541f37b559e9bfe9c46316858fa0d616017717f7fee47b3a2e3aab6f.
Post-hour public health200/static bytes match. No FAE or firmware Flash/header/
signing/settings/Windows Pair/cache/bond/security change. Fresh CUA inventory
still apps[]/browsers[]: independent **production browser-to-board E2E NOT RUN**;
localhost browser receipt remains user-observed. [Morning checklist](demo-start-20261013.md)
now documents powered SRAM operation and guarded reload if RAM is lost.
This accepts the requested supervised one-hour BLE-only demo observation, not
all-night reliability, Wi-Fi/Cloud/fulltask4, classifier accuracy, physical
power loss, executing-handler interruption or historical fault causes.

## Actual BLE-only NPU/image runs and MAIN/Azure deployment (2026-10-12)

The user explicitly disconnected the browser and released hardware ownership.
The exclusive lease was reacquired only after checking competing processes.
This supersedes the earlier paused/user-owned checkpoint below. No OS Pair,
bond/cache/security mutation, firmware load/reset or persistence write occurred.

Three actual nonbonded BLE reconnect cycles **PASS** on hook-free protected RAM
`5689348E42076D018F4614AEAA17D17B0FCF173A478A1EDCF5C73C3832870B61`:
297 CLI PONG+complete replies, max189.49ms against the unchanged1500ms bound;
388 actual UUID0005 NPU results, 187 CRC-complete54x42 images, zero CRC/parser
errors. MTU247/public address/OS-pairedfalse/pair=False on all three connections.
NPU-only Notify left image route NONE/NONE each time. With ToF Notify and MAP ON,
images and results coexisted; frame/run IDs strictly advanced in generations
11/13/15, maximum model-result age252ms. All int8 scores/class/confidence matched
the actual-model formula. There were92 matching sensor frame IDs across image
and result records; other results stay separate in the UI. Observed class was
scissors, not a classifier-accuracy evaluation. NCP recovery/SPI faults remained0,
board Wi-Fi IP0/Cloud HTTP0/Cloud images0, Cloud pairing preserved. Disconnect
released image route to NONE. All run-owned handles closed. Evidence: ignored
`coordinated-ble-rps-integrated-20261012/{report,verified-summary}.json`.

The initial600s sustained image+NPU+CLI attempt failed in the host startup check. The initial host harness
asserted image availability before the first frame could arrive, failed with
0 images/12 valid NPU results, then closed handles. That failed artifact is
retained in `coordinated-ble-rps-soak-20261012`; the corrected harness gives the
first image an explicit5s startup budget, then requires fresh continuous images
and results with the same1500ms CLI gate. Retry evidence:
`coordinated-ble-rps-soak-20261012-retry1/report.json`. No firmware change/reset
was used for this host correction.

The corrected600s gate **PASS** at600.483s:1171 actual NPU results,
615 CRC-complete images/CRC errors0,976 CLI finals/max165.36ms, result age
max252ms,299 matching image/result sensor frame IDs. No malformed/stale result,
stream stall, UART recovery event, new NCP recovery or SPI fault. PairFalse and
actual OS-pairedfalse; RPS-only routeNONE, final routeNONE after disconnect.
All soak handles closed. The initial host startup failure remains retained.
This is ten-minute bounded acceptance, not an hour/overnight/fulltask4 pass.

Fresh final read-only SRAM audit matches vector/text/rodata/ARM of exact5689348E...
without halt/reset/load. Store slot0/gen1/flags31/705/CRC72B6B9AF/writes0/arm0/
busy0/io0/calls4 remains unchanged. WiFiIP0/intent0/CloudHTTP0/requests0, pairing
preserved; ToF ready/advancing40840->40921, BLE advertising/disconnected, image
NONE, fence/drain/notify/recovery0, NCP/SPI0. UART/USB/debugger/collector handles
closed and exclusive lease released. No firmware Flash/sign/header/persistent
write, Windows Pair/cache/bond/security mutation or FAE change. Normal Debug
8234AB7F... remains preserveOFF/BLE-onlyOFF and must not replace live protected
RAM. Final evidence: `coordinated-ble-rps-terminal-20261012/inspection.json`.


The human explicitly authorized N6 website MAIN merge and Azure deployment.
PR1 merged exact head7b95fd32 into MAIN
`18cff11142f250ff247952f852cfdd1d42ef8d41`. Exact push Actions run
[38303887605](https://github.com/NetanelUnger/Web_N6_ST67W611M1_VL53L9CX/actions/runs/38303887605)
**SUCCESS**: frontend lint/16 protocol tests/build, .NET package, Azure login and
Production deploy. Local website checkout is clean MAIN at that SHA.
[Production terminal](https://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net/terminal)
now serves `/assets/index-Bq_SpfPR.js`, SHA256
`dce21722541f37b559e9bfe9c46316858fa0d616017717f7fee47b3a2e3aab6f`,
byte-for-byte equal to the local merged build (336038 bytes), including UUID0005,
NPU RPS TX and Hebrew no-Windows-PAIR guidance. `/`, `/terminal`, `/cloud` and
`/api/health` return200; health says N6 Cloud Relay/ok. Evidence:
`coordinated-production-20261012/verification.json`. These are deployment/content
checks; the earlier browser-to-board receipt was user-observed on localhost,
not independent production browser rendering. Chrome/IAB automation remains
unavailable. No FAE_Master or firmware Flash/header/signing change occurred.

Older1515.03ms BLE-only, combined3193/2906/2543ms and wired Cloud-hour failures
remain failures. This new bounded BLE-only pass does not accept fulltask4,
executing-handler interruption, unexplained historical recoveries, natural SPI
root cause, physical power loss or overnight endurance.

## Earlier user-observed browser receipt and pause (superseded by release above) (2026-10-12)

The user reported the working browser panel: **NPU scissors, model score98.8%,
sensor frame20615, inference8943**. It explicitly said the result frame was
separate from the displayed image and that the model score is not calibrated
correctness probability. This is **user-observed end-to-end receipt**, not an
agent-captured packet trace, alignment proof, classification-accuracy result or
sustained acceptance. It supersedes a blanket claim that the browser path is
blocked; earlier WinRT failures remain failed with their causes unproven.
Evidence: ignored `coordinated-user-npu-receipt-20261012/report.json`.

**Project operating rule: NEVER PAIR this N6 BLE device in Windows.** Connect
through the browser's device chooser/GATT connect; do not use Windows Bluetooth
Settings Pair, a Pair API, `BleakClient(pair=True)`, forced bonding or cache/bond
erasure as a workaround. All automated N6 clients must request `pair=False`.
Cancel a system pairing prompt. The user's report that Windows pairing caused
trouble is operating guidance, not a proven diagnosis of earlier failures.
Existing Cloud pairing/settings remain separate and must be preserved.

The browser session is currently user-owned. The parent requested disconnect
and an explicit reply **מנותק**. Until the parent confirms release, do not acquire
the hardware lease, serial/debug/BLE handles, disconnect the user's session,
reset/load firmware, or start any automatic hardware test. Elapsed time is not
release. RAM5689348E.../BLE-only configuration remain unchanged by the agent.

Safe pending preparation: review retained logs and document the next acceptance
gate. After confirmed release and exclusive ownership, verify baseline/identity/
unchanged settings, then three bounded BLE image+actual NPU runs and soak. Capture
real UUID0005 records, model-score consistency, frame identity/age, CRC-complete
images, reconnect/CCCD behavior and the unchanged1500ms CLI bound. Preserve the
earlier1515ms failure and120.388s/188-finals/123-CRC-image pass. Production remains
unpublished until meaningful physical verification; latest website draft PR1
SHA0b30c802... has successful CI. No test was run during this user-owned session.


## Resumed BLE-only GATT investigation and browser handoff (2026-10-12)

Current hook-free protected RAM is
`5689348E42076D018F4614AEAA17D17B0FCF173A478A1EDCF5C73C3832870B61`,
binary SHA256 `D0EBAA4C69EAF6B4269E55B3041BB11C7DC66D342C5FC1AC6DC5AF55F8DEC445`,
493212 bytes/heap373064/margin4424, preserve1/BLE-only1/writesOFF/header9.
Normal Debug8234AB7F... is preserveOFF/BLE-onlyOFF and must not substitute.
The new Notify UUID0005 is now appended to **DEBUG service0101/index2**, after
its prior RX/TX. The former CLI/index3 prototype is superseded. Original
CLI/ToF/DEBUG creation order/indices and MAC/name remain unchanged. Changed native
sender/callback tests and five feature modes/default+protected builds pass; the
prior46-suite regression pass remains evidence, rather than a newly repeated run.

Safe physical investigation actually completed:
- Fresh characteristics over cached CLI/DEBUG services returned only old entries.
  Exact0005 UUID lookup returned status0/protocol-errorNULL/empty,530.69ms.
- Manual subscription to existing Generic Attribute Service Changed2a05 was
  denied by Windows. It was not retried or worked around; no bond/cache/security
  change occurred. No host-side Service Changed hook was found in current code;
  NCP-internal cache invalidation remains unverified. Windows documents its GATT
  cache as system-wide, so a fresh process alone is not an independent cache.
  [Microsoft cache semantics](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothcachemode).
- Temporary owner-thread NCP query DC861CD1... confirmed UUID-match1/index2/
  Notify16/READ1/type2 at startup. Temporary30EBF9D3... acknowledged supported
  volatile application GATT REGISTER0/1 as0/0 with the same readback. Neither
  resolved full uncached Windows discovery. This confirms the configuration
  table, not the active on-air graph or a specific Windows/NCP cause.
- Temporary B4C037D6... suppressed optional peripheral MTU/connection-parameter
  requests during discovery; scalar UART confirmed central-negotiation1. Full
  uncached discovery still failed E_UNEXPECTED. That hypothesis did not resolve
  discovery. No permanent connect-policy change was made. All temporary hooks
  were removed by restoring exact5689348E... with a fresh immutable SRAM audit.

**Bounded existing-channel BLE-only PASS:**120.388s,188 PONG/final pairs and123
CRC-valid54x42/9072-byte images, max131.81ms/GATT-write67.99ms, no slow commands.
Control call max472ms/queue max205ms, CLI drops/retries/errors0, image CRC0,
NCP0/0/failed0/SPI0, Wi-Fi IP0 and Cloud HTTP0. Busy image drops reflect the
single-snapshot backpressure policy, not corrupt completed frames. Evidence:
`coordinated-ble-only-latency-20261012/report.json`. The original1515.03ms failure
was not reproduced and its initiating owner remains uncaptured; no threshold
relaxation or endurance acceptance. **New NPU Notify received0; its three
integrated runs and soak remain NOT RUN.**

Final fresh audit `coordinated-appended-latency-final-20261012/inspection.json`
matches slot0/gen1/flags31/705/CRC72B6B9AF/writes0/loaded1/calls4, WiFiIP0/
intent0, Cloud paired/waiting/requests0, fence/drain/notify/recovery0; ready
advancing ToF, BLE disconnected/advertising and image NONE. All hardware handles
and the reacquired exclusive lease are released for the next human browser test.

Both `cua.createBrowserTab('chrome', ...)` and `('iab', ...)` explicitly returned
Browser unavailable; inventory apps[]/browsers[]. Native control is disabled.
The tested localhost preview is still running,HTTP200 at
`http://127.0.0.1:4173/terminal`, asset `index-87c4YD8S.js`.
Human step: regular Chrome on this connected Windows PC; close only stale N6
BLE tabs, preserve the Cloud workspace; open preview, press חיפוש התקן BLE,
select N6-MAINT-B8FB, and report whether NPU RPS TX is available. If available,
enable it and TOF IMAGE TX; cancel any system pairing prompt. No host BLE test
runs concurrently. A genuinely independent BLE central may be needed if this
Windows cache remains unresolved; cache clearing/unpairing is not proven necessary
and is not authorized by the present scope.

Website draft PR1 now has SHA `0b30c802e2c92333d8be792971da83e9b0968fd5`,
CI run38299648238 success; production deployment remains skipped/not run. No
FAE, firmware Flash/signing/header, stored settings/credentials or identity change.


## BLE-only NPU/demo checkpoint - NOT ACCEPTED (2026-10-12)

The latest user scope supersedes network coexistence testing: the board now
runs a protected **BLE-only RAM profile**, without a Wi-Fi connection or Cloud
traffic. `APP_DEMO_BLE_ONLY=1` suppresses only volatile station restore intent;
saved settings are still loaded read-only. No Wi-Fi disconnect/store operation,
Cloud disable/save, credential deletion, re-pairing or PC network change was used.
Ordinary feature defaults retain their prior behavior. `W61_CONFIG_PRESERVE=1`
retains the existing read-only NCP configuration checks; mismatch still stops.

The new optional CLI-service Notify characteristic is
`7a1e0005-b5a3-f393-e0a9-e50e24dcca9e`, index3. CLI RX/TX and image UUID/indices
are unchanged. Its CCCD only controls NPU results and never requests/releases an
image destination. The existing shared asynchronous notifier gains source5;
generation loss, unsubscribe and binary updater cancel/drain it before reuse.
One bounded192-byte Radio-owned slot replaces unadmitted results, pins admitted
frame/scores, and limits publication to2Hz. No new task/queue/image buffer or
steady allocation. Existing CLI priority and image fragment scheduling remain.

The actual Neural-ART success snapshot publishes its four int8 scores, argmax,
per-mille confidence, sensor frame, inference counter and HAL tick atomically.
The wire format is bounded newline ASCII JSON: `v,g,f,r,ok,c,p,q,npu,a`.
`q` order is none/rock/paper/scissors; `p` is the existing rounded quantization
conversion, not calibrated probability of correct recognition. Disabled/not-run/
error/stale output is invalid. The fixed-width age footer stays together at
ATT20 and is refreshed until copied; receivers also expire partial/displayed
records, reject inconsistent scores and old generations, and clear on disconnect.
`none` is a real model class, not a transport failure or fabricated prediction.

**Validation PASS:**46 native suites; five wifi_ble feature modes; ordinary and
protected Non-Secure compile/link/memory checks. Native coverage includes ATT20
fragmentation, pinned scores, admission backpressure, age/tick wrap, cancellation
and image handover independence. The existing RWX LOAD warning remains. A default
compiler crash/TEMP failure and intermediate host failures are retained; writable
process-local TEMP and normal build access corrected compilation. Debug artifacts
were finalized after the guarded loader restored them. No Generate Code needed.

Current live ELF SHA256:
`7CAB8F5AE062C9542E240A14AEF746BA14E7F0794868B0B4701973FB5090E1E6`.
Binary SHA256 `2EA5CC69133D82898BF429D127C52D4E77786AE7801B1E102FE6FB61E1EC3C61`;
493212 bytes, heap373064, margin4424 above368640. Writes/transitionOFF, preserve1,
BLE-only1, header9, no DMA test hook. Ordinary Debug ELF
`2C168A542149F11A6E03E2352001B86C0E9F9FC82F4D4F2F743459BA605FA881` is
preserveOFF/BLE-onlyOFF and must not be loaded under the current guarded scope.

**Physical Notify BLOCKED:** the sandbox attempt failed before commands. Normal
uncached full-service discovery failed with Windows E_UNEXPECTED; public/random/
automatic variants did not resolve it. CLI-service-only uncached discovery failed
with ERROR_BAD_COMMAND (or address not found). A read-only cached catalog connected
but retained old UUIDs and lacked0005. This is cache/discovery evidence, not proof
of the firmware/NCP/Windows cause. No cache erasure, OS re-pairing, adapter reset or
credential workaround was performed. The three new image+NPU integrated profiles
never reached subscriptions: **NOT RUN**, not three passing runs.

**Existing-channel BLE-only gate FAILED:** cached unchanged CLI/ToF handles did
receive five9072-byte54x42 CRC-valid images and five PONG/final pairs. Latencies
104.77/67.58/142.06/78.00/1515.03ms; the last exceeded the unchanged1500ms gate.
No NPU notification was claimed from this observation. Its initiating contention
owner was not captured; it is not proof Cloud alone caused prior BLE latency.
Actual NPU execution is independently visible over USB: e.g. runs4228/errors0,
frame9998/scissors/988permille/raw[-128,-126,-127,125]/inference2ms. LCD reports
the corresponding real model result; DMA render is not optical verification.

**Final public gate PASS:**20 USB PONGs, max308.58ms, local LCD map enabled,
35 submitted/rendered frames, LCD DMA7605/errors0, advancing ready ToF/NPU.
Radio ready, NCP0/0/failed0, SPI fault0; BLE disconnected/advertising, queues empty.
Cloud remains paired but waiting for Wi-Fi, HTTP0/requests0/images0. Fresh immutable
SRAM and settings audits before/after confirm slot0/gen1/flags31/705/CRC72B6B9AF,
writes/arm/busy/io/fence/drain/notify/recovery0, loaded1/calls4, volatile intent0.

The N6 website (not FAE) has optional result discovery, bounded validation, a
Hebrew class/percentage/frame panel and stale-session handling. Local lint/build
and16 protocol tests pass. User-authorized commits were pushed to
`codex/npu-notify-demo-20261012`, SHA
`7e63750973faa1de04dc6aab8b4dca3986576890`.
[Draft PR1](https://github.com/NetanelUnger/Web_N6_ST67W611M1_VL53L9CX/pull/1)
has successful CI build/tests/.NET packaging; deploy is skipped for the PR.
The task has no available browser surface, so actual Web Bluetooth/rendering and
new physical Notify remain blocked. Main merge/production deployment and deployed
verification remain **NOT RUN**, pending acceptance rather than a new approval.

Evidence is retained under ignored `coordinated-ble-rps-20261012/`,
`coordinated-rps-preload-20261012/`, `coordinated-rps-loaded-20261012/`,
`coordinated-rps-final-20261012/` and four `coordinated-ble-rps-hil*` failed reports.
The earlier304CC6F7 recovery/DMA passes below retain their own scope; their failed
latency/endurance reports remain failed. Natural SPI cause/unclassified recovery,
executing-handler cancellation, unattended reconnect and full task4 stay open.
No persistent firmware Flash, signing/header change, settings write or FAE change.
Owned handles and the hardware lease are released at the terminal checkpoint.


## Coordinated demo follow-up — bounded recovery PASS, BLE latency FAILED (2026-10-12)

The current source and protected RAM candidate are independent of the previous
parent checkout. The starting branch was `ble` at
`62483589670b1cadbd379a7b3e6ffd206a2e8844`; its three dirty documentation files
were preserved. No local `.agents/skills` directory was found in the examined
project ancestors. Runtime app status showed the previous local task idle, its
terminal report confirmed closed handles, and elevated read-only process
inspection found no competing serial/debug/HIL process. A host-only exclusive
lease now coordinates access; an existing marker is a blocker, never something
to remove or steal. The live owner checkpoint is in the ignored
`coordinated-owner-progress.json` file.

**Source change:** an automatically restored CLI CCCD can let an UNKNOWN event
drain before a newly attached application observes it. A new host profile
reproduced missing remote UNKNOWN while the firmware's pending flag reached 0;
the failed report is retained. This does not prove the exact Windows/NCP timing.
Firmware now repeats the same sequenced event once after fresh CLI input in
that generation, holding that input through the event's terminal drain. The
readiness epoch is published before RX queue admission can wake the CLI. The
initial event remains proactive; already-present input needs no duplicate, and
a later ordinary generation cannot resurrect an acknowledged event. This does
not replay the interrupted command, its output, or a command completion marker.
Binary firmware update retains its existing exclusion. Two static 32-bit epochs
add 8 bytes; task, queue, response capacity, HTTP/TLS and SDK budgets are unchanged.

**Image policy:** three pure CLI connects without image CCCD writes passed18
PONG/final pairs and kept CLOUD. The host runner now leaves the ToF CCCD alone,
retires the old CLI notification/client before NCP return, and retains causal
UART collection between profiles. An actual image CCCD enable remains a BLE
request under last-request-wins. There is no firmware route-policy change.

Validation:45 native suites and5 feature modes for the changed unit pass; both
ordinary and protected Non-Secure build/link/memory checks pass. A compiler TEMP
failure and a host lease-read failure before hardware access are retained and
corrected. The lease uses a separately readable JSON status because Windows byte
locking also prevents reading the marker. The existing RWX LOAD warning remains.
No Generate Code is required.

Protected hook-free ELF SHA256:
`304CC6F723881BD3E8DA50219858F6BBED317D15F394701B0368B239F136389D`;
binary SHA256 `805489AEBD9F7DFDC0744E3D2E476B8B29AE1B48FDD8AC347839CF2E7BE822B3`.
Binary492124 bytes, C heap374360, margin5720 above368640 minimum. It has
`W61_CONFIG_PRESERVE=1`, settings/transition writesOFF and header9. Ordinary
Debug ELF49E3F634... is config-preserveOFF and must not replace this guarded RAM
candidate. Known protected fallback05FD9EFD... and primary ELF/bin/map copies
are preserved in ignored `demo-ready-20261013/manifest.json`.

### Actual partial DMA cancellation

A temporary, explicitly host-armed SRAM-only copy suspended only SPI5 TX10/RX11
after observing real DMA progress during BLE notification payload transmission.
The unchanged SPI worker then entered its real abort/cleanup path. The temporary
hook is absent from the final demo image and starts unarmed in each probe image.
No shared GPDMA reset or payload/credential inspection was used.

- Initial probe F576FC3B...:252 bytes,250 RX bytes still remaining at abort;
  both channels disabled and both DMA handles plus SPI READY after abort.12 BLE
  finals/11 USB pings and clean fresh-generation output pass. Actual new-client
  UNKNOWN was not observed; this initial result does not prove notice reception.
- Current-fix probe FEDAC2E8...:252 bytes,251 RX bytes remaining at abort,
  TX had already advanced8 bytes. Both channels disabled and DMA/SPI READY.
  Automatic AT_FENCED recovery16877ms,12 BLE finals/14 USB pings, actual sequence1
  UNKNOWN observed, no old HELP banner. The same sequence may appear twice by
  design, before and after first fresh input. No old command was replayed.

Evidence: ignored `coordinated-dma-20261012/{initial-report.json,report.json,
initial-build.json,build.json}` plus named scalar pre/post DMA registers and
fresh immutable SRAM audits. The hook was disarmed and the hook-free304CC6F7...
image restored through the supported SRAM loader before integrated acceptance.
This is controlled partial-transfer cancellation, not natural SPI causality or
executing-handler proof. The notice snapshot still has active_reply0/tx_slots4.

### Three final integrated profiles

All three profiles pass the bounded gate on the exact hook-free304CC6F7... image:

| Profile | Radio/Wi-Fi recovery | BLE PONG/finals | USB pings | Cloud accepted frames before/return/final |
|---|---:|---:|---:|---|
| 1 | 19819ms | 13 | 9 | 515/526/558 |
| 2 | 20533ms | 13 | 9 | 594/600/638 |
| 3 | 20519ms | 13 | 14 | 678/685/716 |

Every profile captures exactly one TEST_MISSING_RESPONSE START, genuine fence,
Wi-Fi restoration and ready END. Attempts/ready0->3/3, failed0; no extra recovery
between profiles.39 BLE finals/32 USB pings; maximum observed BLE314.06ms and
USB308.75ms include host observation overhead. UNKNOWN precedes each new
readiness PONG, even when profiles2/3 deliberately discard the proactive notice
to model a late application observer. No old HELP banner or extra command final,
no image CCCD writes, CLOUD route retained, advancing ToF and automatic Cloud
return. Continuous USB/UART handles are retained between profiles and closed at
the terminal result. Evidence: `coordinated-integrated-final-20261012/summary.json`
and its three `profile-N/report.json` files. Earlier FAILED reports remain FAILED.

### Sustained demo validation and remaining risks

The strict combined one-hour profile **FAILED** on a completed BLE reply taking
3193.5ms, above its declared1500ms functional bound;66 BLE finals/65 USB pings
were observed before stopping. The LCD SPI4 DMA, ToF and Cloud counters advanced.
A separate180.548s diagnostic profile also **FAILED** the same latency bound:
180 BLE finals/179 USB pings, with slow replies2906.82/2543.51ms. Their GATT writes
took45.17/50.17ms and the firmware PONG ticks were only201/193ms after the preceding
USB PONG. TX admission contention peaked306 ThreadX ticks=3060ms, with no BLE
drop/retry/error, Radio max gap23ms and Cloud worker maximum4501ms. The existing
Cloud HTTP budget is4500ms. This supports output admission contention, but the
specific AT owner at each slow reply was not captured; no speculative late
network/protocol refactor or budget increase was made. These are completed
commands, not a passed BLE latency gate.

The distinct one-hour **wired USB/LCD/Cloud** profile also **FAILED**: last
stored elapsed1186.5s,1401 USB PONGs/max313.68ms, then new Cloud request errors
2->4 (drop3 unchanged). The declared strict gate stopped; this was not a completed
hour or an accepted Cloud demonstration. Its failure report and final public
snapshot are retained under `coordinated-wired-demo-soak-20261012/`.

Before that sustained baseline, a natural SPI fault was found: count1, source1
pre-HAL IRQ, RX overrun HAL_error4, len520, tick431538. Radio remained ready and
NCP stayed3/3. It occurred outside the prior continuous observer window; an
association with the intervening SRAM audit is unproven. Keep this captured fault
and the older unclassified extra recovery. One more unclassified recovery was
seen after an earlier old-reader reload outside its30s observer; current protected
starts now retain90s UART coverage, without repeating that extra recovery so far.

Fresh protected metadata after the three profiles still matches slot0/gen1/
flags31/705/CRC72B6B9AF, writes/arm/busy/io0, loaded1/calls4. A final audit and
handle/lease release follow sustained testing. Independent browser rendering is
unavailable in this environment, and LCD DMA completion is not optical proof.
Executing-handler cancellation, unattended Windows reconnect, natural fault
root causes, full task4 latency/endurance and physical power-loss durability
remain open. There was no persistent Flash/header/signing/pairing/settings
mutation, Git push or deployment.

See [the exact classroom start and protected fallback checklist](demo-start-20261013.md).

## Active Cloud/BLE reply recovery campaign — overall FAILED (2026-10-12)

Three bounded profiles each submitted exactly one genuine missing-response test
while Cloud images were active and BLE HELP was accepted but not fully received.
All three profiles retain FAILED verdicts; the narrower passing observations
below do not promote them to whole-gate acceptance.

- First profile: radio/Wi-Fi returned in17619ms, but image destination changed
  CLOUD->BLE and fresh Cloud images did not return before the80s deadline.
  USB38/38 passed, max306.58ms; ToF continued, SPI/allocation failures0.
- Second profile explicitly read the BLE image CCCD0100 and toggled its image
  subscription on/off to confirm0000 before the Cloud baseline. It still failed:
  radio/Wi-Fi returned17984ms, then CLI subscription was off while image
  subscription was on and destinationBLE. USB37/37 passed, max387.5ms.
- Third profile also retired the old Windows GATT client immediately after fault
  admission, before NCP reinitialization. Radio/Wi-Fi recovery16219ms, Cloud
  accepted images7859->7869 and CLOUD destination returned without MAP ON.
  Fresh BLE reconnect then found image CCCD0100; the harness explicitly cleared
  it to0000, which itself requests BLE then releases it, leaving destinationNONE.
  Its assertion that the final destination still be CLOUD failed. This is not
  proof that a purely CLI-only reconnect changes the destination: the reconnect
  cleanup performed actual image subscription changes. USB9/9 passed,
  max307.67ms. Genuine-fence status3/fence1 was captured for all three probes.

The third fresh BLE session received actual sequence5/old_generation13
UNKNOWN/rx0/tx4/active0. Six new PONG/final pairs passed, with exactly six new
complete markers and no old HELP banner; twelve total BLE ping finals passed in
that profile. This proves interruption of queued reply transmission and a
delivered new-generation notice; it does not prove the CLI handler was still
executing. Replies are assembled before notification: remote accepted alone
cannot prove `reply.active`. Total across the profiles:24 BLE ping finals and
84 USB pings; no old command was replayed by the host.

First baseline NCP attempts/ready1/1 became final5/5, failed0. Only three explicit
fault submissions were made. The additional recovery occurred between the second
and third captured baselines; its cause/terminal was not captured and stays
UNCLASSIFIED. Request errors0->2/drop1 unchanged; SPI fault and radio allocation
failure counters remained0. Do not erase these observations or infer an SPI
electrical cause from them. Windows subscription restoration/GATT identity is a
candidate explanation for the descriptor behavior, not a proven root cause.
The existing last-request-wins policy treats an actual image CCCD enable as a
new BLE destination request; no firmware defect/fix is established by this run.

Fresh read-only immutable SRAM audits before/after match reader05FD9EFD...;
managed record remains slot0/gen1/flags31/705/CRC72B6B9AF, writes/arm/busy/io0,
loaded1/calls4. Final fence/drain/notify/recovery0, saved-reference Wi-Fi ready,
Cloud still paired. No source edit/build/RAM load/MCU reset/Flash/credential
mutation/re-pairing/deployment. All USB/UART/collector/BLE handles closed.
Cloud MAP ON and `debug ping combined-final` completed in the retained IAB
workspace after cleanup. Final Cloud status polling/paired/HTTP200/transport0/
backoff0, accepted images8267/drop1/request errors2; rendered browser frame323844
CRC B1C8D8E5. The measured4501ms cumulative worker maximum is not latency
acceptance. Summary: combined-active-retired-host-20261012/terminal-summary.json;
chat visualization screenshot: `combined-final-cloud.jpg`.

Ignored evidence: combined-active-preflight-20261012 and combined-active-final-
20261012/inspection.json; report.json and run_once.py in combined-active-
20261012, combined-active-followup-20261012 and combined-active-retired-host-
20261012. Physical in-flight DMA abort/cancellation, executing-handler recovery,
unattended Windows reconnect, the unclassified extra recovery and fulltask4
latency/endurance remain open. No fourth forced fault is warranted before
isolating the host subscription restoration behavior.

## Existing Cloud workspace restored and verified (2026-10-12)

The Cloud authorization blocker is resolved for the current session. Read-only
USB status confirmed the device remains paired to the existing workspace. Its
matching downloaded workspace file had an empty device list. An ignored restored
copy adds only the already-paired N6-MAINT-B8FB device; all other fields, including
the existing signed token, remain identical and the original file is preserved.
The user explicitly approved opening this copy at the existing Azure N6 site.
Automated file opening first failed approval review, then after explicit approval
failed the browser tool's workspace-root check. The user opened the copy manually
in the in-app browser. No token value was displayed or included in evidence.

The UI reports RELAY CONNECTED and the device became online after its existing
30-second workspace-inactive backoff. `debug ping workspace-restored` returned
PONG plus `[CLI-RESULT] state=complete`. Cloud `MAP ON` explicitly restored
the CLOUD destination and also returned complete. The earlier attribution to
USB DTR-close was not established: that policy releases only USB publication,
not a selected Cloud route. Independent browser reception
and rendering now show LIVE Depth 54x42 frames advancing: 306373/E849F8C9,
306609/BF0BF812, 306686/21DAD22C and 306880/5718A143. These are displayed frame
IDs/CRCs, not a throughput/endurance measurement.

Cloud `cloud status` returned a matching completion: polling/paired, HTTP200,
transport0/backoff0, frames6060->6190, dropped1 unchanged, request errors0.
No re-pairing, token rotation, new workspace, firmware edit, build, reset, Flash,
power interruption or deployment was needed. USB handles are closed; the user
workspace remains open in the in-app browser. Ignored summary:
`.local-dependencies/diagnostics/workspace-restore-20261012/summary.json`.
Screenshot: the chat's visualization directory, `cloud-restored.jpg`.

This closes only the workspace/Cloud prerequisite. Combined active BLE CLI/DMA
fault injection and full task4 are still NOT RUN in this follow-up. Natural SPI
causality, physical power-loss durability and latency/endurance gates stay open.
Earlier blocked and failed checkpoints below retain their original outcomes.

## Combined-load preflight blocked on Cloud authorization (2026-10-12)

The user approved the bounded sensor/Cloud/BLE CLI/DMA recovery test. No forced
fault was injected because active Cloud failed its prerequisite. Exact immutable
SRAM matches protected reader05FD9EFD...; metadata storeOK/gen1/flags31/705/
CRC72B6B9AF/writes0, saved-reference Wi-Fi IP and fence/drain/recovery0 remain
valid. Cloud stays paired but ERROR/HTTP403/transport0; accepted images stopped
6060. This does not prove loss of local pairing.

One runtime `cloud reconnect` reused existing pairing without persistent mutation
and still returned403. Dropped frames0->1 while retiring the pending lease; no
new accepted upload. Server source maps403 to device_not_allowed,409 to inactive
workspace and401 to invalid authentication. The live response body was not read:
membership is a source/status inference, not captured JSON. User was asked to
check RELAY CONNECTED and the correct updated existing workspace containing the
device. No workspace credential file, code or token payload was read/transmitted.

The first BLE failure is retained: sandbox scan saw N6-MAINT, but automatic/public/
random connections all returned DeviceNotFound before commands. Normal Windows
device access then connected transiently with pair=False/uncached GATT/MTU247.
Six real BLE PONG/final pairs pass, max125ms; OS paired flag observed, no Pair API
or new bonding request. CLI RX6 events/120 bytes, TX9 messages/1195 bytes; drops,
retries/errors0. Client and subscription disconnected on exit.

SPI5 data above8 bytes selects GPDMA1 TX channel10/RX channel11. Real BLE data
uses this verified code path; it does not prove DMA was active at a fault or
DMA abort/cancellation/in-flight reply UNKNOWN/no-replay safety. Combined HIL
is NOT RUN, not replaced by mocks or earlier separate recovery tests. Existing
soak runners' password/warm-connect/unreachable-network mutations were excluded
from this read-only preserved-settings scope.

Final ToF58337->58348/ready, Wi-Fi IP/radio available, BLE disconnected/advertising,
NCP1/1/0 unchanged, Cloud paired/403/stopped6060, drop1, USB ping PASS. COM8/BLE/
WinRT and prior COM6/SWD handles released; no active test/build. No firmware code,
build/Flash/reset/power-cut/old-file/CWCRED/HTTP/TLS/commit/push/deployment change.
No proven firmware defect justified a fix. Prior44 native/91 feature/build checks
retained, not rerun. Combined test/fulltask4 remain open pending active Cloud.

Ignored evidence: combined-preflight-20261012/inspection.json and combined-
recovery-20261012/{ble-sandbox-failure.json,ble-transient-preflight.json,
cloud-reconnect-once.json,final-health.json,terminal-summary.json}.

2026-10-11 build-only settings extension: see [unified NCP settings](unified-ncp-settings.md)
for the new guarded Wi-Fi/Cloud format and ownership integration. Writes defaultOFF,
legacy files/credentials and missing-byte blocker remain unchanged. No RAM HIL of
the new3575B8A7... candidate occurred; prior recovery checkpoints below retain their
original candidate identities and do not validate the new storage path.

2026-10-11 terminal follow-up: four controlled genuine missing-response probes
pass (`status=3 genuine_fence=1`), coordinated recovery20011/19968/20000/20792ms,
saved-credential IP return,573 CRC records/28 USB pings and no ToF recovery.
The original longer campaign FAILED on ordinary Wi-Fi loss while ToF/USB lived;
the existing control owner now restores confirmed ordinary loss with retained
saved intent, without healthy-NCP reset. User cancellation/queued work/DHCP/
unconfirmed state/true fences/owned DNS or BLE notification prevent submission;
max3 calls,10s completion cooldown, original SDK deadlines and capacities.
Two ordinary no-reset gates pass; an unsolicited loss restores with2687ms
association call, ToF/USB and NCP baseline unchanged. RF/AP/NCP cause unproven.
Eight static bytes, no new task/steady allocation; unsigned4D953D64...,
binary487952/heap383792/header9,33 native/24 feature/build-only pass. Selected
mixed-candidate ToF coverage7263.641s/22653CRC/16 faults/12 pauses passes;
original FAILED preserved, no full task4/active BLE CLI-DMA/Cloud return accepted.
Final ToF/Wi-Fi/USB/radio healthy, BLE adv/disconnected, imageNONE/Cloud unpaired;
UART2021/2021 zero drops/errors, all owned handles released. Radio max gap269ms,
BLE pump20820ms includes recovery, not latency acceptance. Strict FS bytes/CRC/
fence and UNKNOWN integrity remain; no Flash/config/auth/header/sign/package/
HTTP/TLS/commit/push/deployment. See [terminal evidence](tof-desired-state-recovery.md#longer-campaign-terminal-continuation-2026-10-11).

Tasks 3–4 are in progress. The implementation and focused hardware recovery
are present; full delivery/latency/endurance acceptance is still open. Earlier
failed reports remain evidence. Earlier candidates were RAM v10; the current
unsigned task-3 follow-up preserves header v9 and leaves Flash unchanged.
No CubeMX generation is required, and no queue, stack, radio pool or image
snapshot capacity was increased.

## Cloud startup investigation - 2026-10-10

### Saved-pairing follow-up and terminal blocker, 2026-10-11

Reconciled the existing dirty `ble` checkout at `d89a510` with the healthy
unsigned4D953D64... RAM checkpoint. No competing Python/HIL/programmer/build
process was found. No firmware implementation changed in this follow-up: the
current production read already requires all1172 original bytes, original
whole-record CRC/schema, one original2000ms scope, output retirement and a
retained genuine fence. It neither repairs nor deletes a failed saved record.

The logical command matches the official host1.3.0 implementation and
[NCP2.0.106 FS semantics](https://applist67.github.io/Web_AT_Documentation_ST67/v2.0.106/index.html#at-fs):
type0/LittleFS, operation3/read, filename, offset and length. Both request and
reply use the AT traffic queue0; no documented separate FS binary channel or
logical hex/checksum operation was found. The previous public-offset5 probe
already saw an empty13-byte reply before buffer pull/resize, with exact host
copy. No new saved-file payload read or reconstructed-byte experiment was run.

Added `hil_tests/test_spi_fs_framing.py`, which compiles and executes the actual
`spi_xfer_one`, header validation and buffer helpers. Mocked byte transfers feed
the header-first/remaining-transfer paths, alignment and short-buffer resizing.
Real-NUL14-byte and absent-payload13-byte public replies remain distinct across
11 TX sizes. Another132 TX/RX length combinations preserve all256 byte values
through the1520-byte MTU. Two failed small-buffer allocations retain exact
original packets; two transfer failures publish no partial packet and release
RX only after successful local abort. All158 scenarios pass. This is host
framing evidence, not DMA/electrical/NCP-storage proof. An initial test-harness
preprocessor newline failure was corrected; its failed log is retained.

The three actual-C parser/lifetime/pairing regressions also pass, including
strict empty+OK rejection,32-bit length, original CRC and actual nonzero
tails/padding. No new firmware build/feature matrix was required or run; prior
33-native/24-feature/build results apply to the unchanged exact ELF, not to a
new candidate. Only the four focused host test files were run in this follow-up.

**Smallest remaining blocker:** a validated NCP2.0.106 binary-safe logical-file
read/response contract that supplies the complete original record. An independent
NCP-local CRC can resolve storage integrity but cannot alone load the missing
pairing bytes. Current AT FS omits a declared public byte; size/partition/command
availability metadata cannot supply or certify it. `AT+CMD?`/`AT+PART?` were not
run: discovering command names/layout does not provide a validated logical read
encoding or safe physical-file mapping. The generic vendor AT API exists but no
raw AT path is exposed by this application. No temporary interface/RAM reload
was added merely to repeat metadata that cannot resolve that dependency.
Physical FLASH-R-HEX mapping, lock permission and credential exclusion remain
unknown. No raw Flash read, address guess, unlock, credential/token transfer,
record mutation, re-pairing or ST contact occurred. The separate FAE project was
not touched. Requesting the vendor's logical FS binary response specification
or corrected implementation is the next useful dependency; no action has been
sent on the user's behalf.

Connected Cloud -> genuine NCP fault -> restored Cloud HIL is **BLOCKED / NOT
RUN** because the board remains unpaired. A fault test on that state cannot
accept connected Cloud restoration; prior Wi-Fi recovery passes remain valid.
Final read-only status: ToF114793->114834, ready, recovery8/8/0/gen8 unchanged;
Wi-Fi IP ready, USB/radio ready, BLE advertising/disconnected, imageNONE,
Cloud unpaired, NCP recovery3/3/0 unchanged, SPI faults/allocations0,
UART7085/7085 zero drops/errors. The collector closed COM8; no COM6/debugger was
opened and no test/build process remains. WMI process enumeration was denied;
ordinary process enumeration completed without those active processes.
Current ELF and retained candidate hashes both remain
`4D953D643096FFF95E7013FEB21E311220C7D0622783EB6A9C4B3CA914B962C6`.
Header9/Flash unchanged; no signing/package, HTTP/TLS, commit/push/deployment
or task4 endurance work. Evidence and failed fixture log are under ignored
`.local-dependencies/diagnostics/cloud-fs-resume-20261011/`.

### Official read-only diagnostic lead, 2026-10-11

The [official ST wiki](https://wiki.st.com/stm32mcu/wiki/Connectivity:ST67W611M_AT_Command)
links to the version-specific
[ST67 AT2.0.106 documentation](https://applist67.github.io/Web_AT_Documentation_ST67/v2.0.106/index.html#at-flash-r-hex).
`AT+FLASH-R-HEX=<nbytes>,"<address>"` is documented to return hexadecimal data
for1..8192 bytes at a physical Flash address. `AT+CMD?` lists supported command
types, and `AT+PART?` returns partition names, addresses, lengths and update
metadata. These are availability/layout leads, not a logical-file reader.

The documentation does not establish this device's lock-state permission, a
safe logical LittleFS filename/offset-to-physical mapping, or exclusion of
credential material from a physical range. Partition metadata cannot identify
the current file blocks or establish that they are safe to inspect. No
independent FS checksum command was found in the inspected command reference.
The FS section documents logical LittleFS operations but supplies no validated
binary/hex read encoding that explains the existing absent-NUL response.
Device availability/partition queries were not executed: this exact application
has no exposed raw-AT menu path; the vendor shell/API exists in source but is
not the application's CLI. Adding a temporary raw interface does not solve
file mapping or credential exclusion. No raw address was guessed/read, no
unlock/security/provisioning command was issued, and no credential dump occurred.

The local host driver identifies as1.3.0, and UART reports NCP SDK2.0.106.
[ST's V1.3.0 release notes](https://github.com/STMicroelectronics/x-cube-st67w61/blob/main/Release_Notes.html)
include P67W61-738, an SPI TX-length versus allocated RX-buffer overflow fix.
The current AT bus caller uses `SPI_MSG_OP_DATA`; `spi_write` bounds its data
length to the MTU, RX allocation includes that MTU plus the SPI header, and
peer-header length is checked against the same MTU. Those checks also appear
in the local vendor1.3.0 source. This is a source/version comparison, not a
reproduction of every overflow path or proof that the historical defect never
occurred. The public FS probe's received13-byte packet and exact host copy do
not establish a causal connection to P67W61-738. Its relevance remains unproven;
the missing NUL is still an upstream malformed response at the observed boundary,
with stored-record integrity UNKNOWN.

The strict exact-byte count, original whole-record CRC/schema, original2s
budget, borrowed-output retirement and genuine fence remain unchanged. The
next useful evidence is ST's binary FS response implementation/validated
encoding, an independent on-NCP checksum or binary-safe logical-file read,
or a vendor-established safe mapping/security contract. None is supplied by
partition metadata alone. Cloud pairing/restoration remains blocked; no saved
record repair/re-pairing, HTTP/TLS change or Flash operation is justified.
Downloaded official HTML, its hash/provenance and the comparison notes are
retained under ignored `.local-dependencies/diagnostics/tof-longer-20261011/`
(`st-at-2.0.106.html`, `st-fs-lead.json`).

### SPI-boundary diagnosis and strict binary fix (latest)

Earlier conclusions about an invalid **stored** record are withdrawn. The legacy
reader and tail audit inferred NUL from empty+OK and, initially, guessed string
tails. A CRC failure over those transformed values does not distinguish corrupt
storage from a corrupt/undefined read representation. The143 nonzero-tail count
and failed CRC are retained observations of that decoder, not an independent
filesystem integrity check. No claim of stored-file corruption is justified.

A bounded, public-offset-only RAM probe locates the missing byte before host
parsing. Expected ST-LINK and no competing HIL/debugger were checked; the healthy
39116974... board snapshot/ELF was saved before reset. The probe examined only
file offset5, the version-high byte expected to be NUL0x00 for a valid version1
header. It did not examine credentials or expose file values. Before SPI buffer
pull/resize/queue publication, it compared the received AT packet against fixed
public response shapes and recorded peer header length. After the retained-packet
copy, it recorded byte-for-byte equality; at the direct callback it classified
the accumulated buffer. Formatting occurred only in the FS caller; SPI/RX code
captured scalar flags without allocation or formatting.

Exact RAM observation:
`peer_len=13 raw_seen=1 raw_len=13 raw_empty=1 raw_nul=0 copy_seen=1 copy_equal=1 parser_seen=1 parser_len=19 parser_empty=1 parser_nul=0`.
The received packet is11 bytes of `+FS:READ,1,` plus2 delimiter bytes; there is
**no payload byte**, although the FS response declares1. The parser later has
those same13 bytes plus6 bytes of terminal OK. Host copying did not delete NUL.
The defect is a malformed binary FS reply **as received at the SPI boundary**,
upstream of host parser interpretation. The probe did not capture electrical
signals or NCP filesystem internals: it cannot prove the actual stored byte,
the NCP's formatter implementation, or whether storage itself is intact.
The expected NUL refers to value0x00 at offset5, not a byte at offset0.

The proven host defect was accepting a delimiter as the missing byte, followed
by an unvalidated empty-to-zero workaround. Both are closed: complete empty+OK
now reports an error, leaves output untouched and fences admission. No inferred
zero, tail or padding can become pairing data. A returned terminal cannot clear
the fence. The original single2000 ms binary read, complete copied-length proof,
output-pointer retirement and full original CRC/schema validation remain. The
FS declaration is32-bit so65544 cannot wrap to8 and be falsely accepted.
Production reads all bytes exactly or scrubs volatile output and rejects the
load; it neither rewrites nor deletes the saved record. Temporary SPI/copy/parser
probe code was removed after capture; ordinary SPI transport is unchanged.

Native regressions execute the actual retained SPI-to-parser read, explicit
collector count and direct FS callback using synthetic packets. Embedded NUL,
all256 byte values and33 destination-room boundaries preserve every byte and
packet ownership; empty+OK is rejected. These tests do not emulate DMA or NCP
storage. Pairing tests require exact complete binary data, preserve arbitrary
actual tail/padding bytes, check original CRC/schema and scrub every partial
failure under one original budget. All31 native files/16 feature compiles/build
pass. Final unsigned ELF:
`31010048FB2DCA41377E34FC702E6836F69EE8659C127B30F6A455BA07BB0B70`;
binary486632, heap385112 (minimum368640), header9. FS caller frame288/callback40
bytes are compiler frames, not worst-stack proof. No capacity/task/steady-state
allocation or HTTP/TLS budget change. Earlier failed native test-fixture setup
attempts remain in the ignored evidence, followed by passing retests.

Probe ELF4A1DE821... rejected the malformed response without changing the output;
genuine fence recovery15977 ms completed while ToF frames advanced. Cloud remained
unpaired. Clean final RAM reload then reproduced the known warm ToF I3C dynamic-
address startup failure (frame0). The full FS read recorded declared1172,
assembly27/copied0, original2000 ms timeout/fence1, and no reconstructed input.
USB/Wi-Fi remained usable: five pings and saved-credential IP restore recorded,
but this failed sensor boot is not a full recovery/latency PASS. Short firmware
recovery timings214/386 ms from this warm boot are not promoted to acceptance.
Last captured board: final31010048... RAM, radio/USB ready, Wi-Fi IP, BLE
advertising/disconnected, imageNONE, Cloud unpaired, ToF error/frame0. All host
handles released. Full physical power removal/reconnect requested to restore a
healthy sensor boot; confirmation pending, existing RAM permission valid.

**Terminal diagnostic blocker:** AT FS is the sole available local view of the
saved file, and it has just demonstrated missing binary data. Repeating its
reads, using its size query, rebuilding CRC over inferred bytes, or re-pairing
does not distinguish storage from the read defect. Need an independent on-NCP
file CRC32/binary-safe read interface, or ST's FS read/response implementation/
validated binary encoding for NCP2.0.106. It can return only integrity metadata;
credential disclosure is unnecessary. If physical transport is disputed, a
logic-analyzer capture of this same public offset can independently confirm the
received frame. No documented empty-to-NUL encoding or independent file checksum
was found in the available host SDK. ST publishes NCP images in its
[binary package](https://github.com/STMicroelectronics/x-cube-st67w61/blob/main/Projects/ST67W6X_Scripts/Binaries/README.md);
host code is not evidence of the closed NCP formatter. No configuration repair,
re-pairing or NCP flashing is justified by this evidence or authorized here.

Cloud restoration remains blocked/unverified. No persistent credential/config/
auth/Flash/header write, provisioning, HTTP/TLS modification, signing/package,
commit/push/deployment or endurance run occurred. Evidence:
`.local-dependencies/diagnostics/task3-fs-boundary-20261010/`.

### Earlier legacy decoder/audit checkpoint (superseded)

### Final legacy RAM validation and stored-record audit

The inferred-byte audit below cannot establish actual stored contents or stored
CRC corruption. Its conclusions are limited by the latest SPI-boundary finding.

The second physical power cycle was confirmed by the user. No competing HIL or
debugger was active. Expected ST-LINK000C00344142501620353451 was identified;
approved RAM loads reached ThreadX with no external-NOR programming. The logger
initially found no `serial` in the default Python314 runtime; switching to the
existing `training/.venv` succeeded before loading RAM, so no boot capture was
lost. Dirty `ble`/d89a510 and unrelated edits/processes were preserved.

The previously omitted byte is the **NUL value0x00 at file offset5** (the sixth
magic/version byte), not a byte at offset0. Five/six-byte public-header probes
and the one-byte offset5 probe locate the failure in the binary FS-read path.
The old `on_cmd_fs_readfile` accepted a CR delimiter as a one-byte payload;
whole-record reads instead waited for bytes that never arrived. The host SPI/RX
path uses explicit packet lengths and `memcpy`, not `strlen` for payload. This
supports an NCP FS-output limitation; no raw electrical SPI capture or NCP
firmware source was inspected, so the internal NCP function/cause is unproven.
It precedes HTTP/TLS work.

Exact first legacy candidate1E4B968F... completed329 one-byte reads within its
original2000 ms scope and ToF was ready/advancing, but pairing was rejected.
Boolean-only diagnostics establish magic/version/length/terminated strings all
valid, **CRC invalid**. The reader now reads the ABI padding/footer exactly
(330 reads), retaining canonical-zero string tails and the original CRC/schema.
Padding was not the cause: CRC still failed. Final unsigned ELF is
`39116974A8322069A7D0939EFBEC9171127BA09FE8CD0FA342F637E8A85B573F`;
binary486808/C heap384952 (minimum368640), unchanged header9. All30 actual-C
files,16 feature compiles, build/memory contracts pass. A nonzero ABI padding
fixture is preserved exactly; corrupt/noncanonical string tails still reject.

A temporary on-device diagnostic then read all842 skipped string-tail bytes,
in separate bounded read-only audit requests, after the failed restoration.
Together with330 original reads, all1172 file bytes were examined inside the
firmware, with no file values/token/credentials exposed to host tools. Metadata:
`result=0 calls=842 nonzero_tail_bytes=143 full_crc_ok=0 stored_crc_nonzero=1`.
Thus the complete record **as returned by FS** fails the existing version1 CRC,
even without assuming zero tails. This is not proof of where/when storage or
NCP output became incorrect. No attempt was made to repair/rewrite the file or
accept a weaker checksum. The extra audit did not admit pairing or renew the
production restoration budget. Its source/ELF/UART are retained; temporary code
was removed, and the final rebuild reproduces the exact39116974... ELF.
Audit ELF: `C4169C8F6C068BC20DA850C7D2DC57A5F200EF925F604D51481B9CB34C0CC58D`.

Focused recovery on the final39116974... image passes independently of the
unpaired Cloud state: RAM-only non-secret desired-SSID/connection intent fixture
after MCU reload uses existing NCP credentials, with no password/CWCREDADD or
stored configuration write. Explicit recovery17781 ms/20 USB pings restores IP.
Connected-BLE genuine missing-response injection recovers in19969 ms (firmware
19511), with23 USB pings and advancing ToF frames3247/3292/3336/3381/3425/3462.
Automatic saved-credential Wi-Fi restoration passes; host sends no connect or
password. All38 BLE finals arrive, p95/max156 ms,13 CRC-valid BLE images,
one interrupted assembly at recovery, zero CRC errors. Actual sequence2 UNKNOWN
notice received; active_reply=0, so in-flight-command HIL remains open. No natural
SPI fault or allocation failure observed. SetConnParam status2 observations are
retained; this is not zero-driver-error acceptance. Radio max gap21 ms; BLE pump
gap19537 ms includes recovery and must not be presented as ordinary21 ms latency.

Cloud pairing load is **FAIL**, and actual server-received images/Cloud restoration
are **NOT RUN/blocked** by the invalid FS record. IP readiness, completed reads,
BLE images or a successful reset do not close this gate. Broader endurance,
DMA-abort/partial-init fault HIL and worst-stack claims remain outside this run.
Flash/header, credentials/configuration, HTTP/TLS, signing/package, provisioning,
commit/push/deployment were unchanged. Current evidence and final-board capture:
`.local-dependencies/diagnostics/task3-cloud-legacy-20261010/`.

Final cleanup reload runs the exact39116974... image with the audit removed.
RAM-only Wi-Fi intent restoration completes18610 ms/21 USB pings (firmware
17430 ms; saved-credential association2617 ms). Final capture: ToF ready with
frames1295 then1321, Wi-Fi IP, BLE disconnected/advertising, image NONE, Cloud
unpaired/HTTP inactive. UART195/195, zero dropped/errors in this final boot
snapshot; this does not erase prior driver errors. COM6/COM8/BLE/debugger handles
released, with no remaining Python/GDB/programmer test process. No further board
availability approval is pending. A valid saved pairing source is required for
the remaining Cloud gate; no configuration repair/re-pairing was authorized here.

### Earlier cold follow-up (retained)

### Cold follow-up and read-only legacy candidate

The user confirmed a full physical power removal/reconnect. ST-LINK recovered,
and sliced candidate `75525ECB0DC9D084CBE5F5BE756CF85977102114093BDD401B6A8A2F5F02FE69`
was loaded into RAM. ToF initialized and continued producing frames. The first
256-byte FS read still failed: declared256, assembly26, copied0, elapsed2000 ms,
fence1. Automatic coordinated AT_FENCED recovery completed in15199 ms while ToF
continued. **Slicing did not fix pairing restoration**; Cloud remained unpaired.
The earlier blocked-USB checkpoint below is historical, not the current blocker.

A temporary diagnostic used only the six public magic/version bytes. Reads of
five and six bytes both returned assembly18; the first five matched, but the
sixth expected NUL did not. Reading only that NUL returned declared1/assembly13
and the old callback copied a response delimiter. Only validity booleans and
lengths were logged; no file payload, token or credential was inspected by host
tools. This proves binary round-trip failure for NUL in this NCP FS response.
The NCP's internal implementation remains an inference, not inspected source.
The temporary probe was removed; its ELF/source/UART evidence is retained.
Its warm RAM reload reproduced the known ToF I3C dynamic-address failure.

The replacement candidate reads each meaningful byte of the existing version1
record. The driver decodes an omitted NUL only from a complete, declared-one-byte
empty record followed by correlated OK; partial responses/timeouts never imply
zero. It leaves OK to the ordinary terminal owner. Real CR/LF/NUL/non-ASCII bytes
are distinguished using the payload delimiter. The existing writer zeroes string
tails/padding, so the reader reconstructs them in existing storage, then requires
the original whole-record CRC and schema/length checks before accepting pairing.
An unexpected tail/padding, unterminated string, timeout or corrupt CRC fails
closed and scrubs volatile state without deleting the saved file. One original
2000 ms scope covers the byte reads; it is never renewed per byte. The size query
retains its existing separate operation. Save verification reuses the reader;
no persistent write path or file format was changed or exercised on hardware.
Successful one-byte scalar logs are suppressed to avoid flooding UART; failures
and aggregate read status/call count remain visible, without payload values.

Actual-C regressions cover both empty-record forms and every partial boundary,
real delimiter/binary bytes, ERROR without OK, original CRC, enabled intent,
invalid schema/strings/tails/padding, every partial failure and one shared budget.
The build passes: binary486464, C heap385304 (minimum368640), header9; unsigned ELF
`1E4B968FE2A3EDAB913529EAD62A350B4042ABDBB21EB5573FCB1BD520997A47`.
Compiler frames are FS caller288, callback64 and legacy reader48 bytes; these
are individual frames, not worst-stack proof. No new buffer/task/capacity or
steady-state allocation was added. This legacy candidate has **not been loaded**.
All30 native test files and16 feature-mode compiles pass, with zero failing files.
`git diff --check` passes (existing CRLF conversion notices only). Focused RAM
validation of this exact legacy candidate remains NOT RUN; Cloud restoration is
not accepted. Native compiler conversion/deprecation warnings and the existing
linker RWX warning are retained in logs, not silently presented as warning-free.

The final captured hardware state is the header-probe RAM image: radio/USB ready,
BLE disconnected/advertising, Wi-Fi disconnected, Cloud unpaired, image NONE,
ToF dynamic-address error/frame0. A second full physical power removal/reconnect
was requested for a healthy cold RAM test; confirmation is pending. Existing RAM
approval remains valid. All UART/USB/debugger handles were released. The transient
execution-environment disconnect occurred between tests, with no active HIL/build;
it invalidated no completed hardware result. A later read-only enumeration again
identified the expected ST-LINK. No Flash/header/authentication/configuration write,
re-pairing, HTTP/TLS change, signing/package, commit/push or deployment occurred.
Evidence: `.local-dependencies/diagnostics/task3-cloud-cold-20261010/`.

### Earlier diagnostic/slice checkpoint (retained)

This follow-up was authorized to diagnose the unresolved startup pairing-file
read without reading credential values through host tools, re-provisioning,
changing saved configuration or expanding HTTP/TLS/endurance scope. Existing
RAM reset/load approval remains valid. The dirty `ble`/d89a510 checkout was
preserved; no other Python/GDB HIL process was active at the initial check.

Diagnostic firmware adds only FS callback count/length scalars; formatting is
in the calling task after the operation, never in SPI/IRQ/parser callbacks.
The approved RAM load reached ThreadX. On this repeated startup, the file-size
query succeeded and requested read length was1172. UART records:
`result=3 elapsed_ms=2000 requested=1172 callbacks=2 declared=1172 available=27 copied=0 fenced=0`.
These are metadata only; the payload was never logged or dumped. Startup ignores
the failed load result, clears volatile pairing and marks Cloud initialized,
so a transient file-load failure cannot be retried via the current reconnect
command. The response assembly is incomplete; the evidence does not yet settle
whether NCP file-output limitations, binary truncation or another transport
issue caused the missing bytes. It is not evidence of an HTTP/TLS timeout.

The candidate follows the existing SDK file comparison's256-byte reads instead
of requesting the entire record at once. One existing2000 ms request scope
includes all slices, without a fresh budget per chunk or additional buffers.
The record is assembled in the existing destination, then passes the original
length/schema/CRC validation. A partial failure scrubs only the volatile record.
The same reader is used for save verification; the persistent write path and
record format were not changed or invoked during this work.

FS read now publishes the expected output length, rejects a mismatched complete
payload, requires copied-length proof even after OK, and retires the borrowed
pointer before releasing AT ownership. Submitted unanswered reads fence the
transport; pre-write timeouts and definite ERROR do not create a false fence.
A true fence is never cleared here. No new task, steady-state allocation,
buffer/queue/stack capacity or HTTP/TLS budget was introduced; diagnostic scalar
metadata uses16 bytes.

All30 `hil_tests/test_*.py` files and16 feature-mode compiles pass. New actual-C
tests cover4x256+148-byte binary assembly, shared-budget expiry, partial-failure
scrub, FS output retirement, late callbacks, wrong lengths, missing payload and
raced terminal OK. Build/link/memory contracts pass: binary486216 bytes,
C heap385528 (minimum368640). FS caller compiler frame280 bytes, callback40;
these are individual frames, not worst-stack proof. Existing linker RWX warning
and native legacy numeric-conversion warnings remain recorded.

The proposed fix has **not** been validated on hardware. Its next loader failed
before SRAM replacement with `DEV_USB_COMM_ERR`; read-only programmer enumeration
also failed with no probe identity, including approved normal device access.
No other GDB server was left running. A full board power removal and ST-LINK USB
reconnect was requested; no user confirmation of that physical action arrived
during this checkpoint. This is the immediate blocker, not a new RAM/pairing
permission request. Do not claim sliced reads fix the file-read failure or that
Cloud was restored.

Identities:

- Loaded diagnostic ELF:
  `B6C38878DCC0A75D0AF4519E3F0EA5FDE03A04155FFC98AABE61E9046F180974`.
- Built/unloaded slice/lifetime candidate:
  `75525ECB0DC9D084CBE5F5BE756CF85977102114093BDD401B6A8A2F5F02FE69`.
- Both preserve version header9. The external Flash v9 installation was not
  changed; a changed RAM program reporting9 does not mean it was Flash-installed.

Final USB capture: radio/USB ready, BLE disconnected/advertising, Wi-Fi
disconnected, Cloud not paired, image NONE. The diagnostic warm RAM reload
reproduced the already documented ToF I3C dynamic-address startup failure
(frame0), independently of the proposed sliced reader. Sensor/Cloud image HIL
cannot proceed in this state. COM6/COM8 logger/CLI and debugger handles were
released. No credential values were inspected, no new authentication/pairing
performed, and no saved file, Flash/header, provisioning, signing/package,
commit/push or deployment operation occurred. Restoring normal Wi-Fi/ToF state
still requires the blocked cold RAM reload and prior non-secret intent fixture.

Ignored evidence: `.local-dependencies/diagnostics/task3-cloud-20261010/`
contains diagnostic build/ELF/load/UART, failed sliced load and its unrelated
old-board UART, candidate ELF/build, native results and individual logs,
feature results, final USB status and summary. The earlier exact-ELF successful
focused recovery remains valid for its checkpoint and does not validate this
new candidate.

## Task 3 host follow-up - 2026-10-10

The checkout is `ble` at `d89a510`, with the coordinator, desired Wi-Fi restore,
SPI/parser stop checks and Candidate F diagnostics already present as dirty
work. No local `.agents/skills` directory was found in this checkout or its
examined ancestors. No Python HIL, compiler or ST-LINK process was active at
inspection; CIM command-line enumeration was denied, so unrelated Node tasks
were left untouched. The prior F hour report and its cleanup runner already
exist with `passed=true`/`test_exit_code=0` and verified Cloud return. Those are
previous-candidate evidence; no task 4 profile was started or rerun here.
Older pending-hour notes below describe the earlier checkpoint and do not
validate this changed build.

Two gaps were reproduced using actual pre-fix C in a temporary host harness:

- A late old-parser CONNECTED record revived the retired BLE generation;
  a following old ToF CCCD record could change the exclusive image route.
  Recovery now ignores old-parser events until teardown finishes. During
  fresh initialization, new connection/MTU/subscription observations remain
  accepted for automatic client reconnection, while writes and application
  RX/TX/reply admission stay closed until restoration completes. A failed
  recovery keeps all of these admissions closed.
- Uptime zero was used both as a valid START time and an unstarted sentinel.
  With an owner still pending, START and Cloud pause repeated at the next
  Radio pass and moved the original deadline. The existing lifecycle stage
  now marks START; a request resets that stage explicitly. A 35 s wait starting
  at HAL tick 0 fails closed on its original deadline.

Reply reservations recheck recovery and generation after acquiring the existing
slots, then return all slots if admission changed. Direct TX retains the
original generation across its bounded slot wait, and cannot label old output
with a replacement link. RX rechecks after dequeue and returns a raced slot
before delivering bytes to the parser. Old reply final publication is rejected
even in the interval before Radio advances the generation. No new task, queue,
buffer, steady-state allocation or time budget was introduced. HTTP/TLS and
the companion web project were not changed in this follow-up.

Verification: all 28 `hil_tests/test_*.py` files pass, including the new
`test_ble_recovery_barrier.py` and additional reply-lease/dequeue/tick0 races.
All 16 existing feature-mode syntax checks pass. The supported
`Tools/Build-NonSecureIncremental.ps1` build/link and image/memory contracts pass:
Non-Secure binary 485504 bytes; C heap 386280 bytes, above 368640 minimum.
The linker still emits the existing RWX LOAD-segment warning. First native/build
attempts failed because compiler child processes could not use the sandbox TEMP
directory; retrying with process-local TEMP/TMP in workspace `tmp` succeeded.
GCC callback frame 32 bytes, reply reservation 96, stream read/write 56,
coordinator 176; these are individual compiler frames, not worst-stack proof.

Build-only ELF SHA256
`DC3BC6DD3539E1BE51C4C2C42E5BC137321A604B858F75B5812BECC9D12E5928`;
binary SHA256
`8D3D3F0326B05826B9B955369B1D5B6342F4A496FB74BB962F25F0B1220D2998`.
Tracked header 9 is unchanged. At the host checkpoint this build was neither
signed nor loaded; the approved RAM follow-up below now verifies this exact ELF.
Prior saved RAM F/v10 evidence does not validate these changes. No signing,
package, Flash/version change, provisioning, commit, push or deployment occurred.
No Generate Code is required for this follow-up.

Ignored evidence directory: `.local-dependencies/diagnostics/task3-review-20261010/`
contains `before-fix.log`, `native-results.json` and per-test logs, `build.log`,
retained `build-temp-failure.log`, `feature.log`/`feature-modes.json` and exact
build identity. Focused RAM HIL subsequently received explicit user
board-availability approval; the results and limits follow.
The natural SPI fault cause, older failed checkpoints and full acceptance gates
remain separate open issues.

## Task 3 focused RAM follow-up - 2026-10-10

The exact host-tested ELF above was loaded with
`Tools/Debug-NonSecureRam.ps1 -NoBuild -Run`; both vectors were checked and
ThreadX reached before debugger detach. No firmware change was needed during
HIL. UART/USB report firmware 9 because the tracked header was preserved;
this unsigned RAM load is separate from prior signed v10 candidate history.
No Flash operation, credential provisioning, package generation or deployment
was performed.

MCU reload intentionally clears volatile desired Wi-Fi intent. This test seeded
only the non-secret SSID and two existing intent/credential-present scalars in
SRAM through SWD, after verifying their exact ELF addresses and SRAM bounds.
The saved SSID was obtained from prior evidence. No password was read or sent,
and no CWCREDADD was issued. This fixture verifies restoration using already
stored NCP credentials; it does not repeat the successful user-connect/store
path. The initial explicit recovery passed in 18542 ms, with 21 USB pings.

With BLE CLI and ToF notifications connected, `radio fault-test` first closed
admission and waited for owners, then powered down NCP and issued the existing
bounded AT diagnostic. UART records `status=3 genuine_fence=1`. Recovery passed
in 21104 ms (host 21812 ms), Wi-Fi restored in 2665 ms with IP and without a
host connect/password command. USB 25/25 pings passed; sampled sensor frames
4594, 4639, 4682, 4727, 4769, 4815, 4826 advanced throughout. Windows restored a
fresh connection during init. The sequence-2 UNKNOWN/no-replay event was received
on the old client's restored subscription and retained alongside the subsequent
manual reconnect. 38 BLE CLI finals passed, p95 nearest-rank 172 ms/max 203 ms,
including 20 after reconnect. At least five CRC-valid BLE frames passed before
and after; 15 complete frames total, zero CRC errors. Two interrupted host frame
assemblies are retained across reset/subscription transitions.

The independent focused exclusive-route gate passed five BLE frames, five USB
dataset records and five further BLE frames, all CRC-valid. BLE packet counts
were 260 at both the first and last complete USB frame; a prior frame drained
during the initial handoff and one interrupted assembly was retained. Final
route NONE, Wi-Fi IP, BLE disconnected/advertising, ToF ready. Allocation failures
and CLI RX/TX drops were zero; UART 481/481, no drops or HAL errors. Driver errors
were not zero: initial filesystem TIMEOUT plus four SetConnParam status=2
observations are retained. SPI natural-fault count remained zero.

Two host attempts failed before any BLE command/fault injection because WinRT
could scan but could not open the device inside the sandbox. Both reports are
retained. Approved normal WinRT device access then passed both connections with
neutral automatic address type; no firmware workaround was made. COM6/COM8,
BLE and ST-LINK/GDB handles were released; both COM ports were opened/closed
again to verify release.

Current acceptance gaps:

- Cloud started unpaired after `W6X_FS_ReadFile` timed out during boot. This
  run did not provision pairing or change HTTP/TLS; actual received Cloud images
  and preserved active Cloud leases across this exact build remain NOT RUN.
- The received notice had `active=0`; this does not prove the outcome of a
  hardware reset during an executing CLI command. Race/lease cases passed native
  actual-C tests. Failed DMA abort, parser stop and partial-init failure safety
  are likewise native evidence, not injected target timing proof.
- Natural SPI/DMA fault cause, repeated boot, full latency/endurance, worst
  stack and whole-chip CPU acceptance remain open. No task 4 run was started.

Ignored evidence: `.local-dependencies/diagnostics/task3-hil-20261010/` contains
`summary.json`, RAM-load log, fixture script/RAM-write logs, bootstrap report,
connected recovery report, retained WinRT failures, exclusive-route report,
final status and full UART log. The original build-only identity remains an
unchanged historical checkpoint; this HIL summary records RAM-loaded=true.

### Engineering assessment

The coordinator provides a coherent boundary for shared transport failure:
fence/expired-drain admission, generation retirement, owner acknowledgements,
SPI/parser stop proof, power-off, fresh init and desired-state restoration.
Ordinary contention and BLE-only repair remain separate legitimate cases.
The current focused target result verifies this shared sequence after diagnostic
owner quiescence; it does not prove every spontaneous concurrency/fault case.

Remaining maintainability concerns are visible in code: recovery directly uses
vendor modem internals, and lifecycle stage, service state, BLE repair, route,
notification and Cloud pause flags are distributed through a large application
module. The callback and uptime-zero bugs fixed here demonstrate the cost of
those interactions. A later bounded simplification could introduce typed
lifecycle states and a driver-owned stop/reset proof interface, consolidating
generation/admission transitions while retaining the existing tests. That is an
engineering recommendation, not a diagnosed cause of the unexplained SPI fault
or an implemented rewrite. Establish the missing acceptance evidence before
adding more automatic retry paths.

## Ownership and trigger

Only a genuine AT fence, an expired DNS terminal drain, or an explicit
`radio recover` / `radio fault-test` requests shared NCP recovery. Ordinary
contention, a pending terminal inside its deadline, and BLE-only faults do not.
The Radio task starts the barrier and publishes scalar status. The existing
Wi-Fi/BLE control worker performs teardown and reinitialization. No new task
was introduced.

```mermaid
flowchart TD
  AT[AT fence / expired DNS / explicit request] --> R[Radio: close admission]
  R --> B[Cancel and retire notification; release wireless snapshot]
  R --> C[Cloud worker: return from scoped call, release image lease, acknowledge]
  B --> W[Existing Wi-Fi/BLE control worker]
  C --> W
  W --> L[Acquire actual AT mutex; no foreign owner]
  L --> S[Stop SPI transaction; abort local SPI5 DMA; retain memory until proven idle]
  S --> P[Stop parser before deleting subsystem contexts]
  P --> N[Power ST67 off; destroy old transport/context objects]
  N --> I[Fresh initialization; DHCP, Net, BLE GATT]
  I --> F[Restore desired Wi-Fi from NCP credential store]
  F --> E[Cloud retires old socket only after reset proof; resume preserved pairing]
  E --> O[Reopen admission; BLE client must reconnect]
```

The barrier waits at most 35 seconds for application owners. At most three
reset attempts are admitted per 60 seconds. Failed SPI stop retains its task,
stack, buffers and protocol fence; it cannot free memory still used by DMA.
Failed partial teardown/reinitialization stays closed and does not automatically
loop. A real fresh fence during Wi-Fi restoration also prevents publishing
READY. There is no shared GPDMA reset or MCU reset in this coordinator.

SPI stop uses bounded RX publication rather than an infinite queue wait. On a
failed DMA abort, the worker remains in the transfer's stack frame and retains
the RX pointer until abort succeeds. Parser-owned packet/assembly state and
all five modem synchronization objects are released only after stop proof.
Network TLS-name allocations are released before the network context.

## Desired Wi-Fi state and credentials

User explicitly authorized persistent credentials in ST67. A successful user
connection writes `CWCREDADD`; the application retains only SSID and connection
intent, clears the password working copy, and logs the store result without
its contents. AT debug tracing prints command verbs, never their arguments.
The SDK's plaintext AT command stack buffers are explicitly erased as well.

After NCP reset, `Secured=1` uses `CWJAPS` with an empty application password.
Restoration occurs in the same control worker before Cloud resumes. An
unavailable AP or missing credentials is reported; radio services can resume
without a successful network association unless the transaction genuinely
fenced. There is no indefinite connection retry loop in the coordinator.

Normal `wifi disconnect` cancels connection intent but preserves credentials.
`wifi disconnect forget` also deletes the remembered NCP credential record;
failed deletion is reported. Application connection intent is volatile across
MCU reset: this change does not choose an arbitrary stored network at boot.

Cloud pairing, enabled state and active command/output lease survive an NCP
reset. Old socket identity is retired only after hardware-reset proof. Sequenced
output may be retried with server deduplication; commands are not replayed.
Accepted old-generation Wi-Fi requests complete explicitly with failure.

USB ping/status and ToF acquisition remain independent. The exclusive image
route remains last-request-wins. A Windows client restoring a ToF CCCD makes a
new BLE route request; Cloud MAP ON must then reclaim the route. Recovery never
enables simultaneous BLE/Cloud image delivery.

## Evidence and limitations

Native regression: 25 test files passed; 16 feature-mode compilations passed.
New actual-C checks cover owner barriers, deadlines/reset budget, Cloud reset
proof/socket retention, SPI/DMA memory lifetime, parser/semaphore cleanup, and
seven credential/desired-state cases. These mocks do not prove RF or DMA timing.

Candidate E ELF SHA-256:
`00EB0BB1A03A4C79E36DF93E519E73046278125E5EB8DB0B531FDC1BD84CD2AF`.
Signed package 483904 bytes, Non-Secure binary 482608, C heap 389344 bytes.
Ignored evidence is in `.local-dependencies/diagnostics/cli-service/`.

Earlier candidate C completed five real NCP recoveries (three missing-AT
diagnostics and two genuine Cloud fences), with USB/ToF continuity. Cloud
received 371 CRC-valid frames without CRC/protocol errors. Its combined
recovery reports failed on post-reset connection/route/Cloud checks, and
required host password resubmission; they are not full acceptance.
Candidate D failed ToF startup dynamic addressing after a warm RAM reload.
Full board power-off before E restored ToF startup without an unrelated driver
change. Boot repeatability remains open.

E first diagnostic produced a genuine fence, restored NCP and Wi-Fi without
any host connect/password command, and received five new complete Cloud
frames. NCP recovery elapsed 21768 ms; Wi-Fi restore elapsed 2663 ms with IP.
USB ping remained available; Radio loop maximum gap 32 ms. The intentional
BLE outage is retained in the pump's 21801 ms maximum-gap metric.
Combined report E1 still failed on Windows GATT characteristic discovery.
A subsequent fresh uncached discovery found the complete contract and received
57/57 replies, but p95 1531 ms/max 1562 ms failed the 250 ms latency threshold.
Do not present these results as full BLE/endurance acceptance.

Tracked `hil_tests/run_radio_recovery_soak.py` runs the planned 30-minute
BLE/USB/Cloud test with ten warm Wi-Fi cycles. Password is supplied by the
environment; reports retain raw outcomes and server matching completion IDs.
It requires zero missing replies, actual CRC-valid Cloud images, all cycles,
and BLE p95 below 250 ms. Full 30-minute and one-hour failure results must be
recorded separately; older failed latency/delivery gates remain open.

Focused E4 subsequently passed on the same firmware: Windows address-type-neutral
uncached discovery (the method used by the existing inspector) replaced the
helper's forced-public discovery.36 BLE final replies including20 after reset,
p95 219/max265 ms;28/28 USB pings across recovery;five new Cloud frames in1719 ms
after the receiver checkpoint. Firmware recovery elapsed22216 ms, host observed
22562 ms; automatic Wi-Fi restore2693 ms/IP. No host password resubmission.
This single focused success does not erase E1/E2 discovery failures or the
57/57 latency failure. E3 timed out because the local Node receiver crashed
while reading a partially written command JSON, closed its Hub and made the
server return409 workspace-inactive; this was a host test defect. The receiver
now retries incomplete JSON and the command producer uses atomic replacement.
Its failures remain retained.30-minute combined run has started separately.

### Thirty-minute combined result — PASS

`recovery-run-e-next/soak-30min-e1.json`:1800.2 seconds,7726 BLE final replies,
1243 USB pings, zero missing. BLE p95 203 ms/max3734 ms; long individual pauses
remain visible. Ten Wi-Fi reconnects restored three server-received frames in
875--2609 ms after IP.3264 new CRC-valid Cloud images during the run, no CRC or
protocol errors.37 matching Cloud command completions:36 correct PONGs plus
the initial MAP ON. Three separately admitted UART bursts produced300 ordered
lines. Final UART3120/3120, zero drops/transport/allocation errors, high water24/32.
Radio max gap32 ms, allocations0, BLE RX/TX drops/retries/errors0. ToF ready with
no local recovery attempts; NCP attempts remained3 (the earlier explicit tests),
no new NCP/MCU reset in this profile. This accepts the M10.2 profile; it does not
erase the earlier failure/latency/boot/worst-stack gates.

Clean build/sign passed with the same package/binary/heap sizes. Clean ELF SHA
`481B3EEC292EC9AF2CF368C643AE9387605B0A708230CC6245591155CC6A00DC`;
the hardware continues to run the saved E ELF above. Extracted Non-Secure binary
comparison found exactly8 changed bytes, all within the model's compile datetime
string (`AppliNonSecure/AI/Model/stai_rps_tof.c:617`, `__DATE__ " " __TIME__`).
Loaded binary SHA `86A368A9FDB3707104BB37AEFFDD085A4E320E979B834C02B226E850A52F8726`;
clean binary SHA `D0BBA2F5E42E97BABB3247FD58BC4A750E18D444F93F6DFB2D79A52758BEB2A6`.
Instruction bytes and all other data match; do not call the two ELF hashes equal.

The one-hour unreachable-network profile has started on E separately using
`hil_tests/run_radio_failure_soak.py`. It uses a nonexistent SSID/non-secret
password, preserves the authorized Cloud endpoint, checks USB/ToF and BLE,
reconnects BLE every five minutes and sends four-command bursts each minute.
Radio/Cloud loop cadence is observed; whole-chip CPU utilization and worst-case
stack bounds are not measured by this host tool.

The first hour attempt (`failure-1hour-e1.progress.json`) stopped on the host:
no matching Python/Node/trace processes remained and no final report existed.
Last checkpoint was743 seconds,3010 BLE commands,552 USB pings,three BLE
connections,twelve bursts andthree unreachable-AP attempts. It is INCOMPLETE,
not PASS, preserved in `failure-1hour-e1.interrupted.json`. The board remained
responsive: USB/ToF ready, no new NCP recovery, radio pool4424 bytes/40 fragments,
zero BLE RX/TX drops or allocation failures. This does not prove a complete hour.

A second full3600-second attempt writes `failure-1hour-e2.json`, minute summary
and raw `.checkpoint.json` files. An independent hidden host runner restores
the intended Wi-Fi connection on exit and writes `failure-e2-runner-result.json`.
Until a final passing report exists, the one-hour acceptance remains open.

### One-hour failure profile second attempt — FAILED

`failure-1hour-e2.json` ended near48 minutes with
`TimeoutError('BLE final/PONG missing: B12387')`, after12525 successful BLE
commands and2107 USB pings. Ten BLE connections,46 bursts andten unreachable-AP
attempts completed. The report's `elapsed_s` is unset because failure occurred
before the final duration assignment; last periodic snapshot was2851.36 s.
This is a failed test, not a completed hour or merely another host interruption.

UART reports SPI txrx HAL error and failed first transaction immediately before
device uptime8958997 ms: unresolved notify, phase2,0/244 bytes and AT
fence. Recovery began8959017 ms and ended ready15840 ms later. NCP attempts/
successes advanced3->4, failures0. USB/ToF continued; final ToF ready3.5 fps,
radio allocation failures0, CLI RX/TX drops0, pool4424 bytes/38 fragments.
One18-byte GATT input was discarded across the generation change. These counters
do not prove the exact causal disposition of the missing command. The host
reconnected Wi-Fi successfully afterward (`failure-e2-wifi-restored.json`).

Next priority is to capture the SPI HAL/DMA error state and transaction/handshake
phase at the first fault, determine its cause, and verify how an in-flight CLI
command is retired/reported when recovery changes generations. Never replay an
uncertain command or report success without evidence. Then repeat the full-hour
failure profile. No further Flash installation is claimed by this checkpoint.

### Candidate F: SPI evidence and explicit BLE recovery event

The original error callback attempted `LogError` from interrupt context. The
logging adapter rejects ISR formatting, so the exact HAL error was absent in
the E failure trace (two interrupt rejections in the final counter). This
explains missing diagnostic detail; it does not establish the hardware cause.

`spi_port_capture_irq()` now samples error flags in SPI5's USER IRQ block before
HAL clears them or starts DMA abort. Callback/start/timeout/bad-completion paths
retain fixed scalar evidence: transfer/phase/length, HAL error/state, SPI control
and status registers, TX/RX DMA state/error/CCR/CSR/CBR1/CTR1/CTR2 and pin levels.
No payload copy, allocation, formatting or wait in the ISR. The first unreported
snapshot survives later capture attempts and local/NCP reset. Radio prints four
`SPI-FAULT` lines through existing UART storage; `radio status` exposes a summary.
Snapshot source codes:1 pre-HAL SPI IRQ,2 HAL error callback,3 DMA start failure,
4 polling failure,5 non-clean DMA completion,6 transfer timeout. `collapsed`
counts additional capture attempts before the first record can be reported.
HAL flags may be enriched by its later callback. No SPI speed, DMA priority or
hardware reset policy changed. Capture frame32 bytes; deferred report280 bytes
runs on Radio, not the constrained768-byte SPI worker stack. This is not a
worst-case whole-system stack proof.

Each coordinated recovery records the retired BLE generation and scalar pending
RX/TX/reply state, and reports UNKNOWN/no replay on UART. The next subscribed
BLE CLI receives `[CLI-EVENT] event=RADIO_RECOVERY ... outcome=unknown` using
the existing eight response slots. It is not `[CLI-RESULT]` and cannot finalize
a new command. New input waits until the event's actual TX terminal drain;
publication/backpressure/link changes retain it. Raw update input is excluded.
No old command text, password or output is exposed to the new session.

F ELF SHA256 `4E18B7AA28B6C1E6B6CB80A6C0CC512EB37C583CF3C6AB9356440DE388363B14`,
RAM v10 package486496/NS485192/heap386568.27 regression files and16 feature-mode
compiles pass; package/sign/load pass; ToF started ready after this warm load.
The boot-repeatability gate remains open. Native capture/notice tests verify
ownership and publication races; they do not reproduce the natural SPI fault.

Focused `connected-recovery-f1.json` failed its notice check: it observed only
the later manual reconnect, after Windows had already restored the previous
BLE subscription and the notice had drained. The failed report is retained.
The corrected observer records both connections. `connected-recovery-f2.json`
passes36 BLE finals/25 USB pings (BLE p95 187/max391 ms) andfive new CRC-valid Cloud frames after
automatic Wi-Fi restoration. The actual receiver captured recovery sequence2,
old generation7, UNKNOWN. No host password/connect command during recovery.
This diagnostic power-off obtains a genuine unanswered AT fence; it does not
inject or explain the earlier natural SPI HAL error.

`failure-1hour-f1.json` is a new full-hour profile, with raw minute checkpoints,
failed-command received bytes and duration retained on failure. Radio/Cloud
loop rates are recorded without an arbitrary100 Hz CPU assertion: Radio is
also woken by notifications. Reset/fault, missing-reply and ToF-health gates
remain strict. The host runner restores Wi-Fi and checks matching Cloud MAP ON
completion plus five new frames afterward. Full-hour result is pending; the
natural SPI cause and Flash acceptance remain open.

Post-load source review explicitly qualifies shared `fault_reported` as volatile
(Radio writes, ISR reads). Incremental/sign and native capture checks pass.
Loaded F binary SHA `0A9398EE7AF85C097918447874EF67909AF3A0E57FE510143A67737D455F7611`;
updated binary SHA `647BBAB87F014F09573FDB9D7EDDE0DEB1444AAD0B79D908D6FC7F435CFBD0B5`.
Both binaries are485192 bytes;11 instruction bytes differ in the diagnostic
report function. The saved F ELF remains the hardware image during this hour;
do not claim byte equality or hardware acceptance of the later build.
Updated ELF SHA256 `4D70F6D97C5E7396E30F3D9DF28C0042CB58EC7F9EF0C8BC4BFF65D168D6CF93`.
All SPI/AT/recovery/CLI execution paths outside that report function are unchanged
in the binary comparison. At741 seconds the new F hour checkpoint records2804
BLE commands,550 USB pings,three connections/twelve bursts/three unreachable-AP
attempts; no new SPI snapshot, NCP recovery or allocation failure, ToF ready.
This intermediate checkpoint is not a completed hour or proof of the natural cause.
