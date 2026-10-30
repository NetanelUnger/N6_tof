# ST67 CP6: compatibility preparation and retain-current decision

Reviewed2026-10-28UTC. This independent documentation/source audit advances P6
preparation while P0/P1 gates are open. It performs no hardware command, package
repair, setting change, NCP update, security change, install or restart. Exact B52
observation and unresolved SPI failures remain in CP5. P6 exit is not signed off.

## Identity and manufacturer comparison

CP4 records live SDK2.0.106.0 / AT1.0.0.0 / MAC1.6.44.0 /
BLEcontroller1.6.128.0 / BLEstack1.10.83.0. The local imported host header reports
1.3.0. The official component release and header both identify1.3.0 dated10April2026;
the top-level bundle table's1.2.0 driver entry is inconsistent with those direct
component records. No local firmware mismatch is inferred from that table alone.
[Driver release](https://github.com/STMicroelectronics/x-cube-st67w61/blob/572b72d/Middlewares/ST/ST67W6X_Network_Driver/Release_Notes.html); [version header](https://github.com/STMicroelectronics/x-cube-st67w61/blob/572b72d/Middlewares/ST/ST67W6X_Network_Driver/Api/w6x_version.h).

The official NCP release lists T01 SDK2.0.106 and SHA256
`33198f446ac7c1b9c48e25573f3498e7277119dff43da12a3e25791078b552f3`. Fresh local binary hashing matches that value and contract.json.
This confirms the packaged artifact, not the bytes currently installed in the
radio. The live module identity matches the contracted version; no live radio
flash hash or new NCP installation was attempted. The release also documents
DHCP/static-IP and TLS interoperability limitations. [NCP release](https://github.com/STMicroelectronics/x-cube-st67w61/blob/572b72d/Projects/ST67W6X_Scripts/Release_Notes.html).

## Actual configuration audit

| Area | Local source / evidence | Conclusion and remaining limit |
|---|---|---|
| Power and clock | w6x_config.h selects internalRC mode1 and power-save0. W6X_Init checks clock; W61_SetClockSource refuses a different source with preserve1. B52 preserves configuration | Consistent intended policy. Do not enable low power or alter clock/jumpers on speculation |
| Power readback | W61_GetPowerMode copies cached LowPowerCfg.PSMode; W6X_Init ignores return from W6X_SetPowerMode | A successful getter is not independent fresh NCP readback. Actual current power state/consumption not measured; preserve this limitation in any comparison |
| DHCP | wifi_enable_station_dhcp queries and verifies CWDHCP1 in preservation mode, instead of writing configuration; B52 has IP and saved autoconnect intent | DHCP expected/working in observed run. AP loss/return and DHCP edge cases remain untested; no static-IP change proposed |
| BLE services | Application owns advertising restart and reconciles generations; CP4 ends disconnected/advertisingon, notificationsOFF | Fits host-managed behavior. CP5 shared drivererror2 still lacks operation provenance; do not label it a proven MTU or clock error |
| Cloud/TLS | ConfigTLS0 and CP5 reports current HTTP endpoint with409; no active Cloud workspace | TLS interoperability is outside this observed HTTP failure; TLS product-release requirement remains open. Endpoint/security policy unchanged |

ST requires an accurate low-frequency clock for low-power BLE; the default
internal RC is insufficient for that mode. Current source avoids that combination.
This is a source-policy comparison, not a measurement of installed oscillator
accuracy or power. [Manufacturer clock guidance](https://wiki.st.com/stm32mcu/index.php?title=Connectivity:ST67W611M1_32KHz_management&oldid=80818).

## Decision and deferred experiments

Retain T01/2.0.106 and the intended awake/internalRC/DHCP configuration. There is
no evidence that replacing NCP firmware or changing clock/power/DHCP would fix
the measured SPI overrun. No migration toT02 is proposed. This is a present
engineering decision, not a claim that T01 has no defects or P6 is accepted.

No setting is yet causally implicated, so P6-03 one-variable A/B testing is
deferred until a specific hypothesis and reversible control/readback exist.
If needed, record before/after actual parameter readback, exact workload, latency,
throughput, receive gaps, reconnection and power; do not confuse the cached getter
with measurement. Preserve credentials/settings and restore original intent.

No binary repair script was executed: Test-ST67Package.ps1 invokes a text repair
helper, whereas this audit needed only read-only hashing of the named NCP binary.
Keys, tokens and unrelated vendor private material were not read. No upstream
source replacement was applied; local ownership/lifetime deviations remain.

Conclusions: packaged/contracted identity matches the direct manufacturer release;
the source policy is compatible with awake BLE; current power readback is cached;
known network limitations do not explain HTTP409 or prove the SPI root cause.
P6 acceptance still depends on completed baseline and relevant P1 measurements.
No user physical action is required. Existing Cloud workspace activation remains
the same pending user prerequisite for P0 workload measurements.
