# Wireless ToF image codec, version 3

`MAP ENCODING` reports the selection; `MAP ENCODING RAW|UINT16|UINT8|JPEG` changes
it in RAM for the next accepted wireless snapshot. RAW is the boot default.
The same command works through the shared USB/BLE/Cloud CLI. USB CDC `MAP ON`,
USB dataset records, local LCD and NPU inputs retain their existing formats.

The producer snapshots float pixels and the selected mode, frame identity,
channel, dimensions and publication tick. It never quantizes. The Radio Manager
encodes a BLE snapshot once on READY -> ACTIVE; the Cloud worker encodes its
borrowed snapshot before the HTTP upload. Both call `tof_image_codec.c` in place
inside the existing single SRAM4 buffer. No frame-sized second allocation.
The existing ownership/drain/backpressure and one BLE fragment per cycle remain.
An in-flight frame retains its original mode after a CLI change.

## Encoding

* 1 RAW: original IEEE754 float32 little-endian bits, including NaN/Inf.
* 2 UINT16: unsigned little-endian affine quantization.
* 3 UINT8: unsigned affine quantization.
* 4 JPEG: experimental grayscale JPEG plus exact validity mask (see below).
* Other IDs are rejected.

For quantization, code zero means invalid (decoded as NaN). Finite positive
values are valid for depth; finite nonnegative values are valid for channels
2..5, so zero ambient/amplitude/confidence/reflectance remains a valid value.
Base is the minimum valid sample; step covers the valid min/max range with
65534 or 254 intervals. Round to the nearest code. Decode `base+(code-1)*step`.
Constant frames use step zero and code one; all-invalid frames use base/step
zero and all codes zero. Error is approximately step/2 plus float roundoff.
This is quantization of the original channel units, not integer millimetre
casting; UINT16 and UINT8 are lossy relative to original float32 samples.

## Wire header

All integers and floats are little-endian. Each BLE notification starts with
this 56-byte header; Cloud sends one header with START|END and offset zero.
The CRC32 polynomial is reflected IEEE 0xEDB88320, initial/final XOR 0xffffffff.

| Offset | Type | Meaning |
|---:|---|---|
| 0 | u16 | Magic 0x364e |
| 2 | u8 | Version 3 |
| 3 | u8 | START=1, END=2; other bits zero |
| 4 | u32 | Sensor frame ID |
| 8 | u16 | Offset in encoded pixel payload |
| 10 | u16 | Total encoded pixel payload bytes |
| 12,13 | u8,u8 | Width and height, max 54x42 |
| 14 | u8 | Channel: depth1/amplitude2/ambient3/reflectance4/confidence5 |
| 15 | u8 | Encoding ID |
| 16 | u32 | CRC32 of complete encoded pixel payload |
| 20 | f32 | Base (zero for RAW) |
| 24 | f32 | Step (zero for RAW) |
| 28 | u32 | Publication HAL tick in milliseconds; wraps at 2^32 |
| 32 | u16 | Header size, 56 |
| 34 | u8 | NPU state: 0 off, 1 not ready, 2 no result for this frame, 3 valid |
| 35 | u8 | Class: 0 none, 1 rock, 2 paper, 3 scissors |
| 36 | u16 | Model score per mille, 0..1000 (not calibrated probability) |
| 38 | u16 | Reserved, zero |
| 40 | u32 | NPU sensor frame ID; must equal image frame when valid |
| 44 | u32 | Inference run counter; nonzero when valid |
| 48 | u32 | Inference duration in milliseconds |
| 52 | u32 | CRC32 of bytes 0..51, including offset/flags/NPU |
| 56 | bytes | This fragment's pixel payload |

Receivers validate bounds and header CRC before allocating, require contiguous
fragments with identical metadata, verify total length and payload CRC before
publishing, and reject unsupported modes. Browser and relay retain v1 RAW and v2 codec
compatibility. Upgrade the site/server before using the new firmware with Cloud;
the previous production server cannot accept v3.

At MTU247 the maximum pixel chunk is 188 bytes. Full 54x42 frames:

| Mode | Pixel bytes | Notifications | BLE application bytes | Cloud body bytes |
|---|---:|---:|---:|---:|
| RAW | 9072 | 49 | 11816 | 9128 |
| UINT16 | 4536 | 25 | 5936 | 4592 |
| UINT8 | 2268 | 13 | 2996 | 2324 |

These exclude ATT/link/radio and HTTP/TCP overhead and retransmissions.

## Verification

