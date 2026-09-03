"""Review captured frames without deleting or rewriting immutable raw data."""

from __future__ import annotations

import argparse
import json
import os
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, ImageTk
import tkinter as tk
from tkinter import ttk

from common import (CONFIG_ROOT, MODELS_ROOT, RAW_ROOT, REVIEW_PATH,
                    REVIEW_ROOT, TRAINING_ROOT, atomic_json, class_names,
                    dataset_input_fingerprint, file_fingerprint, iter_jsonl,
                    load_json, load_review_decisions, mark_stage, relative,
                    sha256_file, stable_hash, utc_now)
from dataset import (load_depth_record, nearest_connected_component,
                     preprocess_depth)


ANALYSIS_PATH = REVIEW_ROOT / "automatic_analysis.json"
FLAG_TEXT = {
    "no_foreground": "לא נמצא אובייקט קרוב אחרי preprocessing",
    "touches_sensor_edge": "האובייקט נוגע בגבול החיישן ועלול להיות חתוך",
    "foreground_outlier": "גודל האובייקט חריג ביחס למחלקה",
    "exact_duplicate": "קיימת תמונה זהה נוספת",
    "model_disagrees": "המודל הקיים אינו מסכים עם ה-label",
    "low_confidence": "למודל הקיים confidence נמוך",
}


def metadata_files() -> list[Path]:
    files = sorted(RAW_ROOT.glob("*/metadata.jsonl"))
    if not files:
        raise RuntimeError("No captured metadata found. Run 01_CAPTURE.bat first.")
    return files


def raw_records(files: list[Path]) -> list[dict[str, Any]]:
    return [row for path in files for row in iter_jsonl(path)]


def analysis_fingerprint(files: list[Path], skip_model: bool) -> str:
    model = MODELS_ROOT / "rps_int8.tflite"
    paths = [*files, CONFIG_ROOT / "preprocessing.json"]
    if model.exists() and not skip_model:
        paths.append(model)
    return stable_hash({
        "schema": 1,
        "inputs": file_fingerprint(paths),
        "skip_model": skip_model,
    })


def tflite_predictions(inputs: list[np.ndarray]) -> tuple[list[dict[str, Any]], str | None]:
    model_path = MODELS_ROOT / "rps_int8.tflite"
    if not model_path.exists():
        return [{} for _ in inputs], "No TFLite model is available"
    try:
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import tensorflow as tf
            interpreter = tf.lite.Interpreter(model_path=str(model_path))
            interpreter.allocate_tensors()
        input_info = interpreter.get_input_details()[0]
        output_info = interpreter.get_output_details()[0]
        scale, zero_point = output_info["quantization"]
        names = class_names()
        results = []
        for tensor in inputs:
            value = tensor[np.newaxis, ...].astype(input_info["dtype"], copy=False)
            interpreter.set_tensor(input_info["index"], value)
            interpreter.invoke()
            raw = interpreter.get_tensor(output_info["index"])[0]
            decoded = ((raw.astype(np.float32) - float(zero_point)) * float(scale))
            selected = int(np.argmax(raw))
            results.append({
                "prediction": names[selected],
                "confidence": float(decoded[selected]),
                "scores": [float(item) for item in decoded],
                "raw_scores": [int(item) for item in raw],
            })
        return results, None
    except Exception as exc:
        return ([{} for _ in inputs],
                f"TFLite inference unavailable: {type(exc).__name__}: {exc}")


