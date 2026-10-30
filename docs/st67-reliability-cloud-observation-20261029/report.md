# ST67 CP9: live Cloud images, new SPI fault, Windows input still blocked

2026-10-29 08:11:22-08:13:23 UTC. User confirmed the desktop open and requested
another access check. B52/source5432d4a remains; no firmware/build/sign/reset,
pairing, saved settings, security/ACL, push or deployment change.

## Actual Cloud-only observation

At the first UI read the existing workspace/device was ONLINE with live actual
ToF images. Its transcript already contained MAP ON and MAP ENCODING UINT8,
plus an intervening unsupported map-compression command. These were not issued
by this agent. Preserve the current user's stream/encoding; no MAP OFF or route
switch was sent. The observed route is CLOUD, DEPTH54x42/UINT8 affine/2268bytes;
BLE is disconnected with notificationsOFF.

Under the exclusive lease, read-only CN8 status and120s USB pings completed:
59 pings, maximum65.476ms, version52, ToF/NPU progressing and NPUerrors0.
Cloud sender counter150->269 (+119), dropped0, requesterrors109->110. Commands
received/acked remain5/5 and output17. These are sender counters, not a complete
browser receive count or command-latency distribution. Sampled UI frame IDs
advanced354178->355392, and rolling3s rates ranged0.0..2.3fps; sampling is too
sparse for exact receive gaps or per-frame CRC acceptance. Display of a CRC
field alone is not proof of zero corrupted transfers.

**FAIL for scoped transport health:** SPI122->123 during the observation, last
tick35569180/source1/phase2/len332/HALerror4/SR00b80042, DMAerrors0. NCP recoveries
remain2/ready2/failed0 and RX allocationsfailed0. This is a newly captured SPI
fault with BLE idle, independent of CP8's BLE1953ms latency violation with no
new SPI fault. Neither observation establishes the physical root cause.
Full V02 command/receive/memory acceptance and P0-04 remain INCOMPLETE.

User stream and settingsgeneration2 were preserved, all serial handles and lease
released. No cable/power/jumper intervention is indicated. The postflight Cloud
state was connecting/last204 with its user-started image route still CLOUD.

## Browser action and exact denial

CP7 URL restriction did not recur. AX and screenshot correctly showed the N6 page.
An element click first reported unavailable geometry. A fresh screenshot provided
the geometry; a coordinate focus click returned success but AX still reported the
address bar focused. Attempting setValue(version) was stopped by the tool's user
input guard. Input actions stopped and state was refreshed as the tool requested.
After a fresh screenshot, a bounded focus/paste attempt failed at the click with
`GetCursorPos failed: Access is denied. (0x80070005)`. Paste/send did not execute.
The final read showed the input empty and no version command in the transcript.
No additional input retry, alternate browser/backend, storage read, privilege,
window-station, desktop or ACL change was attempted.

Read-only OS metadata printed console session1 Active, with Chrome and ChatGPT/
Codex/node/shell in session1. Both metadata command wrappers had exit1 despite
displaying those rows; the raw error cause and helper thread desktop are unknown.
This excludes a demonstrated gross process-session split; it does not prove the
helper's desktop identity or its window-station rights.

Microsoft documents both window-station read-attribute access and the correct
input desktop as prerequisites for GetCursorPos. This supports investigating
the native input helper context; it does not prove that the user locked Windows.
[Microsoft GetCursorPos documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getcursorpos).
No native desktop-switch/API workaround was invoked.

The specific next step is a **normal restart of the ChatGPT/Codex desktop app on
Flow13**, keeping Chrome's existing N6 workspace and the board connected, followed
by one fresh access check. This may restore the app's native input context but is
not a proven fix. The app was not restarted by this task. Do not repeat a request
merely to unlock Windows or re-pair N6. If restart does not resolve it, retain
this exact repro for the Computer Use integration rather than changing privileges.
This is a Windows/tool input denial, not automatic shell-approval rejection.

## Independent BLE-isolation audit

Rechecked actual CLI/source to avoid requesting secrets or disconnecting blindly.
debug_cli.c:2584+ accepts wifi connect only with SSID and starts a hidden-password
prompt; no bare connect/reconnect-saved command is exposed. wifi_forget_connection
at wifi_ble_app.c:2887 clears volatile intent then calls AppSettings_DisconnectWifi.
app_settings_ncp.c:314 clears WIFI_DESIRED and commits even with forget=0. The
saved-credential restore path at wifi_ble_app.c:2844 requires both volatile desired
intent and saved desired=true. Therefore disconnect+reboot is not a reversible
BLE-only profile procedure. No such commands or credential reads were performed.
Any future baseline isolation facility must use the existing owner and reversible
volatile suspension with unchanged saved flags/generation; it is not implemented
or accepted here. Source hashes are retained in source-audit.json.

## Conclusions and pending gates

1. Live Cloud image reception is established qualitatively; sender progress and
   one new physical SPI fault are measured. USB remains responsive throughout.
2. CP8's1953ms/1500ms failure remains; no repeated BLE load attempted after it.
3. Actual controlled Cloud commands, precise receive windows and safe BLE-only
   isolation still block P0-04/05. No dependent firmware gate or safety limit waived.
4. Next UI prerequisite is the specific app-context restart above. Firmware remains
   B52, previous A51 intact; all future installation stays signed USB only.
