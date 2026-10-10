# Radio availability and bounded CLI replies

2026-10-10, tasks 1 and 2 authorized by the user. Implementation and focused
BLE/USB/Cloud hardware checks pass after the live follow-up below.
Tasks 3 (coordinated genuine-NCP recovery) and 4 (full endurance) are not started.

## Availability contract

`WIFI_BLE_App_GetServiceStatus` reads the existing owners without issuing AT
queries or waiting for a mutex. It reports `available`, `waiting` or `fault`, a
reason, elapsed milliseconds and remaining milliseconds where a deadline exists.
Reasons include startup, DNS terminal drain, late BLE terminal, Wi-Fi work and a
genuine shared-AT fence. A zero remaining value on Wi-Fi work means the budget
is unknown, not that the operation has expired. Reading status never creates,
clears or bypasses a protocol fence. The original notification, DNS and request
budgets are preserved. Brief normal AT transactions are not reported as outages.

CLI reports service transitions on the existing debug UART and, when usable,
USB. UART START/END describes the observed service interval; the existing
RADIO-WAIT diagnostics retain precise transaction start/end and the PENDING
timeout snapshot. Remote command replies carry a service snapshot. Local status,
ping and ToF commands remain usable while the radio waits; radio-dependent
commands, including password submission, are explicitly rejected before dispatch.

A fault on the response transport itself can prevent a remote fault message
from arriving. The browser then shows an unknown command outcome; USB/UART remain
the independent diagnostic path. This change does not implement NCP recovery.

## Ownership and admission

| Transport | Existing storage | Ordinary admission / completion |
| --- | --- | --- |
| BLE CLI | 8 x 768-byte TX slots | Reserve all existing free slots before reading a command; pack print calls; retain following RX bytes in their original slot until the next reservation. |
| Cloud CLI | 8 x 384-byte output slots | Reserve empty output storage before executing a leased record; return an unexecuted lease on contention; retain command identity through ACK, output and final server completion. |
| USB | Existing console path | Independent of radio reply capacity. |

Each packed reply reserves 128 bytes for an explicit final record. Final records
report dispatch completion, rejection, output limit, failed write/formatting or
Cloud JSON encoding limit. Completion is not a claim that asynchronous Wi-Fi
work has already acquired IP. Its existing result ownership is retained. Cloud
publication can retry a busy mutex without rerunning the command or adding a
duplicate trailer. Generation replacement retires old builders. Another producer
cannot borrow an active text reply. No stack, queue or pool capacity is enlarged;
there is small scalar metadata overhead, and added code reduces the linked
C heap margin. No per-command payload allocation is added.

XMODEM uses its existing raw byte/record contract. BLE releases the empty ordinary
reservation before updater dispatch, so the initial single-byte `C` cannot be
packed with the text banner. Binary Cloud update records bypass text packing.

The live scan probe found ordinary `input.completed` wrongly entering the updater
completion branch and retiring the command before its asynchronous Wi-Fi result.
That branch now also requires `update_was_active`. Cloud's completion stays held
until the existing owned Wi-Fi result is published; later commands can then run.

Live image delivery also reproduced SPI receive allocation failure on two boots,
including a clean start. A full-MTU retained TX and a full-MTU RX need simultaneous
space in the fragmented radio pool. The1560-byte RX allocation failed despite1820
bytes total free; a genuinely unanswered raw send then correctly fenced AT traffic.
Cloud now limits each socket send to512 bytes. TCP preserves the HTTP byte stream;
partial writes retain their cursor, failures stop without replay, and the existing
total request deadline remains. No pool, queue, payload buffer or stack is enlarged.
This improves the observed transient headroom; it is not a general allocator or
genuine-fence recovery guarantee. More sends can add time to the same request budget.

## Browser behavior

Both terminals permit one ordinary command per device until a final result.
BLE GATT write acknowledgment is not execution acknowledgment. Cloud waits for
the matching server `completed` record, including asynchronous Wi-Fi output;
an early CLI dispatch trailer cannot admit another command. Output arriving
before the SendCommand invocation returns is matched by the returned command ID.
Old commands, prompts and duplicate outputs cannot complete a new command.

After 30 seconds without completion, or an ambiguous write/invocation failure,
the outcome is unknown and remains blocked. Ordinary BLE writes have no automatic
retry. Late completion can resolve the wait. Radio text is explicitly labeled a
snapshot taken during the command. Manual reconnect creates a new BLE session;
old firmware without final markers may remain unknown. Update upload buttons
are blocked while an ordinary command is outstanding. The UI is built locally;
it has not been published to the production site in this task.

## Evidence and limits

- 29 actual-C cases plus two source audits cover reservation/rollback, output
  overflow, write failure, formatter truncation, generation retirement, RX
  remainder, Cloud lease return/ACK/hold, JSON escaping, status timing/fences and
  raw-update isolation. Existing driver/lifetime/budget regressions and 16
  feature-mode compilations pass.
