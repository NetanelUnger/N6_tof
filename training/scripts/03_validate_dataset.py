"""Stage 03: validate geometry, metadata, duplicates, range and class balance."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

import numpy as np

from common import (CONFIG_ROOT, RAW_ROOT, REPORTS_ROOT, TRAINING_ROOT,
                    atomic_json, class_names, file_fingerprint, iter_jsonl,
                    load_json, mark_stage, relative, utc_now)
from dataset import depth_sha256, load_depth_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    metadata_files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    if not metadata_files:
        raise RuntimeError("No captured metadata found. Run 01_CAPTURE.bat first.")
    fingerprint = file_fingerprint(metadata_files)
    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    training_cfg = load_json(CONFIG_ROOT / "training.json")
    expected = (cfg["source_height"], cfg["source_width"])
    counts: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    hashes: defaultdict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    warnings: list[str] = []
    invalid_ratios: list[float] = []
    total = 0
    for metadata_path in metadata_files:
        for row in iter_jsonl(metadata_path):
            total += 1
            location = f"{metadata_path.parent.name}:{total}"
            try:
                label = row["label"]
                if label not in class_names():
                    raise ValueError(f"unknown label {label!r}")
                depth = load_depth_record(row)
                if depth.shape != expected or depth.dtype != np.uint16:
                    raise ValueError(f"shape/dtype {depth.shape}/{depth.dtype}")
                observed_hash = depth_sha256(depth)
                if observed_hash != row.get("depth_sha256"):
                    raise ValueError("depth hash differs from metadata")
                for key in ("depth_png", "preview_png"):
                    if not (TRAINING_ROOT / row[key]).exists():
                        raise ValueError(f"missing {key}: {row[key]}")
                valid = (depth != cfg["invalid_mm"]) & (depth > 0)
                invalid_ratios.append(1.0 - float(valid.mean()))
                counts[label] += 1
                sessions[row.get("session_id", "unknown")] += 1
                hashes[observed_hash].append(location)
            except Exception as exc:
                errors.append(f"{location}: {exc}")
    duplicates = {digest: locations for digest, locations in hashes.items()
                  if len(locations) > 1}
    duplicate_count = sum(len(items) - 1 for items in duplicates.values())
    if duplicate_count:
        warnings.append(f"{duplicate_count} exact duplicate frame(s)")
    minimum = training_cfg["minimum_samples_per_class"]
    for label in class_names():
        if counts[label] < minimum:
            warnings.append(f"{label}: {counts[label]} < recommended {minimum}")
    report = {
        "schema": 1,
        "created_utc": utc_now(),
        "status": "failed" if errors else "valid_with_warnings" if warnings else "valid",
        "total_records": total,
        "valid_records": sum(counts.values()),
        "counts_by_class": dict(counts),
        "counts_by_session": dict(sessions),
        "mean_invalid_ratio": float(np.mean(invalid_ratios)) if invalid_ratios else 1.0,
        "exact_duplicate_frames": duplicate_count,
        "duplicate_groups": list(duplicates.values())[:100],
        "warnings": warnings,
        "errors": errors[:200],
        "input_fingerprint": fingerprint,
    }
    report_path = REPORTS_ROOT / "dataset_validation.json"
    atomic_json(report_path, report)
    mark_stage("03_validate", status="failed" if errors else "complete",
               inputs=fingerprint, outputs=[relative(report_path)],
               details={"records": total, "warnings": len(warnings),
                        "errors": len(errors)})
    print(f"Validated {total} records: {sum(counts.values())} usable, "
          f"{len(errors)} errors, {len(warnings)} warnings.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors[:20]:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

