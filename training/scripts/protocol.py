"""Decoder/encoder for CRC-protected N6DF v1/v2 depth records."""

from __future__ import annotations

import binascii
import struct
import time
from dataclasses import dataclass
from typing import BinaryIO

import numpy as np

MAGIC = b"N6DF"
VERSION_V1 = 1
VERSION_V2 = 2
VERSION = VERSION_V2
HEADER_SIZE_V1 = 48
HEADER_SIZE_V2 = 64
HEADER_SIZE = HEADER_SIZE_V2
PIXEL_FORMAT_DEPTH_U16_MM = 1
HEADER_PREFIX = struct.Struct("<4sHH")
HEADER_V1 = struct.Struct("<4sHHIIHHHHIIHHHHII")
HEADER_V2 = struct.Struct("<4sHHIIHHHHIIHHHHII4bBBHII")


class ProtocolError(RuntimeError):
    pass


class ChecksumError(ProtocolError):
    """A structurally plausible N6DF record failed a CRC32 check."""


@dataclass(frozen=True)
class DepthFrame:
    frame_id: int
    timestamp_ms: int
    width: int
    height: int
    flags: int
    valid_count: int
    minimum_mm: int
    maximum_mm: int
    invalid_mm: int
    processing_filter: int
    payload_crc32: int
    depth_mm: np.ndarray
    protocol_version: int = VERSION_V1
    npu_frame_id: int | None = None
    npu_scores: tuple[int, int, int, int] | None = None
    npu_class_id: int | None = None
    npu_valid: bool = False
    npu_confidence_per_mille: int | None = None
    npu_runs: int | None = None


def crc32(data: bytes | bytearray | memoryview) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def decode_record(header: bytes, payload: bytes) -> DepthFrame:
    if len(header) < HEADER_PREFIX.size:
        raise ProtocolError("N6DF header is truncated")
    magic, version, header_size = HEADER_PREFIX.unpack_from(header)
    if magic != MAGIC or len(header) != header_size:
        raise ProtocolError("invalid N6DF header")
    npu_frame_id = None
    npu_scores = None
    npu_class_id = None
    npu_valid = False
    npu_confidence = None
    npu_runs = None
    if version == VERSION_V1 and header_size == HEADER_SIZE_V1:
        values = HEADER_V1.unpack(header)
        (magic, version, header_size, frame_id, timestamp_ms, width, height,
         pixel_format, flags, payload_size, valid_count, minimum_mm, maximum_mm,
         invalid_mm, processing_filter, payload_crc32, header_crc32) = values
        crc_region = header[:44]
    elif version == VERSION_V2 and header_size == HEADER_SIZE_V2:
        values = HEADER_V2.unpack(header)
        (magic, version, header_size, frame_id, timestamp_ms, width, height,
         pixel_format, flags, payload_size, valid_count, minimum_mm, maximum_mm,
         invalid_mm, processing_filter, payload_crc32, npu_frame_id,
         score0, score1, score2, score3, npu_class_id, npu_ready,
         npu_confidence, npu_runs, header_crc32) = values
        npu_scores = (score0, score1, score2, score3)
        npu_valid = bool(npu_ready) and npu_frame_id == frame_id
        crc_region = header[:60]
    else:
        raise ProtocolError(
            f"unsupported N6DF version/header {version}/{header_size}"
        )
    if pixel_format != PIXEL_FORMAT_DEPTH_U16_MM:
        raise ProtocolError(f"unsupported pixel format {pixel_format}")
    expected_size = width * height * 2
    if payload_size != expected_size or len(payload) != expected_size:
        raise ProtocolError(
            f"payload size mismatch: header={payload_size}, actual={len(payload)}, "
            f"geometry={width}x{height}"
        )
    if crc32(crc_region) != header_crc32:
        raise ChecksumError("header CRC32 mismatch")
    if crc32(payload) != payload_crc32:
        raise ChecksumError("payload CRC32 mismatch")
    depth = np.frombuffer(payload, dtype="<u2").reshape(height, width).copy()
    observed_valid = int(np.count_nonzero(depth != invalid_mm))
    if observed_valid != valid_count:
        raise ProtocolError(
            f"valid pixel count mismatch: header={valid_count}, "
            f"payload={observed_valid}"
        )
    return DepthFrame(frame_id, timestamp_ms, width, height, flags,
                      valid_count, minimum_mm, maximum_mm, invalid_mm,
                      processing_filter, payload_crc32, depth, version,
                      npu_frame_id, npu_scores, npu_class_id, npu_valid,
                      npu_confidence, npu_runs)


