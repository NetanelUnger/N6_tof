"""Stage 04: preprocess and split by capture burst, never adjacent frame."""

from __future__ import annotations

import argparse
import hashlib
import itertools
from collections import Counter, defaultdict

import numpy as np

from common import (CONFIG_ROOT, PREPARED_ROOT, RAW_ROOT, REPORTS_ROOT,
                    atomic_json, class_names, file_fingerprint, is_stage_current,
                    iter_jsonl, load_json, mark_stage, relative, stable_hash,
                    utc_now)
from dataset import load_depth_record, preprocess_depth

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
    groups: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        group = row.get("burst_id") or row.get("session_id") or row["depth_sha256"]
        groups[f"{row['label']}:{group}"].append(row)
    assignment: dict[str, str] = {}
    by_label: defaultdict[str, list[str]] = defaultdict(list)
    for group in groups:
        by_label[group.split(":", 1)[0]].append(group)
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
    args = parser.parse_args()
    metadata_files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    validation_path = REPORTS_ROOT / "dataset_validation.json"
    if not validation_path.exists():
        raise RuntimeError("Run 03_VALIDATE.bat before preparing the dataset.")
    validation = load_json(validation_path)
    if validation["status"] == "failed":
        raise RuntimeError("Dataset validation failed; inspect reports/dataset_validation.json")
    current_metadata_fingerprint = file_fingerprint(metadata_files)
    if validation.get("input_fingerprint") != current_metadata_fingerprint:
        raise RuntimeError(
            "The raw dataset changed after its validation report was created. "
            "Run 03_VALIDATE.bat again, then repeat this stage."
        )
    cfg_paths = [CONFIG_ROOT / "preprocessing.json",
                 CONFIG_ROOT / "training.json", CONFIG_ROOT / "classes.json"]
    fingerprint = stable_hash({
        "metadata": file_fingerprint(metadata_files),
        "raw_npz": file_fingerprint(RAW_ROOT.glob("*/*/*.npz")),
        "configs": file_fingerprint(cfg_paths),
    })
    output_paths = [PREPARED_ROOT / f"{split}.npz"
                    for split in ("train", "validation", "test")]
    manifest_path = PREPARED_ROOT / "manifest.json"
    if not args.force and is_stage_current("04_prepare", fingerprint,
                                           output_paths + [manifest_path]):
        print("Prepared dataset is current; nothing to rebuild. Use --force to redo it.")
        return 0
    all_rows = [row for path in metadata_files for row in iter_jsonl(path)
                if row.get("accepted", True)]
    # An exact image can be present after repeated imports. Keeping one copy
    # prevents the same measurement from leaking across split groups.
    rows_by_hash = {}
    for row in all_rows:
        rows_by_hash.setdefault(row["depth_sha256"], row)
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
    for row in rows:
        group_id = f"{row['label']}:{row.get('burst_id') or row.get('session_id') or row['depth_sha256']}"
        split = assignment[group_id]
        tensor = preprocess_depth(load_depth_record(row), pre_cfg)
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
            "capture burst kept intact; deterministic sample-balanced "
            "assignment with per-class holdout gates"
        ),
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