def build_analysis(records: list[dict[str, Any]], files: list[Path],
                   skip_model: bool, force: bool) -> dict[str, Any]:
    fingerprint = analysis_fingerprint(files, skip_model)
    if not force and ANALYSIS_PATH.exists():
        cached = load_json(ANALYSIS_PATH)
        if cached.get("input_fingerprint") == fingerprint:
            return cached

    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    model_max_distance = int(cfg.get("model_max_distance_mm", cfg["far_mm"]))
    duplicate_counts = Counter(str(row.get("depth_sha256", "")) for row in records)
    metrics: list[dict[str, Any]] = []
    model_inputs: list[np.ndarray] = []
    print(f"Analyzing {len(records)} captured frames...", flush=True)
    for index, row in enumerate(records, start=1):
        depth = load_depth_record(row)
        valid = ((depth != int(cfg["invalid_mm"])) & (depth > 0) &
                 (depth >= int(cfg["near_mm"])) &
                 (depth <= model_max_distance))
        foreground = nearest_connected_component(depth, valid, cfg)
        model_input = preprocess_depth(depth, cfg)
        model_inputs.append(model_input)
        component_pixels = int(foreground.sum())
        touches_edge = bool(
            component_pixels and
            (foreground[0, :].any() or foreground[-1, :].any() or
             foreground[:, 0].any() or foreground[:, -1].any())
        )
        metrics.append({
            "depth_sha256": row["depth_sha256"],
            "original_label": row["label"],
            "component_pixels": component_pixels,
            "source_foreground_ratio": float(foreground.mean()),
            "model_foreground_ratio": float(np.mean(model_input != 0)),
            "touches_sensor_edge": touches_edge,
            "duplicate_count": duplicate_counts[row["depth_sha256"]],
        })
        if index % 100 == 0:
            print(f"  technical analysis {index}/{len(records)}", flush=True)

    if skip_model:
        predictions = [{} for _ in records]
        model_error = None
    else:
        predictions, model_error = tflite_predictions(model_inputs)

    values_by_label: defaultdict[str, list[float]] = defaultdict(list)
    for item in metrics:
        values_by_label[item["original_label"]].append(
            float(item["source_foreground_ratio"])
        )
    bounds: dict[str, tuple[float, float]] = {}
    for label, values in values_by_label.items():
        q1, q3 = np.percentile(np.asarray(values), [25, 75])
        spread = max(float(q3 - q1), 0.002)
        bounds[label] = (max(0.0, float(q1) - 1.5 * spread),
                         min(1.0, float(q3) + 1.5 * spread))

    items: dict[str, dict[str, Any]] = {}
    for row, metric, prediction in zip(records, metrics, predictions):
        flags: list[str] = []
        priority = 0
        label = str(row["label"])
        if metric["component_pixels"] == 0 and label != "none":
            flags.append("no_foreground")
            priority += 100
        # An edge-touching nearest component is expected in many empty/negative
        # scenes. It is useful as a clipping hint only for actual gestures.
        if metric["touches_sensor_edge"] and label != "none":
            flags.append("touches_sensor_edge")
            priority += 35
        lower, upper = bounds[label]
        ratio = float(metric["source_foreground_ratio"])
        if ratio < lower or ratio > upper:
            flags.append("foreground_outlier")
            priority += 25
        if metric["duplicate_count"] > 1:
            flags.append("exact_duplicate")
            priority += 15
        if prediction:
            if prediction.get("prediction") != label:
                flags.append("model_disagrees")
                priority += 40
            if float(prediction.get("confidence", 1.0)) < 0.55:
                flags.append("low_confidence")
                priority += 20
        digest = str(row["depth_sha256"])
        # Identical hashes deliberately share one review decision and analysis.
        items[digest] = {
            **metric,
            **prediction,
            "flags": flags,
            "priority": priority,
        }

    payload = {
        "schema": 1,
        "created_utc": utc_now(),
        "input_fingerprint": fingerprint,
        "model_sha256": (sha256_file(MODELS_ROOT / "rps_int8.tflite")
                         if (MODELS_ROOT / "rps_int8.tflite").exists() and
                         not skip_model else None),
        "model_error": model_error,
        "records": len(records),
        "items": items,
    }
    atomic_json(ANALYSIS_PATH, payload)
    return payload


