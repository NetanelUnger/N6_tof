# N6DF v4 classification/data contract

This extends the USB training record to 2–16 explicitly mapped classes.
The Python decoder still accepts v1/v2/v3; legacy inference has four scores and
no transmitted contract identifier. New firmware emits a fixed 132-byte header.
All multibyte integers are little endian. The payload remains lossless uint16
depth followed by the exact uint8 input tensor for the same frame.

| Offset | Field |
|---:|---|
| 0–43 | v3 common raw-depth metadata, with version 4/header size 132 |
| 44 | inference sensor frame ID, u32 |
| 48 | 16 signed int8 score slots; unused slots filled with -128 |
| 64,65 | class index and validity, u8 |
| 66 | confidence per mille, u16 |
| 68 | inference run counter, u32 |
| 72,74 | model width/height, u16 |
| 76,78 | model format/flags, u16 |
| 80,84,88 | tensor payload bytes, tensor frame ID, tensor CRC32, u32 |
| 92,93 | class count (2–16), reserved zero, u8 |
| 94 | model contract version 1, u16 |
| 96 | complete model-contract SHA-256, 32 bytes |
| 128 | CRC32 over bytes 0–127 |

Tensor flags: bit 0 exact pre-inference device input; bit 1 binary silhouette;
bit 2 Helium resize/copy path. Spatial-depth tensors set exact but not binary.
Each payload has its own CRC32. Reject invalid counts, indices, versions,
dimensions, frame associations and CRCs before committing a sample. Never
substitute an inference from another frame. The contract binds stable class
UUIDs/output indices, display names, profile/preprocessing, boundary shape and
quantization, project semantics, and the exact TFLite hash.

Stage 08 generates `n6_model_contract.h`; firmware statically checks generated
network boundary types and element counts. Header generation is centralized;
users do not edit firmware class counts/names. Legacy wireless viewer formats
cannot represent arbitrary class mappings, so their RPS inference fields are
suppressed for non-RPS contracts; new training transports must use the complete
general record. This is not acceptance of the M4/M5 capture implementations.

The full-field spatial profile preserves absolute depth and image position,
uses nearest-neighbour pixel-center sampling to 64x50, clips valid distances to
the configured near/far range, maps them into 1..255 with integer rounding, and
encodes invalid depth as 0. It does not crop/select/dilate an object. The
production C helper and Python implementation are byte-exact in native tests.
