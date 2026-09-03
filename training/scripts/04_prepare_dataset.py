"""Stage 04: preprocess and split by capture burst, never adjacent frame."""

from __future__ import annotations

import argparse
import hashlib
import itertools
from collections import Counter, defaultdict

import numpy as np

from common import (CONFIG_ROOT, PREPARED_ROOT, RAW_ROOT, REPORTS_ROOT,
                    atomic_json, class_names, dataset_input_fingerprint,
                    file_fingerprint, is_stage_current, load_json, mark_stage,
                    relative, reviewed_rows, stable_hash, utc_now)
from dataset import (load_depth_record, load_device_model_input_record,
                     preprocess_depth)

SPLITS = ("train", "validation", "test")


def candidate_assignments(sizes: list[int], targets: tuple[float, ...]):
    """Yield deterministic split choices; use a bounded beam for many bursts."""
    if len(sizes) <= 12:
        yield from itertools.product(range(len(SPLITS)), repeat=len(sizes))
        return
    states: dict[tuple[int, ...], tuple[int, ...]] = {
        (0, 0, 0, 0, 0, 0): ()
    }
    for size in sizes:
        expanded: dict[tuple[int, ...], tuple[int, ...]] = {}
        for state, choices in states.items():
            counts = state[:3]
            group_counts = state[3:]
            for split_index in range(3):
                next_counts = list(counts)
                next_group_counts = list(group_counts)
                next_counts[split_index] += size
                next_group_counts[split_index] += 1
                key = tuple(next_counts + next_group_counts)
                expanded.setdefault(key, choices + (split_index,))
        if len(expanded) > 20000:
            def partial_score(item):
                counts = item[0][:3]
                return sum(abs(counts[index] - targets[index]) /
                           max(1.0, targets[index]) for index in range(3))
            states = dict(sorted(expanded.items(), key=partial_score)[:20000])
        else:
            states = expanded
    yield from states.values()