`python hil_tests/test_tof_image_codec.py` compiles the production codec with
MSVC and checks 90 combinations of modes/channels/edge cases, in-place bounds,
RAW bit preservation, CRC and quantization error. `--fixtures PATH` writes
cross-language vectors; the website uses `scripts/fixtures/tof-codec.json`.
`node --test scripts/test-tof-codec.mjs` validates the browser against those
vectors, fragmentation, corruption, mode changes and legacy frames.
`node scripts/test-tof-relay.mjs` validates the local HTTP/SignalR/browser path.
Hardware validation results are recorded separately; synthetic tests are not RF
or real Cloud acceptance. No CubeMX Generate Code is required.

## Validation checkpoint (2026-10-16)

- PASS: normal and protected Non-Secure builds, minimum heap guard.
- PASS: 90 native codec cases; 41 website protocol/CLI/updater tests.
- PASS: 24 C-generated frames through the local HTTP/SignalR/browser decoder;
  damaged packets rejected. This is a synthetic local server test, not board Wi-Fi.
- PASS: 15 syntax checks (three changed integration units, five feature modes).
- PASS: five existing actual-C routing/Cloud/BLE/ToF recovery regression suites.
- PASS: host BLE inspector reads 24 C vectors and rejects 24 damaged headers.
- Hardware incomplete after user-confirmed CN8/jumpers/reset: current protected
  candidate `d8f3ae62eff06beb6248d81352b7cbfac7faf347257eae982caeeb28797f89c1`
  loaded into SRAM successfully; heap 370888 bytes. UART confirmed ThreadX,
  VL53L9CX 54x42 initialization, first frame processing, NPU readiness and CDC
  activation at tick 6149. Output stopped at ST67 pre-init/W6X_Init. Afterwards
  Windows enumerated only ST-LINK COM6; application CDC was absent, and an
  attach-only SWD attempt at 1 MHz returned "No device found on target".
  CubeProgrammer HOTPLUG on the default access port subsequently reported
  target voltage 0.09 V and no core ID (`hotplug-default-ap.log`). This supports
  loss of target supply/reference; the initiating cause remains unresolved.
  A bounded BLE scan found zero N6 advertisers. No wireless image was received. Logs are retained under
  `.local-dependencies/diagnostics/image-codec-20261016/resume-*` and `attach-*`.
- Pending: restore stable target access, real BLE mode transitions and USB MAP
  regression, board Wi-Fi/Cloud and browser visual acceptance.
- Website changes are local; production has not been deployed. No external NOR
  programming, version change, settings write or NCP pairing was performed.

After hardware readiness, hold the existing exclusive lease and run:

```powershell
.\hil_tests\.venv\Scripts\python.exe .\hil_tests\run_image_codec.py --owner-thread YOUR_OWNER --report .local-dependencies/diagnostics/image-codec-live.json
```

Then, from the website repository, replay the real captured bytes through its
production decoder:

```powershell
node scripts/replay-tof-capture.mjs ABSOLUTE_PATH_TO_REPORT
```

## Hardware follow-up (2026-10-17)

After user reset, ST-LINK measured 3.28 V and identified the target. The exact
protected candidate above loaded successfully and reached an operational radio
and USB CDC COM8. Normal local Debug artifacts were restored after RAM loading.

- PASS real BLE RAW -> UINT16 -> UINT8 -> RAW: at least six complete frames per
  phase; 27 total frames, zero CRC errors and zero assembly drops.
- PASS replay of captured BLE bytes through production website decoder:
  RAW 13, UINT16 7, UINT8 7. Payloads 9072 / 4536 / 2268 bytes at 54x42.
- PASS USB MAP ON while selecting each wireless encoding: 15 advancing ANSI
  map frames per mode, same 54x42 depth format; final CLI ping passed.
- Final encoding restored to RAW; MAP stopped, BLE disconnected, serial handles
  closed and hardware lease released. Radio status reported zero SPI faults and
  zero NCP recovery attempts. No pairing/settings commands that write were used.
- Evidence: `.local-dependencies/diagnostics/image-codec-20261017/` contains
  `live.json`, `usb-validation.json`, `final-status.json`, and startup logs.
- Physical Wi-Fi/Cloud and visual browser rendering remain unverified; the
  existing local HTTP/SignalR/decoder integration test is synthetic. Production
  website is not deployed. The previous supply-loss cause remains unresolved.

### Supply review

