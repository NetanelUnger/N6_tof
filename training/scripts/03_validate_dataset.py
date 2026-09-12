"""Stage 03: validate geometry, metadata, duplicates, range and class balance."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict

import numpy as np

from common import (CONFIG_ROOT, RAW_ROOT, REPORTS_ROOT, TRAINING_ROOT,
                    apply_review, atomic_json, class_names,
                    dataset_input_fingerprint, iter_jsonl, load_json,
                    load_review_decisions, mark_stage, relative, utc_now)
from dataset import (depth_sha256, load_depth_record,
                     load_device_model_input_record, preprocess_depth)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    metadata_files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    if not metadata_files:
        raise RuntimeError("No captured metadata found. Run 01_CAPTURE.bat first.")
    fingerprint = dataset_input_fingerprint(metadata_files)
    review_decisions = load_review_decisions()
    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    training_cfg = load_json(CONFIG_ROOT / "training.json")
    expected = (cfg["source_height"], cfg["source_width"])
    counts: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    sessions_by_class: defaultdict[str, set[str]] = defaultdict(set)
    labels_by_burst: defaultdict[str, set[str]] = defaultdict(set)
    hashes: defaultdict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    warnings: list[str] = []
    invalid_ratios: list[float] = []
    total = 0
    rejected = 0
    reviewed = 0
    relabeled = 0
    device_tensor_records = 0
    host_only_records = 0
    for metadata_path in metadata_files:
        for raw_row in iter_jsonl(metadata_path):
            total += 1
            location = f"{metadata_path.parent.name}:{total}"
            try:
                row = apply_review(raw_row, review_decisions)
                if row.get("reviewed"):
                    reviewed += 1
                if row.get("label") != row.get("original_label"):
                    relabeled += 1
                if not row.get("accepted", True):
                    rejected += 1
                    continue
                label = row["label"]
                if label not in class_names():
                    raise ValueError(f"unknown label {label!r}")
                depth = load_depth_record(row)
                if depth.shape != expected or depth.dtype != np.uint16:
                    raise ValueError(f"shape/dtype {depth.shape}/{depth.dtype}")
                observed_hash = depth_sha256(depth)
                if observed_hash != row.get("depth_sha256"):
                    raise ValueError("depth hash differs from metadata")
                device_tensor = load_device_model_input_record(row)
                if device_tensor is None:
                    host_only_records += 1
                else:
                    device_tensor_records += 1
                    host_tensor = preprocess_depth(depth, cfg)[..., 0]
                    if device_tensor.shape != host_tensor.shape:
                        raise ValueError(
                            "device model-input shape differs from Python"
                        )
                    if set(np.unique(device_tensor).tolist()) - {0, 255}:
                        raise ValueError(
                            "device model-input violates binary 0/255 contract"
                        )
                    device_hash = row.get("device_model_input_sha256")
                    observed_device_hash = hashlib.sha256(
                        device_tensor.tobytes(order="C")
                    ).hexdigest()
                    if device_hash and device_hash != observed_device_hash:
                        raise ValueError("device model-input hash differs")
                    if not np.array_equal(device_tensor, host_tensor):
                        raise ValueError(
                            "device model-input differs from Python preprocessing"
                        )
                for key in ("depth_png", "preview_png", "model_input_png"):
                    if not (TRAINING_ROOT / row[key]).exists():
                        raise ValueError(f"missing {key}: {row[key]}")
                valid = (depth != cfg["invalid_mm"]) & (depth > 0)
                invalid_ratios.append(1.0 - float(valid.mean()))
                counts[label] += 1
                sessions[row.get("session_id", "unknown")] += 1
                sessions_by_class[label].add(row.get("session_id", "unknown"))
                burst = row.get("burst_id")
                if burst:
                    labels_by_burst[
                        f"{row.get('session_id', 'unknown')}:{burst}"
                    ].add(label)
                hashes[observed_hash].append(location)
            except Exception as exc:
                errors.append(f"{location}: {exc}")
    duplicates = {digest: locations for digest, locations in hashes.items()
                  if len(locations) > 1}
    duplicate_count = sum(len(items) - 1 for items in duplicates.values())
    mixed_label_bursts = {
        burst: sorted(labels)
        for burst, labels in labels_by_burst.items()
        if len(labels) > 1
    }
    if duplicate_count:
        warnings.append(f"{duplicate_count} exact duplicate frame(s)")
    if host_only_records:
        warnings.append(
            f"{host_only_records} sample(s) have no N6DF v3 device tensor; "
            "Stage 04 refuses them unless --allow-host-preprocessing is explicit"
        )
    minimum = training_cfg["minimum_samples_per_class"]
    for label in class_names():
        if counts[label] < minimum:
            warnings.append(f"{label}: {counts[label]} < recommended {minimum}")
        minimum_sessions = training_cfg["capture"].get(
            "minimum_sessions_per_class", 1
        )
        if len(sessions_by_class[label]) < minimum_sessions:
            warnings.append(
                f"{label}: {len(sessions_by_class[label])} capture session(s); "
                f"recommended at least {minimum_sessions}"
            )
    report = {
        "schema": 1,
        "created_utc": utc_now(),
        "status": "failed" if errors else "valid_with_warnings" if warnings else "valid",
        "total_records": total,
        "valid_records": sum(counts.values()),
        "reviewed_records": reviewed,
        "rejected_records": rejected,
        "relabeled_records": relabeled,
        "device_tensor_records": device_tensor_records,
        "host_only_records": host_only_records,
        "counts_by_class": dict(counts),
        "counts_by_session": dict(sessions),
        "sessions_by_class": {
            label: sorted(sessions_by_class[label]) for label in class_names()
        },
        "mean_invalid_ratio": float(np.mean(invalid_ratios)) if invalid_ratios else 1.0,
        "exact_duplicate_frames": duplicate_count,
        "duplicate_groups": list(duplicates.values())[:100],
        "mixed_label_bursts": mixed_label_bursts,
        "warnings": warnings,
        "errors": errors[:200],
        "input_fingerprint": fingerprint,
    }
    report_path = REPORTS_ROOT / "dataset_validation.json"
    atomic_json(report_path, report)
    mark_stage("03_validate", status="failed" if errors else "complete",
               inputs=fingerprint, outputs=[relative(report_path)],
               details={"records": total, "warnings": len(warnings),
                        "errors": len(errors), "reviewed": reviewed,
                        "rejected": rejected, "relabeled": relabeled})
    print(f"Validated {total} records: {sum(counts.values())} usable, "
          f"{rejected} rejected by review, {relabeled} relabeled, "
          f"{len(errors)} errors, {len(warnings)} warnings.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if mixed_label_bursts:
        print(
            f"INFO: {len(mixed_label_bursts)} reviewed burst(s) contain multiple "
            "labels; Stage 04 will keep every such burst intact in one split."
        )
    for error in errors[:20]:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
