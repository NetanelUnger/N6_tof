# ST67 CP8: verified Cloud workspace; BLE latency regression captured

2026-10-29 07:55-07:59 UTC. Exact B52/source5432d4a remains installed and previously
Secure-confirmed; A51 was not overwritten. No53, firmware write, reset, pairing,
credential/settings/security/ACL change, commit or push occurred.

## Browser prerequisite and precise remaining blocker

The user's foreground change resolved CP7's URL-identification restriction:
native Computer Use successfully read Chrome window25299644 at the existing
N6 `/cloud` URL. The page showed RELAY CONNECTED, the existing workspace prefix
ws-13e32f198c2e429..., and N6-MAINT-B8FB ONLINE. No new pair was attempted.

The next action, `chromeN6.click(4508)` on the Cloud CLI input, failed with
`GetCursorPos failed: Access is denied. (0x80070005)`. The following paste and
Return in that sequential call did not execute. A read-only follow-up AX check
showed the unchanged empty CLI input and original address-bar selection/focus.
Independent USB counters remained received2/acked2/output11. Thus no new test
Cloud command was submitted. No input retry, alternative browser/backend route,
browser-storage extraction, desktop/security alteration or bypass was attempted.
This is Windows native-input denial, not a shell auto-approval rejection. The
desktop lock/session cause is not proven merely by the error code.

The remaining user action is to make the existing Windows desktop/N6 window
available for native input (check unlocked/active desktop, including any remote
desktop session), then permit a new access check. Do not ask for pairing again.
No cable, power removal, jumper change or firmware replacement is indicated.

## Independent bounded baseline and failure

USB preflight30s PASS, max64.328ms, exact COM8/N6TOF001/version52. SPI count121
versus117 at CP7, both prior to this load; NCP recovery remains2/ready2/failed0.
The four intervening faults are not attributed to the browser or this test.

Ran a fresh120s-target BLE image/NPU/CLI profile after Cloud activation changed
from409 to204. This materially changed background workload justified a new
baseline; it does not repeat CP4 to erase its99/100 failure. Used actual current
run_ble_npu_soak.py with its frozen receive-window correction, fresh-service
nonbonded connection, MTU247, actual DEPTH54x42 RAW images, one BLE image route,
NPU notifications, ping followed by0.5s sleep, existing Cloud polling.
The adapter retains the original1500ms/3sNPU/5simage/CRC/count gates; it only
permits and labels existing Wi-Fi/Cloud instead of claiming BLE-only isolation.
No actual Cloud control requests or Cloud image destination were exercised.

**FAIL: the16th measured BLE ping completed in1953ms, exceeding1500ms.**
Measured BLE p50=109ms, p95/p99/max=1953ms across16 replies (small, interrupted
sample). A312ms setup ping is excluded. The collector stopped at first violation;
its9.469s elapsed field is the last successful loop checkpoint, not full run
duration. It has no frozen end-window count, so neither complete120s throughput
nor the image floor is accepted. Raw totals9images/38NPU include setup/cleanup.

Observed direct receive maxima: NPU1.172s, image2.093s, host-loop lag13ms; CRC0
and parser errors0 through abort. No SPI/NCP UART event appeared, but quiet UART
alone proves nothing. Before/after scalar evidence independently remains SPI121,
NCP attempts2/ready2/failed0, RX allocation failures0, Cloud requesterrors108.
The old lifetime BLE control max2035ms did not change; it does not identify the
1953ms request. This localizes the symptom to BLE response delivery under active
polling, without proving AT contention, NCP/RF timing or Windows BLE delay.
The13ms host-loop maximum does not explain a1953ms response by event-loop stall.

Cleanup returned MAP OFF successfully; imagesNONE/datasetOFF/ToFready/NPUerrors0.
Immediate firmware status still reported BLE connected after the host disconnected;
the later30s USB observation confirmed naturally settled disconnected/advertisingON,
all notificationsOFF. Postflight USB PASSmax65.074ms, B52/settingsgeneration2 and
Cloud204 preserved, SPI121/recovery2 unchanged. All handles and leases released.

## Conclusions and next tasks

1. Existing pairing/workspace are confirmed from both UI and board. The unresolved
   blocker is Windows input access, not Cloud activation or USB connectivity.
2. The current known firmware violates BLE latency with active Cloud polling,
   even without a new SPI fault or module reset in the measured interval.
   Preserve this failure separately from CP4's image-rate and overnight SPI faults.
3. P0-04 still lacks isolated BLE-only and actual Cloud-only/combined Cloud command
   profiles; P0-05 numeric workload worksheet remains incomplete. Do not waive
   those dependencies or call the program finished. The currently available
   Wi-Fi disconnect CLI persists autoconnect=false, so it is not a safe isolated
   profile transition without a verified restoration procedure.
4. No further load/retry after this failure. Existing quiet-logger candidate and
   ambiguous SPI replay counterexample remain prepared evidence, not installed
   fixes. Finish baseline and acceptance parameters, then correlate scalar owner/
   phase timing and repair in dependency order through signed USB only.

Artifacts: summary.json, original wrapper/receiver data and failure traceback,
preflight/settled raw USB evidence, exact adapted collector/wrapper and source
hash/change map. No Generate Code requirement: no product firmware was changed.
