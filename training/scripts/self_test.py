"""Fast synthetic tests for framing, resynchronization and preprocessing."""

from __future__ import annotations

import io
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from dataset import preprocess_depth
from common import atomic_json, load_json
from protocol import (VERSION_V2, FrameReader, build_test_record)


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary_root:
        state_path = Path(temporary_root) / "state.json"
        real_replace = __import__("os").replace
        attempts = 0

        def transient_replace(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError("simulated Dropbox sharing violation")
            real_replace(source, destination)

        with patch("common.os.replace", side_effect=transient_replace):
            atomic_json(state_path, {"epoch": 7})
        assert attempts == 3 and load_json(state_path) == {"epoch": 7}

    depth = np.arange(54 * 42, dtype=np.uint16).reshape(42, 54) + 100
    depth[0, 0] = 0xFFFF
    record = build_test_record(depth, frame_id=123, timestamp_ms=456)
    reader = FrameReader(io.BytesIO(b"unrelated CLI text\r\n" + record + b"tail"))
    frame = reader.read_frame(timeout=1.0)
    assert frame.frame_id == 123 and frame.timestamp_ms == 456
    assert np.array_equal(frame.depth_mm, depth)
    record_v2 = build_test_record(
        depth, frame_id=124, timestamp_ms=556, protocol_version=VERSION_V2,
        npu_scores=(-120, 17, -40, -90), npu_class_id=1,
        npu_valid=True, npu_runs=42,
    )
    frame_v2 = FrameReader(io.BytesIO(record_v2)).read_frame(timeout=1.0)
    assert frame_v2.protocol_version == VERSION_V2
    assert frame_v2.npu_valid and frame_v2.npu_frame_id == 124
    assert frame_v2.npu_scores == (-120, 17, -40, -90)
    assert frame_v2.npu_class_id == 1 and frame_v2.npu_runs == 42
    tensor = preprocess_depth(depth)
    assert tensor.shape == (50, 64, 1)
    assert tensor.dtype == np.uint8
    false_marker = FrameReader(io.BytesIO(b"Dataset stream: N6DF v1\r\n" + record))
    assert false_marker.read_frame(timeout=1.0).frame_id == 123
    assert false_marker.framing_errors == 1
    assert false_marker.crc_errors == 0
    corrupted = bytearray(record)
    corrupted[-1] ^= 0x01
    corrupt_reader = FrameReader(io.BytesIO(corrupted))
    try:
        corrupt_reader.read_frame(timeout=0.05)
    except TimeoutError:
        pass
    else:
        raise AssertionError("corrupted payload unexpectedly passed CRC")
    assert corrupt_reader.crc_errors == 1
    prepare_path = Path(__file__).with_name("04_prepare_dataset.py")
    prepare_spec = importlib.util.spec_from_file_location(
        "n6_prepare_self_test", prepare_path
    )
    assert prepare_spec and prepare_spec.loader
    prepare = importlib.util.module_from_spec(prepare_spec)
    prepare_spec.loader.exec_module(prepare)
    classes = ("none", "rock", "paper", "scissors")
    grouped_rows = [
        {"label": label, "burst_id": f"{label}-{group}",
         "depth_sha256": f"{label}-{group}-hash"}
        for label in classes for group in range(3)
    ]
    assignment = prepare.assign_groups(
        grouped_rows, 657,
        {"train": 70, "validation": 15, "test": 15}, 3, 1, 0.30,
    )
    for label in classes:
        label_splits = {
            assignment[f"{label}:{label}-{group}"] for group in range(3)
        }
        assert label_splits == {"train", "validation", "test"}
    deficient = [row for row in grouped_rows
                 if not (row["label"] in ("rock", "paper") and
                         row["burst_id"].endswith("-2"))]
    try:
        prepare.assign_groups(
            deficient, 657,
            {"train": 70, "validation": 15, "test": 15}, 3, 1, 0.30,
        )
    except RuntimeError as exc:
        assert "rock=2" in str(exc) and "paper=2" in str(exc)
    else:
        raise AssertionError("multi-class burst shortage was not rejected")
    print("Synthetic N6DF CRC/resynchronization/preprocessing tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
