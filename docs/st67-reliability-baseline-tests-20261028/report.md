# ST67 CP4: B52 measurements and corrected acceptance

2026-10-28 UTC / 2026-10-29 Asia/Jerusalem. Known signed B52 remains installed
and Secure-confirmed; A51 retained. P0-01/02/03 DONE. P0-04/05 remain incomplete;
active Cloud workload requires the existing workspace to be opened. P1 audit is
done, reliability firmware changes and P2-P7 acceptance have not started.

## Results on exact B52

| Measurement | Result | Evidence / limits |
|---|---|---|
| Existing USB HIL100 | PASS100 exact CPU tensors,100 NPU results, max score delta0, CRC0;27.078s;3.766fps | hil100-wrapper.json/log; same-frame regression, not field accuracy |
| BLE CLI+USB, Wi-Fi connected, Cloud polling409, no images | PASS120s,120 BLE finals,52 USB pings; BLEp50=94,p95=156,p99/max=203ms; host lag29ms | control52/result.json; USBhelper max328ms includes settling |
| BLE RAW float32 DEPTH images+NPU+CLI, MTU247, same Wi-Fi/Cloud background | **FAIL corrected image throughput gate**:99 measured images vs100 reference floor;230 NPU results,199 CLI finals in120.141s | image120-corrected-assessment.json; original raw report retained, not fullV04 |
| Same image profile latency/continuity | PASS scoped: BLEmax219/p99=172/p95=156ms; NPUgap0.641s/imagegap1.406s; host lag28ms; CRC0/parser drops0 | Original1500ms/3s/5s gates preserved; no global PASS |
| Final USB30s | PASS max64.333ms,52 unchanged | final-usb/result.json |
| Native manifest-only safety regression | PASS after making it portable in hil_tests | manifest-only-portable-test.log; mocked hardware, no live erase/readback claim |
| Corrected soak measurement-window tests | PASS4 meaningful boundary cases | soak-window-test.log |

NCP reports SDK2.0.106.0,AT1.0.0.0, MACFW1.6.44.0, BLEcontroller1.6.128.0 /
stack1.10.83.0; host driver1.3.0. PackagedT01 SHA256 matches contract exactly.
This records the live reported identity, not a fresh on-module binary hash or
release-note/power/TLS compatibility signoff (P6 remains open).

BLE driver errors changed0->1 across the control connection;
final counter2. CLI delivery gates passed, but the underlying driver
event is unresolved and not erased from acceptance. Immediate disconnect snapshots
can precede link-state settling. Final link disconnected/advertisingon, notifications
off, imageNONE/mapOFF/datasetOFF; ToF/NPU advancing, NPUerrors0, I3Cerrors0,
SPI0/NCPreset0/allocationfail0, saved settings generation2 and pairing retained.
All hardware handles and leases are closed; no physical action is required.

## Test defect and retained failed attempts

The original soak checked `len(images)` after an awaited end-state query. It
counted101 total images including one warmup and one after the measurement end;
the frozen window was start1/end100 =99. Thus the receiver printedPASS even
though its own unchanged100-frame reference floor was missed. The overall
assessment is FAIL. The raw PASS is preserved and explicitly superseded by the
corrected assessment; no failure was overwritten or limit relaxed.

`run_ble_npu_soak.py` now checks frozen start/end counts for both images and NPU
results. Four host tests cover this actual99/101 counterexample, exact120s
thresholds, NPU shortfall and unchanged hourly floors. The portable native
manifest-only test proves no Write/Finalize/reset for exact256-byte headers,
plus both slot directions/abort and unchanged modeled NOR. These are host-test
changes only; B52 firmware source is unchanged.

The first control invocation used Python3.14 without Bleak and stopped before
hardware. The existing project training environment (Python3.11/Bleak3.0.2)
completed it. The first image invocation failed before BLE setup because the
output parent directory did not exist; the corrected second run is separate.
Both failures and the original image PASS remain retained. No new dependency
installation or repeated physical run merely to seek a PASS occurred.

## Remaining prerequisites and next work

The available browser had no loaded N6 workspace. The deployed Cloud page offers
Open existing file/New workspace; the device continues HTTP409 with no accepted
Cloud CLI or image transfers. The local server command-poll source maps409 to
workspace_inactive. The existing workspace file contains authentication material;
it was not read/uploaded, and no new workspace, token or device pairing was made.

Minimum user action: open the **existing workspace containing N6-MAINT-B8FB** in
N6 Device Lab and leave it open. No cable/power/jumper action is required. This
enables P0 Cloud-only and combined workloads; do not call current409 polling a
working Cloud profile. Authentication/upload permission for a chosen existing
file is a separate possible handoff, not inferred from a generic plan request.

BLE-only also remains open: current `wifi disconnect` persists autoconnect=false,
and reconnect prompts for a password. It was not sent. Design a reversible
profile that preserves saved connection intent before disabling Wi-Fi; do not
read credentials, silently clear intent or substitute a cable/power cycle.

Keep P0-05 worksheet unfrozen until missing profiles and recovery bounds are
measured. The99-frame result identifies a baseline shortfall against the reused
BLE-only reference floor under background Wi-Fi; it does not identify AT/RF/SPI
as the cause. P1 attribution/instrumentation follows the completed baseline.
No improvement is claimed from52's zero restarted SPI counters or quiet logging.

The installed52 source/package/hash is in CP3, HIL now verifies its computation.
These exact immutable host artifacts can support a later deliberate choice to
replace oldA51 while retaining knownB52 as the next confirmed rollback image.
No next version has been built or consumed. No bootloader/Secure/NCP programming,
security/ACL, credentials, server deployment, commit or push occurred.
Generate Code is not required for these Python/test/documentation changes.
