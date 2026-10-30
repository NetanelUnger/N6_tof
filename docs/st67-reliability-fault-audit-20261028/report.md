# ST67 CP5: fault models, diagnostic contracts and fresh B52 observation

2026-10-28 UTC / 2026-10-29 Asia/Jerusalem. Source5432d4a; B52 remains the
confirmed installed baseline, A51 retained. No firmware C changes, build, signing,
installation, reset, NCP update or persistent setting change in this checkpoint.
This is independent source/native preparation while P0 profiles and worksheet
remain incomplete. It does not waive P0-P1 dependencies or sign off P2-P7.

## Fresh hardware observation

CN8 COM8 identity N6TOF001 passed30s, maximum65.400ms, version52 throughout;
all handles and the shared lease released. ToF frame19381->19687, NPU7582->7698,
NPU errors0, NCP recovery0, radio allocation failures0, saved settings generation2.
Image destinationNONE, BLE disconnected/advertisingon, notificationsOFF. Cloud
still polls409 with zero commands/images. No cable/power/jumper action is needed.

**SPI is not healthy:** count2 versus CP4 count0. Both before/after this30s sample
were2, so the events occurred between checkpoints, not necessarily during USB
commands. Last retained fault tick1896870/source1/phase2/length332/HALerror4/
SR00b60040, TX/RX DMA errors0. Local HAL/CMSIS definitions identify OVR bit6 and
HAL_SPI_ERROR_OVR4; phase2 is the remaining-RX transfer. This is physical transport
fault evidence on the exact known B52. It does not identify why RX could not
drain, prove absent DMA timing problems from errorcode0, or tie the fault to
BLE, Cloud409, logging or the host fault model below. No live fault was injected.

## Independent test group

Fourteen existing suites were run, preserving every command/hash/log in
native-tests.json. Thirteen initially passed; Cloud request-budget testing passed
its14 native driver groups but its Cloud fixture did not compile because it lacked
the newer training context/tick/ToF mode. The fixture now uses mode5 from the
production definition, models that boundary, and asserts one training retirement
per epoch plus no false retirement for ordinary images/inactive training. Original
tests remain. Re-run PASS20 native groups plus one source wrapper audit. Across
all14 final suites there are120 printed PASS groups/audits; those are not120 HIL
cases, and some individual groups cover multiple permutations.

Covered: retained fault snapshots; SPI/DMA shutdown ownership; exact FS framing;
flow-probe and backpressure startup guards; asynchronous notification lifecycle;
raw prompt/terminal/fence behavior; parser shutdown; coordinated recovery barriers
and reset budget; BLE control mailbox/generation; scan admission; Cloud send
slices, request deadlines/network epoch; service status. Mocked HAL, clocks,
schedulers, queues and NCP boundaries are explicit in each fixture. Native PASS
does not establish wire timing, electrical behavior or physical reset safety.

## Failure classification and meaningful new models

| Finding | Reproduction/evidence | Classification and limit |
|---|---|---|
| Shared driver errors shown on BLE line | Actual TranslateErrorStatus_W61_W6X + error_callback count WiFi/BLE/system failures identically; only four notification BUSY names are excluded | Diagnostic attribution gap. B52 count2/last2 means generic W6X error; actual operation remains unresolved. MTU/connection-parameter calls are candidates, not proven causes |
| Quiet logger success mismatch | Actual Debug_UART_Write returns94 for a94-byte suppressed record; actual N6R_QueuedBytes treats nonzero as failure; reporter attempts unchanged record at1000/2000/3000ms | Proven host diagnostic-contract defect. Captured failure stays valid; reporting bookkeeping never retires it. Does not prove SPI cause or measured observer overhead |
| Isolated logger candidate | Proposed zero-success branch retires report once, preserves retained counter and performs no queue/poll I/O; enabled branch preserves zero success/negative failures | PASS host comparison, **PROPOSED-NOT-APPLIED** patch. No production edit or deployed fix |
| NCP rx_stall | Actual worker sends4 separate CS transactions: rejected payload, two empty probes (including clear), accepted retained payload; accepted once, freed once | PASS modeled contract; no application-level replay of accepted data in this rx_stall path |
| RX allocation failure | Actual first allocation failure sends0bus bytes and retains identical TX ownership | PASS model; not runtime fragmentation proof |
| Full RX queue | Actual loop uses10ms waits; injected stop on fourth attempt releases retained RX once | PASS cooperative shutdown; total runtime queue wait has no local absolute deadline |
| Header ACK stays high | Actual loop takes3x100ms waits until injected stop; source also exits on ready-low | Missing total operation bound, source/native evidence; do not silently replace with unsafe CS release |
| Remaining RX fails after full TX | Actual spi_xfer_one and spi_do_xfer retransmit the identical packet:2 modeled accepts in2CS transactions, local abort succeeds | **FAIL no-replay criterion in fault model.** Physical NCP may have accepted before receive error, so successful local DMA cleanup is insufficient proof of protocol safety |