class ReviewApp:
    def __init__(self, root: tk.Tk, records: list[dict[str, Any]],
                 analysis: dict[str, Any]):
        self.root = root
        self.records = records
        self.analysis = analysis.get("items", {})
        self.decisions = load_review_decisions()
        self.names = class_names()
        self.undo_stack: list[list[tuple[str, dict[str, Any] | None]]] = []
        self.visible: list[int] = []
        self.current_mixed_bursts: set[str] = set()
        self.position = 0
        self.raw_photo = None
        self.model_photo = None
        self.queue_var = tk.StringVar(value="Recommended first")
        self.label_var = tk.StringVar(value="all")
        self.stats_var = tk.StringVar()
        self.info_var = tk.StringVar()
        self.flags_var = tk.StringVar()
        self.apply_burst_var = tk.BooleanVar(value=False)
        self._build_ui()
        self._rebuild_queue()

    def _build_ui(self) -> None:
        self.root.title("N6 Dataset Review — non-destructive")
        self.root.geometry("1220x820")
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)
        ttk.Label(top, text="N6 DATASET REVIEW",
                  font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.stats_var).pack(side=tk.RIGHT)

        filters = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        filters.pack(fill=tk.X)
        ttk.Label(filters, text="Queue:").pack(side=tk.LEFT)
        queue = ttk.Combobox(
            filters, textvariable=self.queue_var, state="readonly", width=22,
            values=("Recommended first", "Unreviewed", "Flagged only",
                    "Rejected", "All"),
        )
        queue.pack(side=tk.LEFT, padx=6)
        queue.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_queue())
        ttk.Label(filters, text="Label:").pack(side=tk.LEFT, padx=(15, 0))
        label = ttk.Combobox(
            filters, textvariable=self.label_var, state="readonly", width=12,
            values=("all", *self.names),
        )
        label.pack(side=tk.LEFT, padx=6)
        label.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_queue())
        ttk.Label(
            filters,
            text="המודל רק ממליץ מה לבדוק; הוא לעולם אינו פוסל אוטומטית.",
        ).pack(side=tk.RIGHT)

        images = ttk.Frame(self.root, padding=10)
        images.pack(fill=tk.BOTH, expand=True)
        raw_frame = ttk.LabelFrame(images, text="RAW DEPTH — sensor", padding=6)
        raw_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        model_frame = ttk.LabelFrame(images, text="MODEL INPUT — actual learning input",
                                     padding=6)
        model_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.raw_image = ttk.Label(raw_frame, anchor=tk.CENTER)
        self.raw_image.pack(fill=tk.BOTH, expand=True)
        self.model_image = ttk.Label(model_frame, anchor=tk.CENTER)
        self.model_image.pack(fill=tk.BOTH, expand=True)

        details = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        details.pack(fill=tk.X)
        ttk.Label(details, textvariable=self.info_var,
                  font=("Consolas", 11)).pack(anchor=tk.W)
        ttk.Label(details, textvariable=self.flags_var,
                  foreground="#a33", wraplength=1160).pack(anchor=tk.W, pady=4)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="← Previous", command=self.previous).pack(side=tk.LEFT)
        ttk.Button(actions, text="Next →", command=self.next).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="ACCEPT + NEXT (A)", command=self.accept).pack(side=tk.LEFT, padx=(25, 5))
        ttk.Button(actions, text="REJECT + NEXT (X)", command=self.reject).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Clear decision", command=self.clear).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="UNDO (U)", command=self.undo).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            actions, text="Apply action to entire burst",
            variable=self.apply_burst_var,
        ).pack(side=tk.LEFT, padx=(12, 5))
        for name in self.names:
            ttk.Button(actions, text=f"→ {name} + NEXT",
                       command=lambda value=name: self.relabel(value)).pack(
                           side=tk.RIGHT, padx=3
                       )

        ttk.Label(
            self.root,
            text="Keys: ←/→ navigate · A accept · X reject · U undo · N/R/P/S relabel",
            padding=(10, 0, 10, 10),
        ).pack()
        self.root.bind("<Left>", lambda _event: self.previous())
        self.root.bind("<Right>", lambda _event: self.next())
        self.root.bind("a", lambda _event: self.accept())
        self.root.bind("x", lambda _event: self.reject())
        self.root.bind("u", lambda _event: self.undo())
        for name, key in (("none", "n"), ("rock", "r"),
                          ("paper", "p"), ("scissors", "s")):
            self.root.bind(key, lambda _event, value=name: self.relabel(value))

    def _state(self, row: dict[str, Any]) -> tuple[bool, str, bool]:
        decision = self.decisions.get(str(row["depth_sha256"]))
        if decision is None:
            return bool(row.get("accepted", True)), str(row["label"]), False
        return bool(decision["accepted"]), str(decision.get("label") or row["label"]), True

    @staticmethod
    def _burst_key(row: dict[str, Any]) -> str:
        return f"{row.get('session_id', 'unknown')}:{row.get('burst_id', '')}"

    def _mixed_bursts(self) -> set[str]:
        labels: defaultdict[str, set[str]] = defaultdict(set)
        for row in self.records:
            accepted, label, _reviewed = self._state(row)
            if accepted and row.get("burst_id"):
                labels[self._burst_key(row)].add(label)
        return {burst for burst, values in labels.items() if len(values) > 1}

    def _sort_key(self, index: int) -> tuple:
        row = self.records[index]
        digest = str(row["depth_sha256"])
        accepted, _label, reviewed = self._state(row)
        priority = int(self.analysis.get(digest, {}).get("priority", 0))
        return (reviewed, not accepted, -priority,
                str(row.get("captured_utc", "")))

    def _rebuild_queue(self) -> None:
        current_digest = None
        if self.visible and 0 <= self.position < len(self.visible):
            current_digest = self.records[self.visible[self.position]]["depth_sha256"]
        mode = self.queue_var.get()
        selected_label = self.label_var.get()
        mixed_bursts = self._mixed_bursts()
        self.current_mixed_bursts = mixed_bursts
        visible = []
        for index, row in enumerate(self.records):
            digest = str(row["depth_sha256"])
            accepted, label, reviewed = self._state(row)
            priority = int(self.analysis.get(digest, {}).get("priority", 0))
            if selected_label != "all" and label != selected_label:
                continue
            if mode in {"Recommended first", "Unreviewed"} and reviewed:
                continue
            if mode == "Flagged only" and (reviewed or priority <= 0):
                continue
            if mode == "Rejected" and accepted:
                continue
            visible.append(index)
        if mode != "All":
            visible.sort(key=self._sort_key)
        self.visible = visible
        self.position = 0
        if current_digest is not None:
            for position, index in enumerate(self.visible):
                if self.records[index]["depth_sha256"] == current_digest:
                    self.position = position
                    break
        self._show()

    @staticmethod
    def _photo(path: Path, size: tuple[int, int]) -> ImageTk.PhotoImage:
        image = Image.open(path).convert("RGB")
        image = ImageOps.contain(image, size, Image.Resampling.NEAREST)
        canvas = Image.new("RGB", size, "black")
        canvas.paste(image, ((size[0] - image.width) // 2,
                             (size[1] - image.height) // 2))
        return ImageTk.PhotoImage(canvas)

    def _show(self) -> None:
        decisions_count = len(self.decisions)
        rejected_count = sum(
            1 for row in self.records if not self._state(row)[0]
        )
        self.stats_var.set(
            f"Frames {len(self.records)} · reviewed {decisions_count} · "
            f"rejected {rejected_count} · queue {len(self.visible)}"
        )
        if not self.visible:
            self.info_var.set("No frames match the current filters.")
            self.flags_var.set("")
            self.raw_image.configure(image="")
            self.model_image.configure(image="")
            return
        row = self.records[self.visible[self.position]]
        digest = str(row["depth_sha256"])
        analysis = self.analysis.get(digest, {})
        accepted, label, reviewed = self._state(row)
        review_text = "UNREVIEWED" if not reviewed else "ACCEPTED" if accepted else "REJECTED"
        prediction = analysis.get("prediction", "unavailable")
        confidence = analysis.get("confidence")
        confidence_text = (f"{float(confidence):.1%}" if confidence is not None
                           else "unavailable")
        burst_counts: Counter[str] = Counter()
        burst_key = self._burst_key(row)
        for candidate in self.records:
            candidate_accepted, candidate_label, _candidate_reviewed = self._state(candidate)
            if candidate_accepted and self._burst_key(candidate) == burst_key:
                burst_counts[candidate_label] += 1
        burst_summary = ", ".join(
            f"{name}={burst_counts[name]}" for name in self.names
            if burst_counts[name]
        )
        self.info_var.set(
            f"{self.position + 1}/{len(self.visible)}  review={review_text}  "
            f"label={row['label']} → {label}  model={prediction} ({confidence_text})\n"
            f"session={row.get('session_id')}  burst={row.get('burst_id')}  "
            f"foreground={float(analysis.get('source_foreground_ratio', 0.0)):.1%}  "
            f"sha={digest[:12]}\naccepted labels in this burst: {burst_summary or 'none'}"
        )
        flags = list(analysis.get("flags", []))
        self.flags_var.set(
            "מומלץ לבדיקה: " + " · ".join(FLAG_TEXT.get(flag, flag) for flag in flags)
            if flags else "לא נמצאה בעיה אוטומטית; עדיין נדרש שיקול אנושי."
        )
        preview = TRAINING_ROOT / str(row["preview_png"])
        model = TRAINING_ROOT / str(row["model_input_png"])
        self.raw_photo = self._photo(preview, (560, 390))
        self.model_photo = self._photo(model, (560, 390))
        self.raw_image.configure(image=self.raw_photo)
        self.model_image.configure(image=self.model_photo)

    def _save(self) -> None:
        atomic_json(REVIEW_PATH, {
            "schema": 1,
            "updated_utc": utc_now(),
            "decisions": self.decisions,
        })
        rejected = sum(1 for decision in self.decisions.values()
                       if not decision["accepted"])
        relabeled = sum(
            1 for row in self.records
            if ((decision := self.decisions.get(str(row["depth_sha256"]))) and
                decision.get("label") != row.get("label"))
        )
        mark_stage(
            "02_review",
            status="complete",
            inputs=dataset_input_fingerprint(metadata_files()),
            outputs=[relative(REVIEW_PATH)],
            details={
                "reviewed": len(self.decisions),
                "rejected": rejected,
                "relabeled": relabeled,
                "mixed_label_bursts": len(self._mixed_bursts()),
            },
        )

    def _set(self, accepted: bool, label: str | None = None) -> None:
        if not self.visible:
            return
        row = self.records[self.visible[self.position]]
        current_digest = str(row["depth_sha256"])
        if self.apply_burst_var.get() and row.get("burst_id"):
            burst_key = self._burst_key(row)
            targets = [item for item in self.records
                       if self._burst_key(item) == burst_key]
            if accepted and label is not None:
                # Bulk relabel changes only frames that are still accepted;
                # earlier human rejections must not be resurrected silently.
                targets = [item for item in targets if self._state(item)[0]]
        else:
            targets = [row]
        undo_action: list[tuple[str, dict[str, Any] | None]] = []
        for target in targets:
            digest = str(target["depth_sha256"])
            previous = self.decisions.get(digest)
            undo_action.append((digest, dict(previous) if previous else None))
            _accepted, effective_label, _reviewed = self._state(target)
            self.decisions[digest] = {
                "accepted": accepted,
                "label": label or effective_label,
                "updated_utc": utc_now(),
            }
        self.undo_stack.append(undo_action)
        self._save()
        self._rebuild_queue()
        if any(str(self.records[index]["depth_sha256"]) == current_digest
               for index in self.visible):
            self.next()

    def accept(self) -> None:
        self._set(True)

    def reject(self) -> None:
        self._set(False)

    def relabel(self, label: str) -> None:
        self._set(True, label)

    def clear(self) -> None:
        if not self.visible:
            return
        row = self.records[self.visible[self.position]]
        if self.apply_burst_var.get() and row.get("burst_id"):
            burst_key = self._burst_key(row)
            targets = [item for item in self.records
                       if self._burst_key(item) == burst_key]
        else:
            targets = [row]
        undo_action = []
        for target in targets:
            digest = str(target["depth_sha256"])
            previous = self.decisions.get(digest)
            if previous is not None:
                undo_action.append((digest, dict(previous)))
                del self.decisions[digest]
        if not undo_action:
            return
        self.undo_stack.append(undo_action)
        self._save()
        self._rebuild_queue()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        for digest, previous in action:
            if previous is None:
                self.decisions.pop(digest, None)
            else:
                self.decisions[digest] = previous
        self._save()
        self._rebuild_queue()

    def previous(self) -> None:
        if self.visible:
            self.position = (self.position - 1) % len(self.visible)
            self._show()

    def next(self) -> None:
        if self.visible:
            self.position = (self.position + 1) % len(self.visible)
            self._show()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-model", action="store_true",
                        help="Do not use the current TFLite model for prioritization")
    parser.add_argument("--force-analysis", action="store_true",
                        help="Recompute the automatic-priority cache")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Print the automatic analysis summary without opening the UI")
    args = parser.parse_args()
    files = metadata_files()
    records = raw_records(files)
    analysis = build_analysis(records, files, args.skip_model, args.force_analysis)
    flagged = sum(1 for item in analysis["items"].values()
                  if item.get("priority", 0) > 0)
    print(
        f"Automatic review queue: {len(records)} frames, {flagged} flagged; "
        f"human decisions: {len(load_review_decisions())}."
    )
    if analysis.get("model_error"):
        print(f"WARNING: {analysis['model_error']}")
    if args.analyze_only:
        return 0
    root = tk.Tk()
    ReviewApp(root, records, analysis)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
