# ST67 CP7: Cloud resumed; overnight radio faults retained

2026-10-29 07:43:46-07:44:16 UTC. User reported Cloud connection and authorized
continuation. Existing plan hash/source worktree/local changes were preserved.
B52 still runs; CN8 COM8/N6TOF001 passed30s read-only stability, maximum63.254ms.
All owned serial handles and the shared lease were released. No firmware, reset,
settings, credentials, pairing, ACL or physical changes were performed.

## Results

Device-side Cloud status now shows HTTP204, the same workspace/device identity,
received2/acked2/output11, images0. This resolves the earlier device409 inactive
workspace prerequisite. It is not a newly issued test command or a completed
Cloud/image baseline; origin/latencies of those two commands were not measured.
Browser workspace contents were not independently inspected.

**Radio baseline has failed again:** SPI captured-fault count rose from CP5's2
to117 over the intervening unattended period. It stayed117 during this30s sample.
Last source1/phase2/len348/HALerror4/SR00c10040, TX/RX DMA errors0. There were
2 coordinated NCP recovery attempts, both ready, none failed; last recovery
24556ms. Lifetime BLE pump maximum gap24580ms, radio loop maximum gap788ms.
These snapshots are not a supervised endurance test and do not establish when
each fault happened or its cause. An outage-related lifetime maximum is not
an ordinary CLI request latency measurement. No deliberate fault was injected.

Shared ST67 error counter4/last3, BLE currently disconnected/advertisingon,
notificationsOFF; recovery notice sequence2/pending1/UNKNOWN. Radio allocation
failures0 and pool17296bytes/32fragments; saved settings generation2 remains.
Cloud request errors104 are cumulative; do not equate them with SPI faults or
attribute them all to current workspace use. Raw ToF/NPU/status evidence remains
in usb-resume/result.json. No cable/power/jumper action is presently indicated.

## Exact browser blocker

The allowed UI inventory found one Chrome window (ID25299644), whose active title
was an unrelated page; no browser connector for Chrome was available, only empty
in-app browser/MCP surfaces. Selecting that exact Chrome window through
`cua.getApp` was stopped before usable page state or UI action. The tool said it
could not determine the current browser URL on Windows confidently enough to
enforce policy, disabled Computer Use for this turn, and required a final response.
No browser retry, alternate browser/API workaround, storage read or access-policy
change was attempted. This is a Computer Use restriction, not a firmware failure
or an automatic shell approval-review rejection.

The already-running read-only USB check was allowed to finish and close safely;
only its evidence and this checkpoint were then recorded. Browser-controlled
Cloud traffic/receive measurements, P0-04/05 and dependent implementation have
not run. Firmware52 remains installed; no53 was built, signed, sent or consumed.

## Next action

The user's Cloud connection worked; do not ask them to reconnect or re-pair.
The remaining immediate prerequisite is usable authorized control of the existing
N6 Cloud browser session. The parent may ask the user to foreground the existing
N6 tab; a later turn can reassess the materially changed browser state. This is
not a guaranteed fix for the tool restriction. Do not bypass it if it persists.
Once browser access is usable, measure actual commands and one image route,
finish the baseline/frozen gates, then implement the already documented
diagnostic and ambiguous-SPI-completion repairs through signed USB only.

Conclusions: existing Cloud activation blocker is resolved from board evidence;
the known firmware has significant accumulated SPI faults and automatic recovery;
USB remains available; browser control, not a cable, blocks this turn's planned
Cloud workload. The program remains incomplete and no acceptance gate is waived.