The pressure harness returns0 only when its stated characterizations/counterexamples
are reproduced. Its `REPRODUCED ... FAIL` rows remain failed safety criteria;
they are not converted to acceptance PASS by the process exit code.

ST's SPI specification describes the dedicated/full-duplex interface and requires
a separate transaction when the module rejects data with rx_stall; busy p keeps
the current command executing. Reviewed2026-10-28, approved page revision dated
2026-04-01: [manufacturer SPI specification](https://wiki.st.com/stm32mcu/wiki/Connectivity:ST67W611M1_spi).
The no-replay fault is our source/native inference under an explicitly modeled
accepted-TX case, not a quoted ST assertion or a measured NCP trace.

## Staged repair requirements, not installed implementation

1. P1: retain bounded scalar operation/phase/generation/outcome identifiers with
   the shared error counter so quiet builds can attribute failures without
   emitting credentials or payloads. Compare observer overhead only after the
   workload is frozen; do not infer it from this test.
2. Apply the small logger contract patch when the implementation gate opens;
   promote its isolated regression, build the affected firmware contexts and
   measure on the next signed USB candidate. Current52 remains unchanged.
3. P2/P4: distinguish pre-transfer admission failure and explicit rx_stall rejection
   from ambiguous transfer completion. Do not automatically retransmit an unknown
   side effect after successful local abort. Coordinate a transport-failed/fenced
   state with AT owner, generation retirement and UNKNOWN outcome before recovery.
   Merely freeing TX early, clearing the fence, or dropping the buffer is not an
   adequate fix. Test initial TX failure, remaining RX failure, late terminal,
   queued command, stop failure and stale-generation callbacks before HIL.
4. Add bounded aggregate queue/header-ACK policy with preserved DMA/buffer
   ownership and explicit unavailable/unknown outcome. Existing10/100ms polling
   intervals are not total deadlines. Do not increase pool/queue/stack capacities
   without measured demand and fragmentation evidence.

These changes belong to dependent implementation phases. P0-04 needs actual
Cloud activity and a BLE-only baseline that preserves saved settings. The existing
disconnect command persists autoconnect=false; it was not sent. A reversible
profile/control path is an engineering prerequisite, not a request to expose a
password or change jumpers. P0-05 still needs prospective numeric campaign limits.
No new firmware version has been selected or consumed after52.

## Preserved failures and verification

The initial Cloud fixture compilation failure is retained. The first isolated
logger comparison had config.h override its intended enabled variant: quiet
results were valid but enabled coverage was INCOMPLETE. diagnostic-contracts-v2.log
supersedes only that coverage gap, with a post-include switch and distinct enabled
PASS. Neither log is overwritten. No hardware repetition was used to seek PASS.

source-hashes.json pins every implementation inspected. CP0 source recheck matches
all original inventory entries except intentionally edited README documentation.
Only a host fixture was changed in this group; no firmware build or Generate Code
is required for that edit. Final git diff --check must pass. No commit/push/deploy,
Git trust/ACL change, credential/bond/cache change or physical operation occurred.

## Conclusions and next prerequisite

The known B52 now reproduces a physical overrun, removing unknown51 provenance
as an explanation for deferring diagnosis. Root cause is still unresolved.
Two concrete source defects/gaps are demonstrated independently of Cloud: quiet
report bookkeeping and possible ambiguous SPI packet replay; prolonged queue/ACK
waits also need an explicit bounded policy. Their HIL repairs are not accepted.
Existing ownership/recovery tests pass after repairing the stale host fixture.

Pending user action is unchanged: open the existing N6 Cloud workspace containing
N6-MAINT-B8FB and keep it open. No new workspace or pairing is required. The pending
action is a prerequisite, not an automatic approval denial. The next USB candidate
remains gated by P0/P1 and required native/integration validation, not by missing
permission to perform an already authorized ordinary update. No uncertain install
is outstanding, and no cable action is presently needed.