class FrameReader:
    """Resynchronizing reader; terminal text between whole records is ignored."""

    def __init__(self, stream: BinaryIO, *, maximum_payload: int = 65536):
        self.stream = stream
        self.maximum_payload = maximum_payload
        self.buffer = bytearray()
        self.discarded_bytes = 0
        self.crc_errors = 0
        self.framing_errors = 0
        self.last_error: str | None = None
        self.last_error_kind: str | None = None

    def _read_some(self) -> None:
        waiting = int(getattr(self.stream, "in_waiting", 0) or 0)
        chunk = self.stream.read(max(1, min(waiting, 8192)))
        if chunk:
            self.buffer.extend(chunk)

    def read_frame(self, timeout: float = 3.0) -> DepthFrame:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            marker = self.buffer.find(MAGIC)
            if marker < 0:
                if len(self.buffer) > len(MAGIC) - 1:
                    discard = len(self.buffer) - (len(MAGIC) - 1)
                    del self.buffer[:discard]
                    self.discarded_bytes += discard
                self._read_some()
                continue
            if marker:
                del self.buffer[:marker]
                self.discarded_bytes += marker
            if len(self.buffer) < HEADER_PREFIX.size:
                self._read_some()
                continue
            try:
                magic, version, header_size = HEADER_PREFIX.unpack_from(self.buffer)
                if (magic != MAGIC or
                        (version, header_size) not in {
                            (VERSION_V1, HEADER_SIZE_V1),
                            (VERSION_V2, HEADER_SIZE_V2),
                        }):
                    raise ProtocolError("implausible header prefix")
                if len(self.buffer) < header_size:
                    self._read_some()
                    continue
                header = bytes(self.buffer[:header_size])
                unpacked = (HEADER_V1.unpack(header) if version == VERSION_V1
                            else HEADER_V2.unpack(header))
                payload_size = unpacked[9]
                if payload_size > self.maximum_payload:
                    raise ProtocolError("implausible header")
                total = header_size + payload_size
                if len(self.buffer) < total:
                    self._read_some()
                    continue
                payload = bytes(self.buffer[header_size:total])
                frame = decode_record(header, payload)
                del self.buffer[:total]
                return frame
            except ChecksumError as exc:
                last_error = exc
                self.last_error = str(exc)
                self.last_error_kind = "crc"
                self.crc_errors += 1
                del self.buffer[0]
            except (ProtocolError, struct.error) as exc:
                # The CLI acknowledgement intentionally contains the literal
                # text "N6DF".  It is a resynchronization candidate, not a
                # corrupted binary frame, so keep it out of the CRC gate.
                last_error = exc
                self.last_error = str(exc)
                self.last_error_kind = "framing"
                self.framing_errors += 1
                del self.buffer[0]
        message = "timed out waiting for a valid N6DF frame"
        if last_error:
            message += f"; last parser error: {last_error}"
        raise TimeoutError(message)


def build_test_record(depth_mm: np.ndarray, frame_id: int = 1,
                      timestamp_ms: int = 100, *,
                      protocol_version: int = VERSION_V1,
                      npu_scores: tuple[int, int, int, int] = (-128, -128, -128, -128),
                      npu_class_id: int = 0,
                      npu_valid: bool = False,
                      npu_runs: int = 0) -> bytes:
    depth = np.asarray(depth_mm, dtype="<u2")
    height, width = depth.shape
    payload = depth.tobytes(order="C")
    valid = depth != 0xFFFF
    valid_values = depth[valid]
    minimum = int(valid_values.min()) if valid_values.size else 0
    maximum = int(valid_values.max()) if valid_values.size else 0
    if protocol_version == VERSION_V1:
        first = HEADER_V1.pack(MAGIC, VERSION_V1, HEADER_SIZE_V1, frame_id,
                               timestamp_ms, width, height,
                               PIXEL_FORMAT_DEPTH_U16_MM, 1, len(payload),
                               int(valid.sum()), minimum, maximum, 0xFFFF, 0,
                               crc32(payload), 0)
        header = first[:44] + struct.pack("<I", crc32(first[:44]))
    elif protocol_version == VERSION_V2:
        best_score = max(npu_scores)
        confidence = ((best_score + 128) * 1000) // 256
        first = HEADER_V2.pack(
            MAGIC, VERSION_V2, HEADER_SIZE_V2, frame_id, timestamp_ms,
            width, height, PIXEL_FORMAT_DEPTH_U16_MM, 1, len(payload),
            int(valid.sum()), minimum, maximum, 0xFFFF, 0, crc32(payload),
            frame_id if npu_valid else 0xFFFFFFFF, *npu_scores,
            npu_class_id, int(npu_valid), confidence, npu_runs, 0,
        )
        header = first[:60] + struct.pack("<I", crc32(first[:60]))
    else:
        raise ValueError(f"unsupported synthetic protocol version {protocol_version}")
    return header + payload