The official [MB2230 A04 schematic](https://www.st.com/resource/en/schematic_pack/mb2230-antenna-a04-schematic.pdf)
lists C14 10 uF and C15/C16/C17/C18 100 nF on sheet 3; sheet 6 lists U6
LD39050PU33R with C4/C8 1 uF. The regulator is rated for 500 mA
([datasheet](https://www.st.com/resource/en/datasheet/CD00227527.pdf)). This does
not prove inadequate decoupling; capacitor requirements depend on the transient,
rail impedance, regulator response and effective capacitance under DC bias.

[UM3417 section 7.4.1](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf)
describes an ST-LINK-controlled eFuse on the Nucleo 5V_STLK path and host-dependent
current allowance. The observed persistent 0.09 V target reference with ST-LINK
still visible is compatible with an upstream supply cutoff, but does not identify
its cause or demonstrate a transient waveform. Check the actual CN9 selection,
then scope 5 V input/output of the protection and the radio 3.3 V during CHIP_EN
assertion. Do not select extra bulk capacitance blindly: startup inrush also matters.



## Experimental JPEG (2026-10-17)

`MAP ENCODING JPEG` selects mode 4. RAW remains the boot default. This first
experiment uses a portable CPU baseline grayscale JPEG encoder, not JPEG/VENC
hardware. It uses an 8x8 separable DCT, a fixed uniform quantization table of 12
(not a conventional quality percentage), and canonical fixed-length Huffman
codes. This deliberately simple reference is not an optimal JPEG compressor.
There is no added full-frame buffer, allocation or global mutable codec state.
The transmitting worker encodes; USB MAP and producer ownership are unchanged.

Payload = complete JPEG stream (SOI through EOI) followed by ceil(width*height/8)
validity bytes, with bit i%8 of byte i/8 indicating valid pixel i (row-major,
LSB first). Unused final mask bits are zero. JPEG encodes the existing Q8 codes;
invalid input is zero before JPEG, but validity is determined only by the mask.
Decode valid pixels as base + (max(1, decoded_gray)-1)*step; invalid pixels are
NaN. The existing CRC covers both JPEG and mask. Header remains v2/40 bytes.
The step describes the input quantization, not a bound on JPEG reconstruction
error. Invalid regions and sharp edges can affect neighboring valid pixels.

Encoder scratch lives at the snapshot tail. Output capacity is explicitly
bounded; overflow drops the frame, without silently changing encoding. JPEG
can exceed UINT8 size on noisy scenes. Small dimensions may fail when the
caller provides only raw-sized storage because JPEG headers have fixed cost.

The browser uses pinned jpeg-js 0.4.4, strict decoding, a 0.003 MP resolution
limit and 2 MiB allocation limit, validates dimensions, CRC and mask padding,
and labels JPEG experimental/lossy. Existing RAW/Q16/Q8 and v1 tests pass.
Native C tests decode with independent Pillow and check exact validity, bounds,
and errors; website tests decode the same six C-generated JPEG fixtures. All
30 fixtures passed local HTTP/SignalR/browser integration (not physical Wi-Fi).

Synthetic 54x42 depth cases, bytes including 284-byte mask (excluding header):

| Case | Bytes | Mean absolute error (mm) | Max error (mm) |
| --- | ---: | ---: | ---: |
| Smooth ramp | 836 | 2.70 | 9.72 |
| Step edge | 742 | 1.17 | 31.50 |
| Ramp with invalid holes | 3299 | 7.42 | 31.35 |
| Random depth | 3851 | 59.67 | 288.00 |
| Constant / all invalid | 660 | 0 | 0 |

Commands: `test_tof_jpeg.py --fixtures PATH`, `node --test scripts/test-tof-jpeg.mjs`,
then the existing live/replay codec scripts (now include JPEG).


### JPEG hardware validation

Protected SRAM candidate SHA256
`8d532f1227e5cf9147f707dfa188b3507417ae2f13f0a03f98f46349c5e5e8df`,
496836 bytes, heap 369416 (minimum 368640), preserve-config/BLE-only profile.
Normal build restored locally: 496620 bytes, heap 369640. No NOR programming
or production deployment. The guarded candidate remains running in RAM.

PASS RAW -> UINT16 -> UINT8 -> JPEG -> RAW on real BLE: 34 total frames,
zero CRC/assembly drops. Production browser decoder replay accepted RAW 13,
UINT16 7, UINT8 7, JPEG 7. JPEG payloads including mask were 2320..2331 bytes;
CLI command maximum observed 143.91 ms during the bounded test. These are
scene-dependent samples, not an endurance or worst-case latency guarantee.
USB MAP ON with JPEG selected produced 15 advancing 54x42 ANSI maps and final
CLI ping passed. Encoding restored to RAW and MAP stopped. All owned hardware
handles and lease closed. Evidence is in `.local-dependencies/diagnostics/jpeg-20261017/`.
Physical Wi-Fi and browser visual acceptance remain pending; Cloud test was local.
Actual JPEG depth error was not measured against the same physical RAW frame;
error values above are synthetic paired tests, not moving-scene estimates.

## Deployed browser verification (2026-10-17)

The production Azure asset `index-evJ6nRQA.js` matches the local deployment
(SHA256 `64e1a20e2be9db878e2fcdd94914a3e417b460317e27e19b18bdc2ed2747b868`).
Actual Chrome Web Bluetooth receipt and visible 54x42 depth rendering passed:

| Encoding | Payload bytes | Advancing frame IDs | CRC-accepted count |
| --- | ---: | --- | --- |
| RAW | 9072 | 424364 -> 424395 | 30 -> 33 |
| UINT16 | 4536 | 424581 -> 424617 | 61 -> 68 |
| UINT8 | 2268 | 424789 -> 424825 | 115 -> 129 |
| JPEG | 2210..2268 | 425032 -> 425068 | 202 -> 214 |

Displayed assembly/CRC errors and drops stayed zero. These are short live
observations, not an endurance test. JPEG is scene-dependent and lossy.
The browser BLE connection was disconnected before the controlled RAM reload.
Saved Wi-Fi subsequently restored and obtained an IP address. The old Cloud
pairing received HTTP403; the user explicitly authorized re-pairing in the same
workspace. Read-only firmware rejected pairing before network submission.
The initial write-enabled helper failed the heap gate (367272 < 368640) and
was not loaded. Wi-Fi image acceptance is still pending at this checkpoint.

### Physical Wi-Fi / Azure / Chrome result

PASS on the read-only guarded candidate
`c6cca6f17490d40ec2817567cc630cfe6d2ce89ff4ccca2b1ea34d25d3368ef8`
(heap 369416, binary 496836, W61_CONFIG_PRESERVE=1, APP_DEMO_BLE_ONLY=0).
The user-authorized pairing was persisted using a temporary Core/Src -Os,
write-enabled RAM helper `e29535ce7f82017a410612702318de1c580c577fed1e2206828552a344a1f09a`
(heap 401384). The helper was replaced by the exact read-only candidate before
this matrix. Saved Wi-Fi and the new pairing restored automatically after reload.
No firmware NOR programming, signing, version change or Wi-Fi credential change.

| Encoding | Payload bytes | Advancing browser frame IDs | Displayed CRCs |
| --- | ---: | --- | --- |
| RAW | 9072 | 425 -> 478 | 8A0F379F -> 9623159F |
| UINT16 | 4536 | 936 -> 941 | AA3AAE10 -> 1838DD81 |
| UINT8 | 2268 | 1112 -> 1134 | 1C82E6B2 -> 85096955 |
| JPEG | 2229 -> 2189 | 1273 -> 1308 | 4C03FBFB -> 7744349D |

The real production browser rendered the colored depth map; screenshot also
showed JPEG frame1409, payload2188, CRCE2CD858E. The browser decoder validates
header/payload CRC before publishing a frame. Final firmware status: 231 sent,
0 dropped, 0 request errors, HTTP202. No Cloud CLI round trip was accepted as
part of this run: encoding commands used USB, while frame receipt/rendering
used actual Wi-Fi -> Azure -> Chrome. A browser input action did not populate
the command field. This does not affect the observed image-transfer results.
Short observations establish all four modes, not endurance, maximum frame rate
or latency bounds (Cloud worker max step3436ms observed).
Encoding restored to RAW, Cloud left streaming for the user. New workspace
metadata needs saving in the browser; the save action was invoked, completion
awaits the user's native save dialog. Temporary build flags restored.

Normal local build restored: binary496620, heap369640; not loaded to hardware.
Guarded startup explicitly reports settings load result0/writes0. All owned
serial/debugger handles closed and exclusive hardware lease released.


## Frame-bound NPU metadata (2026-10-17)

The processing task passes its copied RPS status immediately after inference
alongside the exact image pixels. Publication accepts a result only when enabled,
ready, successful, with a nonzero run count and matching sensor frame. Otherwise
it publishes an explicit inactive/not-ready/no-result state and zero result fields.
Both worker routes retain this metadata for the lifetime of the single snapshot;
no sender samples the latest NPU status while transmitting an older image.

The BLE and Cloud viewers display `NPU לתמונה` from this header. The existing
independent fast NPU characteristic remains unchanged and the BLE viewer labels
it `NPU מהיר`. Old images show that no attached inference is available. A later
fast notification never changes the decision displayed beside an older image.
CLI HELP now lists MAP ENCODING, all four choices, and the USB exclusion.

Validation: 90 native C codec cases, six JPEG/Pillow cases, 70 browser decoder/NPU
tests, and 60 C-generated v2/v3 fixtures through local HTTP -> SignalR -> browser
decoder passed. Tests reject mismatched NPU frame IDs, changed metadata between
fragments, invalid states/classes/scores/reserved fields, stale data in inactive
states, and corrupted/truncated headers. Frontend build/lint and .NET build pass.
Normal Non-Secure build: binary496924, heap369352 (minimum368640).
No new hardware load, production deployment or firmware signing in this update;
previous live RF results above apply to v2. Deploy the backward-compatible site
and server before loading a v3 firmware. No Generate Code required.