- Browser: six command-progress cases, eight XMODEM regressions, build and lint
  pass. Real DOM checked with a mocked GATT device: pending/unknown disables the
  input, late completion re-enables it, and an ambiguous write performs one
  attempt. The mock is UI evidence, not a hardware connection.
- Initial RAM checkpoint B1E6BD8C9C702C71FA43508FCEE4723E85EDF7835632E4FA1C32B02EC5F09910:
  451/451 ordinary finals, 102 received CRC-valid BLE frames, two concurrent warm
  Wi-Fi cycles, p95 157 ms, maximum 2500 ms. RX/TX drops zero, UART 324/324 without
  drops/errors; Radio maximum loop gap 31 ms. Two commands in one ATT value,
  help, separate XMODEM `C`, cancellation and subsequent ping passed.
- Exact final RAM checkpoint 7165C9CCA727107B8A9115C37F967E5CA69DB15D71289C9EC727897EDC298A08
  adds the native-verified JSON encoding bound. Its focused repeat delivers
  149/149 ordinary finals, 39 received CRC-valid BLE frames and two warm Wi-Fi
  cycles; p95 187 ms, maximum 2797 ms. RX/TX drops zero; Radio gap 23 ms; UART
  180/180 without drops/errors in the concurrent snapshot. XMODEM startup/cancel
  and the combined ATT command repeated successfully.
- Subsequent exact-target admission check: `wifi scan` rejected before dispatch
  during `WIFI_CONNECT` (577 ms elapsed), while a local USB ping succeeded.
  Service returned to available after IP. Final UART257/257 zero drops/errors,
  ToF ready, Wi-Fi results7 routed with zero write/deferred-overflow errors.
  Radio maximum gap later reached266 ms after BLE teardown/control work; do not
  report the earlier23 ms concurrent sample as the final whole-run maximum.
  Eight public service START/END pairs were observed. BLE/COM handles released.
- Exact package 478624 bytes, NS binary 477328 bytes, C heap 394776 bytes
  (minimum 368640). RAM is v10; tracked version and external Flash stay v9.
  Saved ignored ELF: `.local-dependencies/diagnostics/cli-service/candidate-exact.elf`.
  Logs/reports are in the same ignored directory; earlier checkpoints remain.
- The user explicitly approved saved-token use against the existing project
  endpoint, resolving the earlier automatic-review block. No token is printed
  or added to tracked files. Live failures are retained in `cloud-live.log`,
  `cloud-clean.log`, `cloud-probe-failure.json` and `ble-cloud-slices.json`.
- Final Cloud candidate ELF ECB783DA020BACC4D3E4AC55A97A22D34F9708AD4BDF4DC6EF411132D83D9769:
 139/139 ordinary BLE final replies, p95 360 ms/max2297 ms, plus two commands in
  one ATT value, help, separate raw XMODEM C/cancellation/subsequent ping. No
  firmware payload sent. RX/TX drops zero. Two warm Wi-Fi cycles return three
  actual Cloud frames in1406/4218 ms after IP; USB pings remain usable.
- Cloud receiver assembled414 CRC-valid frames, zero CRC/protocol errors. Six
  command probes have matching server completion IDs and final device records,
  including the asynchronous scan result before completion. Final Cloud sample
  maximum9937 ms; an earlier queued command took13890 ms. These pauses remain.
  Final Radio maximum gap88 ms, allocation failures zero, UART416/416 without
  drops/errors,12 public service START/END pairs. One Cloud request error occurred
  across reconnect work; this is not an error-free network/endurance claim.
- Eight added actual-C cases cover partial bounded sends, byte identity, failed
  send/invalid driver result, ordinary async completion and OTA terminal behavior.
  Total37 actual-C +two audits; final16 feature-mode compiles pass. Host harness
  mistakes (a wrong compact-scan text expectation and a shadowed command function)
  were corrected and their failed reports retained; the corrected repeat passed.
- Final package478688 bytes, NS477392, heap394712 (minimum368640); RAM10 and
  Flash/header9. Exact ignored `candidate-cloud-final.elf`, `ble-cloud-final.json`,
  `cloud-probe-report.json`, `cloud-final-summary.json`, UART `cloud-final.log`.
  Test workspace/image polling stopped after HIL; Wi-Fi retained, BLE advertising,
  handles closed. Frontend remains local/unpublished. DNS/late-terminal injection
  remains native-only; no coordinated module recovery or full endurance yet.

These focused checks do not replace the older 621/622 and 614/615 missing-reply
failures or prove the full latency/endurance gate. The measured multi-second
waits remain. Focused Cloud acceptance has passed; full gates have not. Tasks3–4
await the user's next instruction, and v10 has not been installed into Flash.
