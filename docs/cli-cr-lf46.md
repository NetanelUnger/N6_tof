# Remote CLI framing — version46

This supersedes version45's final `[CLI-RESULT]` protocol record for ordinary
BLE/Cloud commands. Debug output still defaults OFF in Core/Inc/config.h.
No CubeMX Generate Code is required.

## Wire format

- CR (`0x0D`, `\r`) means a displayed line break inside the reply.
- LF (`0x0A`, `\n`) is emitted once, after the complete command response.
- A failed/rejected reply includes the standalone visible line `FAIL` before
  the final LF. The failure suffix is `\rFAIL\r\n`.
- The prompt, when present, precedes the final LF. A transport-only ping can
  omit the prompt and end directly with LF.

Examples, using escape notation rather than literal control characters:

```text
Firmware version: 46\rn6> \n
First line\rSecond line\rn6> \n
Unknown command. Type 'help'.\rn6> \rFAIL\r\n
```

Existing handler CRLF and lone LF line endings are normalized at the ordinary
remote-text boundary. A CRLF split across consecutive writes is normalized
without creating an extra blank line. Slot reservations, atomic rejection and
reserved failure capacity remain bounded. The raw append path and XMODEM
control/payload bytes are unchanged. The native USB terminal retains CRLF
lines and its traditional prompt; the framing change is for the website's
BLE/Cloud text protocol.

BLE asynchronous Wi-Fi admission produces text without final LF. The matching
worker result finishes the command. Cloud's existing final `completed` record
now carries the LF, after asynchronous results; command identity and server
completion remain authoritative. Unsolicited session greetings are separate
from command responses and retain their legacy CRLF format.

The website renders CR as a newline and recognizes final LF across arbitrarily
split notifications. FAIL remains visible. It also supports legacy CLI-RESULT
records from older firmware. Binary XMODEM bypasses ordinary command parsing.
The shared Python host helper supports both formats; capture and reusable HIL
clients no longer require the old completion string.

## Verification and current state

B46 was built, signed and installed through CN8 USB; A45 remains the previous
slot. The immutable build directory is
`.local-dependencies/xip/v46-B-cr-lf-command`. Package size:487488bytes.
Signing/package checks and XMODEM EOT ACK passed; USB version46/PONG, ToF ready
and NPU ready/errors0 were verified. An additional explicit reboot is verified
in the final USB postflight report.

Real nonbonded BLE checks passed:

- `version`:26bytes, one notification, one final LF.
- `help`:2716bytes across14 notifications, CR interior lines and one final LF.
- Unknown command:41bytes, visible FAIL/CRLF and one final LF.
- Read-only `wifi scan`:555bytes across4 notifications, one final LF only
  after the scan result, rather than at request admission.

Exact notifications were replayed through the website's CommandProgress and
display functions: admission remained pending before the final notification,
then completed/failed correctly. The website production build and thirteen
progress/display checks pass. Native production-code tests cover normalization,
fragmented CRLF, slot boundaries, overflow, raw-byte preservation, BLE reply
ownership, Cloud asynchronous/failure publication and sticky writer errors;
XMODEM timeout regressions pass. No fresh Cloud network or browser UI session
was exercised. Companion website changes remain local, not published; the old
deployed site requires the updated parser to recognize v46 replies.

The first sandbox BLE access could not create a Windows requester; the normal
Windows user succeeded without pairing/cache changes. An initial exact-byte
assertion also captured the lazy new-session greeting. That failed evidence is
retained; the final test drains the greeting with an empty input line before
checking command responses. It does not discard any command output.

Evidence in the immutable directory: build.json, usb-install.log,
usb-postflight.json, ble-framing-final.json, ble-framing-with-scan.json and
verification.json. No credentials, saved settings, boot-chain images, OS
pairing, website deployment or server code were changed. Hardware handles and
the shared lease are released when validation finishes.

Reusable read-only BLE check (requires the exclusive matching lease and the
project HIL Python environment with bleak):

```powershell
python hil_tests/run_cli_text_framing.py --execute --owner-thread OWNER --version 46 --wifi-scan --output FRESH-REPORT.json
```
