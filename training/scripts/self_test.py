"""Fast synthetic tests for framing, resynchronization and preprocessing."""

from __future__ import annotations

import io
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from dataset import (flatten_binary_silhouette, load_device_model_input_record,
                     nearest_connected_component, preprocess_depth,
                     resize_nearest_centered, save_depth_sample)
from common import TRAINING_ROOT, atomic_json, load_json
from protocol import (VERSION_V2, VERSION_V3, FrameReader, build_test_record)
from radio_hil import load_feature_flags, validate_radio_cli


def main() -> int:
    feature_flags = load_feature_flags(TRAINING_ROOT.parent)
    assert feature_flags == {"radio": True, "ble": True, "wifi": False}
    radio_text = """
ST67 hardware baseline:
  build: radio enabled, BLE GATT enabled, Wi-Fi services disabled
ST67 radio status:
  manager: ready
  W6X_Init: passed
  BLE maintenance GATT: ready, advertising: on, link: disconnected
  Wi-Fi services: disabled
SDK: 2.0.106.0, AT: 1.0.0.0
BLE GATT: ready, link: disconnected, advertising: on, MTU: 23
BLE init stage: 13, last W6X status: 0
Name: N6-MAINT-1234
Address: 00:11:22:33:44:55
"""
    radio_report = validate_radio_cli(radio_text, feature_flags, "2.0.106")
    assert radio_report["result"] == "pass"
    assert radio_report["observed_sdk_version"] == "2.0.106"
    assert radio_report["ble"]["device_name"] == "N6-MAINT-1234"

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
    stage5 = np.zeros((5, 7), dtype=np.uint8)
    stage5[1:4, 1:6] = 32
    stage5[2, 3] = 0
    aggressive = flatten_binary_silhouette(stage5)
    assert set(np.unique(aggressive).tolist()) <= {0, 255}
    assert aggressive[2, 3] == 255
    assert np.all(aggressive[stage5 > 0] == 255)
    assert np.count_nonzero(flatten_binary_silhouette(
        np.zeros((5, 7), dtype=np.uint8)
    )) == 0
    resize_source = np.arange(12, dtype=np.uint8).reshape(3, 4) + 1
    resized = resize_nearest_centered(
        resize_source, 10, 8, 0, preserve_aspect=True, border_pixels=2
    )
    assert resized.shape == (8, 10)
    assert not resized[0].any() and not resized[-1].any()
    assert not resized[:, 0].any() and not resized[:, -1].any()
    cfg = load_json(TRAINING_ROOT / "config" / "preprocessing.json")
    assert int(cfg["binary_foreground_threshold"]) == 210
    threshold_probe = np.zeros((5, 9), dtype=np.uint8)
    threshold_probe[1:4, 1:4] = 255
    threshold_probe[1:4, 6:9] = 200
    thresholded = flatten_binary_silhouette(
        threshold_probe,
        threshold=int(cfg["binary_foreground_threshold"]),
        dilation_iterations=int(cfg["binary_dilation_iterations"]),
    )
    assert thresholded[2, 2] == 255
    assert thresholded[2, 7] == 0
    sloped_sheet = np.full((42, 54), 1000, dtype=np.uint16)
    sloped_sheet[12:26, 20:32] = (
        220 + np.arange(12, dtype=np.uint16)[None, :] * 30
    )
    sloped_valid = ((sloped_sheet >= int(cfg["near_mm"])) &
                    (sloped_sheet <= int(cfg["model_max_distance_mm"])))
    grown_sheet = nearest_connected_component(sloped_sheet, sloped_valid, cfg)
    # Total relief is 330 mm (> the 220 mm seed band), but every neighboring
    # column differs by only 30 mm, so the entire physical sheet must survive.
    assert np.all(grown_sheet[12:26, 20:32])
    assert int(grown_sheet.sum()) == 14 * 12
    record_v3 = build_test_record(
        depth, frame_id=125, timestamp_ms=656, protocol_version=VERSION_V3,
        npu_scores=(-120, 17, -40, -90), npu_class_id=1,
        npu_valid=True, npu_runs=43, model_input=tensor[..., 0],
    )
    frame_v3 = FrameReader(io.BytesIO(record_v3)).read_frame(timeout=1.0)
    assert frame_v3.protocol_version == VERSION_V3
    assert frame_v3.model_frame_id == frame_v3.frame_id == 125
    assert (frame_v3.model_width, frame_v3.model_height) == (64, 50)
    assert frame_v3.model_input is not None
    assert np.array_equal(frame_v3.model_input, tensor[..., 0])
    assert frame_v3.model_flags & 0x3 == 0x3
    # A hand with the same outline at different absolute distances and internal
    # relief must yield the same binary model input.
    near_hand = np.full((42, 54), 1000, dtype=np.uint16)
    far_hand = near_hand.copy()
    relief = np.tile(np.arange(12, dtype=np.uint16), (14, 1)) * 4
    near_hand[12:26, 20:32] = 300 + relief
    far_hand[12:26, 20:32] = 500 + relief
    assert np.array_equal(preprocess_depth(near_hand), preprocess_depth(far_hand))
    assert set(np.unique(preprocess_depth(near_hand)).tolist()) <= {0, 255}
    bordered_hand = preprocess_depth(near_hand)[..., 0]
    assert not bordered_hand[0].any() and not bordered_hand[-1].any()
    assert not bordered_hand[:, 0].any() and not bordered_hand[:, -1].any()
    # The production contract is inclusive at 600 mm and completely rejects
    # an otherwise valid connected object beyond it.
    at_limit = np.full((42, 54), 1000, dtype=np.uint16)
    at_limit[12:26, 20:32] = 600
    beyond_limit = np.full((42, 54), 1000, dtype=np.uint16)
    beyond_limit[12:26, 20:32] = 601
    assert np.any(preprocess_depth(at_limit) == 255)
    assert np.count_nonzero(preprocess_depth(beyond_limit)) == 0
    # Keep temporary sample I/O outside the Dropbox-backed workspace; Dropbox
    # can transiently lock freshly written directories during test cleanup.
    with tempfile.TemporaryDirectory() as temporary_root:
        isolated_training_root = Path(temporary_root)
        temporary_session = isolated_training_root / "session"
        with patch("dataset.TRAINING_ROOT", isolated_training_root):
            device_tensor = preprocess_depth(near_hand)[..., 0]
            saved = save_depth_sample(
                temporary_session, "rock", "bit_exact", near_hand,
                {"source": "synthetic_n6df_v3"},
                device_model_input=device_tensor,
            )
            restored = load_device_model_input_record(saved)
            assert restored is not None
            assert np.array_equal(restored, device_tensor)
            assert saved["model_input_source"].startswith("device_n6df_v3")
            mismatched = device_tensor.copy()
            mismatched[0, 0] ^= 0xFF
            try:
                save_depth_sample(
                    temporary_session, "rock", "must_fail", near_hand,
                    {"source": "synthetic_n6df_v3"},
                    device_model_input=mismatched,
                )
            except ValueError as exc:
                assert "device/Python preprocessing mismatch" in str(exc)
            else:
                raise AssertionError("mismatched device tensor was saved")
    # Tiny close speckles may be nearer than the hand but must not stretch its
    # crop or become the learned object.
    noisy_hand = near_hand.copy()
    noisy_hand[0, 0] = 120
    noisy_hand[2, 52] = 130
    noisy_hand[40, 1] = 140
    assert np.array_equal(preprocess_depth(noisy_hand), preprocess_depth(near_hand))
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
    corrupted_model = bytearray(record_v3)
    corrupted_model[-1] ^= 0x01
    corrupt_model_reader = FrameReader(io.BytesIO(corrupted_model))
    try:
        corrupt_model_reader.read_frame(timeout=0.05)
    except TimeoutError:
        pass
    else:
        raise AssertionError("corrupted model tensor unexpectedly passed CRC")
    assert corrupt_model_reader.crc_errors == 1
    prepare_path = Path(__file__).with_name("04_prepare_dataset.py")
    prepare_spec = importlib.util.spec_from_file_location(
        "n6_prepare_self_test", prepare_path
    )
    assert prepare_spec and prepare_spec.loader
    prepare = importlib.util.module_from_spec(prepare_spec)
    prepare_spec.loader.exec_module(prepare)
    train_path = Path(__file__).with_name("05_train_model.py")
    train_spec = importlib.util.spec_from_file_location(
        "n6_train_self_test", train_path
    )
    assert train_spec and train_spec.loader
    train = importlib.util.module_from_spec(train_spec)
    train_spec.loader.exec_module(train)
    analysis_path = Path(__file__).with_name("analyze_training.py")
    analysis_spec = importlib.util.spec_from_file_location(
        "n6_analysis_self_test", analysis_path
    )
    assert analysis_spec and analysis_spec.loader
    analysis = importlib.util.module_from_spec(analysis_spec)
    analysis_spec.loader.exec_module(analysis)
    # Firmware scans classes with strict `>` and therefore keeps the first
    # class when quantized scores tie. The report must explain the same result.
    selected, confidence, margin, tied = analysis.summarize_scores(
        np.asarray([-126, -17, -17, -96], dtype=np.int8)
    )
    assert selected == 1 and confidence == -17.0 and margin == 0.0 and tied
    metrics = analysis.classification_metrics(
        [0, 0, 1, 1], [0, 1, 1, 1], 2
    )
    assert metrics["matrix"] == [[1, 1], [0, 2]]
    assert metrics["accuracy"] == 0.75
    augmentation = {
        "copies_per_sample": 2,
        "horizontal_flip_probability": 0.5,
        "maximum_translation_pixels": 4,
        "intensity_scale_min": 1.0,
        "intensity_scale_max": 1.0,
    }
    batch = np.stack([preprocess_depth(near_hand)] * 2)
    labels = np.asarray([1, 2], dtype=np.uint8)
    augmented_a = train.augment_training_set(batch, labels, augmentation, 657)
    augmented_b = train.augment_training_set(batch, labels, augmentation, 657)
    assert np.array_equal(augmented_a[0], augmented_b[0])
    assert np.array_equal(augmented_a[1], augmented_b[1])
    assert augmented_a[0].shape[0] == 6
    assert set(np.unique(augmented_a[0]).tolist()) <= {0, 255}
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
            assignment[f"{label}-{group}"] for group in range(3)
        }
        assert label_splits == {"train", "validation", "test"}
    mixed_rows = grouped_rows + [{
        "label": "rock", "burst_id": "paper-0",
        "depth_sha256": "reviewed-rock-inside-paper-burst",
    }]
    mixed_assignment = prepare.assign_groups(
        mixed_rows, 657,
        {"train": 70, "validation": 15, "test": 15}, 3, 1, 0.30,
    )
    assert "paper-0" in mixed_assignment
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
        raise AssertionError("per-class burst shortage was not rejected")
    print("Synthetic N6DF CRC/resynchronization/preprocessing tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
