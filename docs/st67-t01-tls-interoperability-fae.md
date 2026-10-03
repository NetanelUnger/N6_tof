# ST67W611M1 T01 HTTPS interoperability — draft FAE escalation

Status: **draft for a future ST FAE discussion; not submitted to ST**.
Product/configuration: ST67W611M1, `mission_t01` SDK 2.0.106, X-CUBE-ST67W61
host driver, STM32N657 host over SPI, TLS 1.2 client socket with SNI. The
project intentionally needs TCP/IP and TLS offloaded to the ST67 module; a T02
host-side LwIP/MbedTLS migration is not an acceptable answer to this request.

## Problem statement and evidence

The NCP repeatedly returns `AT+CIPSTART` -> `ERROR` while connecting to the
Azure App Service default HTTPS hostname used by the Cloud Relay, before an
HTTP request is sent. `cloud status` reports transport `-14` and HTTP status
`0`; pairing never completes. Disabling server-certificate verification for a
temporary demonstration build did **not** make the connection work. A control
test with the same NCP TLS path connected to `www.google.com`, sent an HTTP
request, and received HTTP 204. These tests establish endpoint-dependent TLS
interoperability, not the NCP's exact internal failure reason.

An independent workstation OpenSSL TLS 1.2 capture of the Azure hostname with
SNI observed one 6,603-byte server handshake record carrying the Azure-managed
certificate chain. The Google control had a 3,772-byte certificate record.
Requesting Maximum Fragment Length (MFL) 4,096 in the workstation ClientHello
did not change Azure's 6,603-byte record or produce an MFL acknowledgement.
The workstation ClientHello is not byte-identical to the NCP's, so this is a
strong compatibility hypothesis, **not** proof of the NCP's private error
code. ST's [T01 HTTPS guidance](https://wiki.st.com/stm32mcu/wiki/Connectivity:Wi-Fi_ST67W6X_HTTPS_Client_Application)
documents a 6,144-byte maximum plaintext fragment and warns that a server
which does not honor MFL may fail. TLS 1.2 itself permits plaintext records up
to 16,384 bytes; see [RFC 5246 §6.2.1](https://www.rfc-editor.org/rfc/rfc5246#section-6.2.1).

Reproduction data and the hardware/host distinction are recorded in
[the Cloud TLS execution history](async-architecture-recovery-plan.md).
The local dual-COM captures may contain echoed short-lived pairing codes and
must be redacted before sharing externally. ST should be provided with the
exact NCP image/driver versions and a sanitized AT/SPI trace. The observed
6,603-byte TLS record is 459 bytes over the documented T01 limit. HTTP
redirects, HTTP/2, and Azure's minimum accepted TLS version cannot explain a
failure that occurs before HTTP.

## Requested T01 product change

Please make the **T01 offloaded TLS client** interoperate with ordinary,
standards-compliant TLS 1.2 HTTPS servers that send a certificate/handshake
record larger than 6,144 bytes and do not negotiate MFL. The primary requested
capability is safe receipt and processing of a legal TLS 1.2 record up to the
16,384-byte plaintext-fragment limit, including a Certificate handshake that
may span multiple records, without moving TLS or TCP/IP to the STM32 host.
An internal bounded/streaming implementation is acceptable; the requirement
is observable interoperability, not a mandated RAM allocation strategy.
MFL negotiation may remain an optimization, but it cannot be the only route to
success with servers that ignore that extension.

Keep TLS server-certificate chain and hostname verification available and
working, with SNI, normal cipher negotiation, and bounded memory/time use.
Do not require applications to disable verification or downgrade TLS to
connect. If a remote endpoint still cannot be supported, return a specific
documented error (for example, oversized record versus certificate validation,
handshake alert, TCP failure, or timeout) instead of a generic `CIPSTART`
`ERROR`; release socket/credential resources and keep Wi-Fi/BLE responsive.
Please confirm the root cause of this exact 6,603-byte case from NCP-side
diagnostics and identify the first SDK/mission firmware version with a fix.

## Proposed acceptance test for ST and this project

1. With T01, TLS 1.2, SNI and **server verification enabled**, connect to a
   controlled HTTPS fixture that sends a legal 6,603-byte certificate/handshake
   record and ignores MFL; complete an HTTP request. Repeat with records near
   the TLS 1.2 16,384-byte plaintext limit and with the Certificate handshake
   split across records. Reject malformed/oversized records safely.
2. Repeat against the currently failing Azure App Service endpoint (or a
   byte-equivalent test fixture) and verify an HTTP response is received. Do
   not rely solely on one live certificate chain: Azure may rotate it.
3. Repeat with valid and invalid trust chains, hostname mismatch, timeout,
   reconnect, and certificate renewal. Valid cases pass; invalid identities
   fail explicitly. Check no socket/credential leak after failed attempts.
4. While connecting and after success/failure, Wi-Fi and BLE retain bounded
   progress and BLE responses are not lost. Record NCP error/timeout counters,
   radio-loop gaps and memory use.

This is currently a **compatibility limitation / suspected NCP defect**, not
a demonstrated cryptographic vulnerability or a proved silicon defect. The
project's current `APP_ST67W6X_CLOUD_USE_TLS=0` setting bypasses TLS entirely
for a separate plaintext-HTTP demonstration; it is not the requested product
fix and must be restored to TLS with server verification before any security
or customer-readiness claim. Cloud pairing and BLE-under-Cloud hardware
acceptance remain open.