def assign_groups(rows: list[dict], seed: int,
                  percentages: dict[str, int],
                  minimum_groups: int,
                  minimum_split_samples: int,
                  minimum_train_fraction: float) -> dict[str, str]:
    def group_id(row: dict) -> str:
        burst = row.get("burst_id")
        session = row.get("session_id")
        if burst:
            return f"{session}:{burst}" if session else str(burst)
        if session:
            return f"{session}:{row['depth_sha256']}"
        return str(row["depth_sha256"])

    groups: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[group_id(row)].append(row)
    assignment: dict[str, str] = {}
    by_label: defaultdict[str, list[str]] = defaultdict(list)
    labels_by_group: dict[str, set[str]] = {}
    for group, group_rows in groups.items():
        labels_by_group[group] = {str(row["label"]) for row in group_rows}
        for label in labels_by_group[group]:
            by_label[label].append(group)
    shortages = [
        (label, len(by_label[label]))
        for label in class_names()
        if len(by_label[label]) < minimum_groups
    ]
    if shortages:
        summary = ", ".join(
            f"{label}={count} (need {minimum_groups - count} more)"
            for label, count in shortages
        )
        raise RuntimeError(
            f"Not enough independent capture bursts: {summary}. Resume "
            "01_CAPTURE.bat, select each listed class and record the missing "
            "SPACE-delimited burst(s), then rerun 03_VALIDATE.bat and this stage."
        )
    infeasible = []
    percentage_values = tuple(percentages[split] for split in SPLITS)
    if sum(percentage_values) != 100:
        raise RuntimeError(f"Split percentages must total 100: {percentages}")
    # The common case has one label per capture burst. Preserve the exact,
    # sample-balanced solver used by the original pipeline for that case.
    if any(len(labels) > 1 for labels in labels_by_group.values()):
        names = class_names()
        totals = Counter(str(row["label"]) for row in rows)
        targets = {
            label: tuple(totals[label] * value / 100.0
                         for value in percentage_values)
            for label in names
        }
        ordered = sorted(
            groups,
            key=lambda group: (
                -len(groups[group]),
                hashlib.sha256(f"{seed}:{group}".encode()).hexdigest(),
            ),
        )
        vectors = [Counter(str(row["label"]) for row in groups[group])
                   for group in ordered]
        best: tuple[float, tuple[int, ...]] | None = None
        thresholds = (percentage_values[0],
                      percentage_values[0] + percentage_values[1])
        # A deterministic hash search keeps every physical burst intact while
        # finding a class-balanced split even when human review corrected a few
        # frames inside that burst to different labels.
        for attempt in range(50000):
            choices = []
            split_counts = {label: [0, 0, 0] for label in names}
            split_groups = [0, 0, 0]
            for group, vector in zip(ordered, vectors):
                value = int(hashlib.sha256(
                    f"{seed}:{attempt}:{group}".encode()
                ).hexdigest()[:8], 16) % 100
                split_index = (0 if value < thresholds[0] else
                               1 if value < thresholds[1] else 2)
                choices.append(split_index)
                split_groups[split_index] += 1
                for label, count in vector.items():
                    split_counts[label][split_index] += count
            if min(split_groups) == 0:
                continue
            if any(
                min(split_counts[label]) < minimum_split_samples or
                split_counts[label][0] < totals[label] * minimum_train_fraction
                for label in names
            ):
                continue
            score = sum(
                abs(split_counts[label][index] - targets[label][index]) /
                max(1.0, totals[label])
                for label in names for index in range(3)
            )
            score += 0.1 * sum(
                abs(split_groups[index] - len(ordered) *
                    percentage_values[index] / 100.0) / max(1, len(ordered))
                for index in range(3)
            )
            candidate = (score, tuple(choices))
            if best is None or candidate < best:
                best = candidate
        if best is None:
            summary = ", ".join(
                f"{group}={dict(vectors[index])}"
                for index, group in enumerate(ordered)
                if len(labels_by_group[group]) > 1
            )
            raise RuntimeError(
                "No leakage-safe balanced split was found for reviewed "
                f"multi-label bursts: {summary}. Capture more independent "
                "bursts for the affected classes."
            )
        return {
            group: SPLITS[split_index]
            for group, split_index in zip(ordered, best[1])
        }

    for label in class_names():
        ordered = sorted(
            by_label[label],
            key=lambda group: (
                -len(groups[group]),
                hashlib.sha256(f"{seed}:{group}".encode()).hexdigest(),
            ),
        )
        sizes = [len(groups[group]) for group in ordered]
        total = sum(sizes)
        targets = tuple(total * value / 100.0 for value in percentage_values)
        best: tuple[float, tuple[int, ...]] | None = None
        for choices in candidate_assignments(sizes, targets):
            split_counts = [0, 0, 0]
            split_groups = [0, 0, 0]
            for size, split_index in zip(sizes, choices):
                split_counts[split_index] += size
                split_groups[split_index] += 1
            if (min(split_groups) == 0 or
                    min(split_counts) < minimum_split_samples or
                    split_counts[0] < total * minimum_train_fraction):
                continue
            score = sum(
                abs(split_counts[index] - targets[index]) / max(1.0, total)
                for index in range(3)
            )
            candidate = (score, choices)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            infeasible.append(f"{label}: burst sizes={sizes}")
            continue
        for group, split_index in zip(ordered, best[1]):
            assignment[group] = SPLITS[split_index]
    if infeasible:
        raise RuntimeError(
            "No leakage-safe balanced split satisfies at least "
            f"{minimum_split_samples} samples per class in every split and "
            f"{minimum_train_fraction:.0%} in train. "
            + "; ".join(infeasible)
            + ". Capture more full bursts for the listed class(es), rerun "
              "03_VALIDATE.bat, then repeat this stage."
        )
    return assignment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--allow-host-preprocessing", action="store_true",
        help=("Allow legacy/imported samples without an exact N6DF v3 device "
              "tensor; the normal guided path refuses them"),
    )
    args = parser.parse_args()
    metadata_files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    validation_path = REPORTS_ROOT / "dataset_validation.json"
    if not validation_path.exists():
        raise RuntimeError("Run 03_VALIDATE.bat before preparing the dataset.")
    validation = load_json(validation_path)
    if validation["status"] == "failed":
        raise RuntimeError("Dataset validation failed; inspect reports/dataset_validation.json")
    current_metadata_fingerprint = dataset_input_fingerprint(metadata_files)
    if validation.get("input_fingerprint") != current_metadata_fingerprint:
        raise RuntimeError(
            "The raw dataset or its human review changed after validation. "
            "Run 03_VALIDATE.bat again, then repeat this stage."
        )
    cfg_paths = [CONFIG_ROOT / "preprocessing.json",
                 CONFIG_ROOT / "training.json", CONFIG_ROOT / "classes.json"]
    fingerprint = stable_hash({
        "metadata_and_review": current_metadata_fingerprint,
        "raw_npz": file_fingerprint(RAW_ROOT.glob("*/*/*.npz")),
        "configs": file_fingerprint(cfg_paths),
        "input_contract": "n6df_v3_device_tensor_bit_exact_v1",
        "allow_host_preprocessing": bool(args.allow_host_preprocessing),
    })
    output_paths = [PREPARED_ROOT / f"{split}.npz"
                    for split in ("train", "validation", "test")]
    manifest_path = PREPARED_ROOT / "manifest.json"
    if not args.force and is_stage_current("04_prepare", fingerprint,
                                           output_paths + [manifest_path]):
        print("Prepared dataset is current; nothing to rebuild. Use --force to redo it.")
        return 0
    all_rows = reviewed_rows(metadata_files)
    # An exact image can be present after repeated imports. Keeping one copy
    # prevents the same measurement from leaking across split groups.
    rows_by_hash = {}
    for row in all_rows:
        digest = row["depth_sha256"]
        existing = rows_by_hash.get(digest)
        if (existing is None or
                (not existing.get("device_model_input_sha256") and
                 row.get("device_model_input_sha256"))):
            rows_by_hash[digest] = row
    rows = list(rows_by_hash.values())
    if not rows:
        raise RuntimeError("No accepted dataset records")
    training_cfg = load_json(CONFIG_ROOT / "training.json")
    pre_cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    try:
        assignment = assign_groups(
            rows, training_cfg["seed"], training_cfg["split_percent"],
            training_cfg["capture"]["minimum_bursts_per_class"],
            training_cfg["minimum_samples_per_split_per_class"],
            training_cfg["minimum_train_fraction_per_class"],
        )
    except RuntimeError as exc:
        mark_stage("04_prepare", status="quality_gate_failed",
                   inputs=fingerprint, details={"error": str(exc)})
        raise
    class_to_id = {name: index for index, name in enumerate(class_names())}
    buckets: defaultdict[str, list[tuple[np.ndarray, int, str, str]]] = defaultdict(list)
    device_tensor_records = 0
    host_only_records = 0
    for row in rows:
        burst = row.get("burst_id")
        session = row.get("session_id")
        if burst:
            group_id = f"{session}:{burst}" if session else str(burst)
        elif session:
            group_id = f"{session}:{row['depth_sha256']}"
        else:
            group_id = str(row["depth_sha256"])
        split = assignment[group_id]
        depth = load_depth_record(row)
        host_tensor = preprocess_depth(depth, pre_cfg)
        device_tensor = load_device_model_input_record(row)
        if device_tensor is None:
            host_only_records += 1
            if not args.allow_host_preprocessing:
                raise RuntimeError(
                    "Training sample has no exact N6DF v3 device tensor: "
                    f"{row.get('npz')}. Capture it again with the current "
                    "firmware, or explicitly use --allow-host-preprocessing "
                    "for legacy/imported data without bit-exact device proof."
                )
            tensor = host_tensor
        else:
            device_tensor_records += 1
            if device_tensor.shape != host_tensor.shape[:2]:
                raise RuntimeError(
                    f"Device tensor shape {device_tensor.shape} differs from "
                    f"Python {host_tensor.shape[:2]} for {row.get('npz')}"
                )
            expected_hash = row.get("device_model_input_sha256")
            observed_hash = hashlib.sha256(
                device_tensor.tobytes(order="C")
            ).hexdigest()
            if expected_hash and observed_hash != expected_hash:
                raise RuntimeError(
                    f"Stored device tensor hash differs for {row.get('npz')}"
                )
            if not np.array_equal(device_tensor, host_tensor[..., 0]):
                mismatch = int(np.count_nonzero(
                    device_tensor != host_tensor[..., 0]
                ))
                raise RuntimeError(
                    "Stored device tensor no longer matches Python "
                    f"preprocessing for {row.get('npz')}: {mismatch} pixels"
                )
            tensor = device_tensor[..., np.newaxis]
        buckets[split].append((tensor, class_to_id[row["label"]],
                               row["depth_sha256"], group_id))
    counts = {}
    for split, path in zip(SPLITS, output_paths):
        records = buckets[split]
        if not records:
            raise RuntimeError(
                f"Split {split} is empty. Capture at least three separate SPACE "
                "bursts per class, then rerun validation/preparation."
            )
        x = np.stack([record[0] for record in records]).astype(np.uint8)
        y = np.asarray([record[1] for record in records], dtype=np.uint8)
        hashes = np.asarray([record[2] for record in records], dtype="U64")
        groups = np.asarray([record[3] for record in records], dtype="U128")
        np.savez_compressed(path, x=x, y=y, hashes=hashes, groups=groups)
        counts[split] = {
            "total": len(records),
            "classes": dict(Counter(class_names()[int(value)] for value in y)),
            "groups": len(set(groups.tolist())),
        }
        missing_classes = sorted(set(class_names()) - set(counts[split]["classes"]))
        if missing_classes:
            raise RuntimeError(
                f"Split {split} is missing classes {missing_classes}. Capture "
                "at least three distinct bursts per class and prepare again."
            )
    manifest = {
        "schema": 1,
        "created_utc": utc_now(),
        "input_fingerprint": fingerprint,
        "preprocessing": pre_cfg,
        "classes": class_names(),
        "split_strategy": (
            "physical capture burst kept intact across labels; deterministic "
            "sample-balanced assignment with per-class holdout gates"
        ),
        "device_tensor_records": device_tensor_records,
        "host_only_records": host_only_records,
        "device_tensor_coverage": device_tensor_records / len(rows),
        "host_preprocessing_override": bool(args.allow_host_preprocessing),
        "counts": counts,
    }
    atomic_json(manifest_path, manifest)
    mark_stage("04_prepare", status="complete", inputs=fingerprint,
               outputs=[relative(path) for path in output_paths + [manifest_path]],
               details=counts)
    print(f"Prepared train/validation/test: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
