"""Stage 01: guided, resumable capture of continuous ToF gesture bursts."""

from __future__ import annotations

import argparse
import logging
import math
import queue
import re
import threading
import time
import tkinter as tk
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import numpy as np
from PIL import Image, ImageTk
import json
from sample_sources import create_source
from sample_store import SampleStore, DuplicateSample
from capture_service import collect
from cloud_sample_source import SourceComplete
from common import PROJECT_ID, STATE_ROOT
from common import TRAINING_ROOT, TRAINING_ENTRY_ROOT, PROJECT_MANIFEST, NON_INTERACTIVE

from common import (CONFIG_ROOT, RAW_ROOT, append_jsonl, atomic_json,
                    apply_review, class_config, iter_jsonl, load_json,
                    load_review_decisions, mark_stage, relative, utc_now)
from dataset import preprocess_depth, preview_rgb, save_depth_sample
from protocol import VERSION_V3, VERSION_V4, DepthFrame, FrameReader


class CaptureApp:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root = root
        self.args = args
        self.classes = class_config()
        self.class_names = [item["name"] for item in self.classes]
        self.training_cfg = load_json(CONFIG_ROOT / "training.json")
        self.pre_cfg = load_json(CONFIG_ROOT / "preprocessing.json")
        self.capture_cfg = self.training_cfg["capture"]
        self.session_id = args.session or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_root = RAW_ROOT / self.session_id
        self.metadata_path = self.session_root / "metadata.jsonl"
        self.session_path = self.session_root / "session.json"
        self.log_path = self.session_root / "capture.log"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"n6.capture.{self.session_id}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        log_handler = logging.FileHandler(self.log_path, mode="a", encoding="utf-8")
        log_handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        self.logger.addHandler(log_handler)
        self.counts: Counter[str] = Counter()
        self.bursts_by_class: defaultdict[str, set[str]] = defaultdict(set)
        review_decisions = load_review_decisions()
        for raw_row in iter_jsonl(self.metadata_path):
            row = apply_review(raw_row, review_decisions)
            if row.get("accepted", True):
                label = row.get("label", "unknown")
                self.counts[label] += 1
                if row.get("burst_id"):
                    self.bursts_by_class[label].add(row["burst_id"])
        self.target = args.target_per_class or self.capture_cfg["target_per_class"]
        self.save_period = 1.0 / (args.save_fps or self.capture_cfg["save_fps"])
        self.warmup_seconds = float(self.capture_cfg["warmup_seconds"])
        configured_burst_limit = (args.samples_per_burst or
                                  self.capture_cfg["samples_per_burst"])
        self.minimum_bursts_per_class = self.capture_cfg[
            "minimum_bursts_per_class"
        ]
        # Never let a small class target collapse into fewer groups than the
        # leakage-safe train/validation/test split requires. Examples:
        # target 50 -> 17+17+16; target 100 -> four bursts of at most 25.
        group_safe_limit = math.ceil(
            self.target / self.minimum_bursts_per_class
        )
        self.samples_per_burst = min(configured_burst_limit, group_safe_limit)
        self.duplicate_threshold = self.capture_cfg["near_duplicate_mean_mm"]
        self.current_label = None if args.unlabeled else (args.label or self._first_incomplete_label())
        self.capturing = False
        self.burst_id: str | None = None
        self.latest: DepthFrame | None = None
        self.last_frame_time = 0.0
        self.last_saved_time = 0.0
        self.capture_armed_at = 0.0
        self.last_saved_depth: np.ndarray | None = None
        self.frames_received = 0
        self.frames_rejected_duplicate = 0
        self.reader_timeouts = 0
        self.reader_exceptions = 0
        self.burst_saved_count = 0
        self.burst_target_was_already_met = False
        self.notice_text = ""
        self.model_foreground_ratio = 0.0
        self.stream_faulted = False
        self.last_fault: str | None = None
        self.stop_event = threading.Event()
        self.frame_queue: queue.Queue[DepthFrame] = queue.Queue(maxsize=2)
        self.source = create_source(args.transport, **source_options(args))
        self.store = SampleStore(TRAINING_ROOT, PROJECT_MANIFEST, self.pre_cfg,
                                 self.session_id, contract_roots=[TRAINING_ENTRY_ROOT])
        try:
            self.source.open()
        except Exception:
            self.store.close()
            for handler in list(self.logger.handlers):
                handler.close(); self.logger.removeHandler(handler)
            raise
        if args.transport == "cloud":
            self.capturing = True
            self.warmup_seconds = 0
            self.burst_id = "cloud-" + self.source.capture_session
        self.reader = self.source.stats
        self.latest_sample = None
        self._write_session_state("active")
        self._build_ui()
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()
        self.root.after(30, self._poll)

    def _first_incomplete_label(self) -> str:
        for name in self.capture_cfg["guided_order"]:
            if self.counts[name] < self.target:
                return name
        return self.capture_cfg["guided_order"][0]

    def _build_ui(self) -> None:
        self.root.title("N6 ToF dataset capture — Rock / Paper / Scissors")
        self.root.geometry("980x650")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        previews = tk.Frame(self.root)
        previews.pack(padx=12, pady=12)
        raw_column = tk.Frame(previews)
        raw_column.pack(side=tk.LEFT, padx=8)
        model_column = tk.Frame(previews)
        model_column.pack(side=tk.LEFT, padx=8)
        tk.Label(raw_column, text="RAW DEPTH (what the sensor sees)",
                 font=("Segoe UI", 10, "bold")).pack()
        tk.Label(model_column, text="HOST PROJECT PREVIEW (received tensor saved separately)",
                 font=("Segoe UI", 10, "bold")).pack()
        self.image_label = tk.Label(raw_column, bg="black")
        self.image_label.pack()
        self.model_image_label = tk.Label(model_column, bg="black")
        self.model_image_label.pack()
        self.title_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Connecting to N6DF stream...")
        tk.Label(self.root, textvariable=self.title_var,
                 font=("Segoe UI", 22, "bold")).pack()
        tk.Label(self.root, textvariable=self.status_var,
                 font=("Consolas", 11), justify="left").pack(pady=8)
        tk.Label(
            self.root,
            text=("SPACE: start/stop a burst   ESC: safe exit\n"
                  "Select a class below or collect unlabeled samples for later review."),
            font=("Segoe UI", 11), justify="center"
        ).pack(pady=8)
        self.root.bind("<space>", lambda _event: self.toggle_capture())
        self.root.bind("<Escape>", lambda _event: self.close())
        labels = tk.Frame(self.root); labels.pack()
        tk.Button(labels, text="Unlabeled", command=lambda: self.set_label(None)).pack(side=tk.LEFT)
        for item in self.classes:
            tk.Button(labels, text=item.get("display_name", item["name"]),
                      command=lambda label=item["name"]: self.set_label(label)).pack(side=tk.LEFT)
            if item.get("key"):
                self.root.bind(item["key"], lambda _event, label=item["name"]: self.set_label(label))
        self._refresh_text()

    def _reader_loop(self) -> None:
        while not self.stop_event.is_set():
            crc_before = self.reader.crc_errors
            framing_before = self.reader.framing_errors
            try:
                sample = self.source.read(timeout=1.0)
                frame = sample.frame
                crc_delta = self.reader.crc_errors - crc_before
                framing_delta = self.reader.framing_errors - framing_before
                if crc_delta or framing_delta:
                    self.logger.warning(
                        "stream_resynchronized frame=%d crc_delta=%d "
                        "framing_delta=%d discarded_total=%d last_error=%r",
                        frame.frame_id, crc_delta, framing_delta,
                        self.reader.discarded_bytes, self.reader.last_error,
                    )
                while True:
                    try:
                        self.frame_queue.put_nowait(sample)
                        break
                    except queue.Full:
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
            except SourceComplete:
                self.root.after(0, lambda: setattr(self, 'notice_text', 'Cloud capture ended; all available records downloaded. Review stored/missing counts.'))
                break
            except TimeoutError as exc:
                if self.stop_event.is_set():
                    break
                self.reader_timeouts += 1
                self.logger.warning(
                    "reader_timeout count=%d buffered=%d crc_total=%d "
                    "framing_total=%d last_error=%r detail=%s",
                    self.reader_timeouts, self.reader.buffered_bytes,
                    self.reader.crc_errors, self.reader.framing_errors,
                    self.reader.last_error, exc,
                )
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                self.reader_exceptions += 1
                self.logger.exception("reader_exception: %s", exc)
                if not self.stop_event.is_set():
                    self.root.after(0, lambda value=str(exc):
                                    self.status_var.set(f"ERROR: reader: {value}"))
                time.sleep(0.2)

    def _set_stream_fault(self, message: str) -> None:
        if self.stream_faulted:
            return
        self.stream_faulted = True
        self.last_fault = message
        self.capturing = False
        self.burst_id = None
        self.logger.error(
            "stream_fault message=%r last_frame=%s crc=%d framing=%d "
            "timeouts=%d exceptions=%d discarded=%d last_parser_error=%r",
            message, self.latest.frame_id if self.latest else None,
            self.reader.crc_errors, self.reader.framing_errors,
            self.reader_timeouts, self.reader_exceptions,
            self.reader.discarded_bytes, self.reader.last_error,
        )
        self.status_var.set(f"ERROR: {message}\nLog: {self.log_path}")

    def _poll(self) -> None:
        newest = None
        while True:
            try:
                newest = self.frame_queue.get_nowait()
            except queue.Empty:
                break
        if newest is not None:
            self.latest_sample = newest
            newest = newest.frame
        if newest is not None:
            model_tensor = self._verified_model_input(newest)
            if model_tensor is None:
                newest = None
        if newest is not None:
            self.latest = newest
            self.last_frame_time = time.monotonic()
            self.frames_received += 1
            self._show_frame(newest, model_tensor)
            self._maybe_save(newest, model_tensor)
        if newest is None and self.args.transport == 'cloud' and getattr(self.source,'pending',None) is self.latest_sample and self.latest_sample is not None and self.capturing:
            self._maybe_save(self.latest_sample.frame, preprocess_depth(self.latest_sample.frame.depth_mm, self.pre_cfg)[...,0])
        stale = time.monotonic() - self.last_frame_time
        if self.args.transport != "cloud" and self.last_frame_time and stale > self.capture_cfg["stale_frame_seconds"]:
            self._set_stream_fault(
                f"no valid N6DF frame for {stale:.1f}s; capture paused automatically"
            )
        self._refresh_text()
        if not self.stop_event.is_set():
            self.root.after(30, self._poll)

    def _verified_model_input(self, frame: DepthFrame) -> np.ndarray | None:
        # This preview is explicitly the selected project's host transform.
        # SampleStore independently checks any known source contract and saves
        # only the exact source tensor as received, including explicit absence.
        return preprocess_depth(frame.depth_mm, self.pre_cfg)[..., 0]

    def _show_frame(self, frame: DepthFrame,
                    model_tensor: np.ndarray) -> None:
        rgb = preview_rgb(frame.depth_mm, self.pre_cfg["near_mm"],
                          self.pre_cfg["far_mm"], frame.invalid_mm)
        image = Image.fromarray(rgb).resize((432, 336),
                                            Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=photo)
        self.image_label.image = photo
        self.model_foreground_ratio = float(np.mean(model_tensor != 0))
        model_rgb = np.repeat(model_tensor[..., np.newaxis], 3, axis=2)
        model_image = Image.fromarray(model_rgb).resize(
            (384, 300), Image.Resampling.NEAREST
        )
        model_photo = ImageTk.PhotoImage(model_image)
        self.model_image_label.configure(image=model_photo)
        self.model_image_label.image = model_photo

    def _maybe_save(self, frame: DepthFrame,
                    model_tensor: np.ndarray) -> None:
        now = time.monotonic()
        if (not self.capturing or now < self.capture_armed_at or
                now - self.last_saved_time < self.save_period):
            return
        if self.last_saved_depth is not None and not self.args.disable_content_filter and not getattr(self.source,"lossless_replay",False):
            both_valid = ((frame.depth_mm != frame.invalid_mm) &
                          (self.last_saved_depth != frame.invalid_mm))
            if both_valid.any():
                mean_delta = float(np.mean(np.abs(
                    frame.depth_mm[both_valid].astype(np.int32) -
                    self.last_saved_depth[both_valid].astype(np.int32))))
                if mean_delta < self.duplicate_threshold:
                    self.frames_rejected_duplicate += 1
                    return
        try:
            self.store.commit(self.latest_sample, label=self.current_label, group=("cloud-"+self.source.capture_session if self.args.transport=="cloud" else self.burst_id))
            if hasattr(self.source,"acknowledge"): self.source.acknowledge(self.latest_sample)
        except DuplicateSample:
            if hasattr(self.source,"acknowledge") and getattr(self.source,"pending",None) is self.latest_sample:
                self.source.acknowledge(self.latest_sample)
            return
        except Exception as exc:
            self._set_stream_fault(str(exc))
            return
        self.counts[self.current_label] += 1
        if self.burst_id:
            self.bursts_by_class[self.current_label].add(self.burst_id)
        self.burst_saved_count += 1
        self.last_saved_depth = frame.depth_mm.copy()
        self.last_saved_time = now
        self._write_session_state("active")
        target_reached = self.counts[self.current_label] >= self.target
        burst_reached = self.burst_saved_count >= self.samples_per_burst
        if ((target_reached and not self.burst_target_was_already_met) or
                burst_reached):
            self.capturing = False
            completed = self.current_label
            self.burst_id = None
            if target_reached and self.current_label is not None:
                self.current_label = self._first_incomplete_label()
                self.notice_text = (
                    f"{completed}: target reached ({self.counts[completed]}). "
                    f"Next: {self.current_label}; press SPACE for a new burst."
                )
            else:
                self.notice_text = (
                    f"Burst complete: {self.burst_saved_count} saved for {completed}. "
                    "Change pose/distance, then press SPACE for another burst."
                )
            self.logger.info(
                "burst_complete label=%s saved_in_burst=%d class_count=%d "
                "target_reached=%s next_label=%s",
                completed, self.burst_saved_count, self.counts[completed],
                target_reached, self.current_label,
            )
            self.root.bell()

    def toggle_capture(self) -> None:
        if self.stream_faulted:
            messagebox.showwarning(
                "Stream fault",
                "Capture is locked after a stream integrity/stall error. "
                "Close and reopen this stage; the existing session will not be erased."
            )
            return
        if self.latest is None:
            messagebox.showwarning("No frame", "No valid N6DF frame received yet.")
            return
        self.capturing = not self.capturing
        if self.capturing:
            self.burst_id = uuid.uuid4().hex[:12]
            self.burst_saved_count = 0
            self.burst_target_was_already_met = (
                self.counts[self.current_label] >= self.target
            )
            self.last_saved_depth = None
            self.last_saved_time = 0.0
            self.capture_armed_at = time.monotonic() + self.warmup_seconds
            self.notice_text = (
                f"Hold the {self.current_label} pose steady; capture starts "
                f"in {self.warmup_seconds:.1f}s."
            )
            self.logger.info(
                "burst_start label=%s burst=%s class_count=%d target=%d "
                "warmup_seconds=%.1f",
                self.current_label, self.burst_id,
                self.counts[self.current_label], self.target,
                self.warmup_seconds,
            )
        else:
            self.logger.info(
                "burst_stopped_by_user label=%s burst=%s saved=%d",
                self.current_label, self.burst_id, self.burst_saved_count,
            )
            self.burst_id = None
        self._refresh_text()

    def set_label(self, label: str) -> None:
        if self.capturing:
            self.logger.info(
                "burst_stopped_by_label_change old_label=%s burst=%s saved=%d",
                self.current_label, self.burst_id, self.burst_saved_count,
            )
        self.capturing = False
        self.burst_id = None
        self.current_label = label
        self.last_saved_depth = None
        self.notice_text = f"Selected {label}; press SPACE to start a burst."
        self.logger.info("label_selected label=%s class_count=%d",
                         label, self.counts[label])
        self._refresh_text()

    def _refresh_text(self) -> None:
        remaining_warmup = self.capture_armed_at - time.monotonic()
        if self.capturing and remaining_warmup > 0.0:
            state = f"HOLD POSE — STARTS IN {remaining_warmup:.1f}s"
        elif self.capturing:
            state = "RECORDING — MOVE THE OBJECT"
        else:
            state = "ready"
        self.title_var.set(f"{(self.current_label or 'UNLABELED').upper()}  [{state}]")
        frame = self.latest.frame_id if self.latest else "waiting"
        count_text = "  ".join(
            f"{name}:{self.counts[name]}/{self.target} "
            f"({len(self.bursts_by_class[name])} bursts)"
            for name in self.class_names
        )
        if not self.stream_faulted:
            self.status_var.set(
                f"port={getattr(self.source, 'port', self.args.transport)}  session={self.session_id}  frame={frame}\n"
                f"{count_text}\nreceived={self.frames_received}  "
                f"near-duplicates skipped={self.frames_rejected_duplicate}  "
                f"model foreground={self.model_foreground_ratio:.1%}\n"
                "Preview: HOST project transform; received tensor saved separately\n"
                f"parser CRC/framing/timeouts={self.reader.crc_errors}/"
                f"{self.reader.framing_errors}/{self.reader_timeouts}\n"
                f"{self.notice_text}"
            )

    def _write_session_state(self, status: str) -> None:
        atomic_json(self.session_path, {
            "schema": 1,
            "session_id": self.session_id,
            "status": status,
            "updated_utc": utc_now(),
            "port": getattr(getattr(self, "source", None), "port", None),
            "target_per_class": self.target,
            "samples_per_burst": self.samples_per_burst,
            "minimum_bursts_per_class": self.minimum_bursts_per_class,
            "warmup_seconds": self.warmup_seconds,
            "counts": dict(self.counts),
            "bursts_by_class": {
                name: len(self.bursts_by_class[name])
                for name in self.class_names
            },
            "capture_log": relative(self.log_path),
            "diagnostics": {
                "crc_errors": getattr(getattr(self, "reader", None),
                                      "crc_errors", 0),
                "framing_errors": getattr(getattr(self, "reader", None),
                                          "framing_errors", 0),
                "reader_timeouts": self.reader_timeouts,
                "reader_exceptions": self.reader_exceptions,
                "last_fault": self.last_fault,
            },
            "instructions": "Each SPACE-delimited burst is kept in one data split.",
        })

    def close(self) -> None:
        if self.stop_event.is_set():
            return
        self.capturing = False
        self.stop_event.set()
        self.logger.info("capture_close requested")
        try:
            if hasattr(self, "thread"):
                self.thread.join(timeout=1.5)
                if self.thread.is_alive():
                    self._set_stream_fault("Source reader did not stop within its bounded read timeout.")
            self.source.stop()
            if self.source.status().get("restore_error"):
                self._set_stream_fault(self.source.status()["restore_error"])
            self.store.close()
        finally:
            final_status = ("closed_with_stream_fault" if self.stream_faulted
                            else "closed")
            self._write_session_state(final_status)
            self.logger.info(
                "capture_closed status=%s counts=%s received=%d crc=%d "
                "framing=%d timeouts=%d exceptions=%d duplicate_skips=%d",
                final_status, dict(self.counts), self.frames_received,
                self.reader.crc_errors, self.reader.framing_errors,
                self.reader_timeouts, self.reader_exceptions,
                self.frames_rejected_duplicate,
            )
            mark_stage("01_capture",
                       status=("complete_with_stream_fault"
                               if self.stream_faulted else "complete"),
                       outputs=[relative(self.session_root)],
                       details={"session": self.session_id,
                                "counts": dict(self.counts),
                                "log": relative(self.log_path),
                                "last_fault": self.last_fault})
            for handler in list(self.logger.handlers):
                handler.close()
                self.logger.removeHandler(handler)
            self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--transport", choices=["usb", "ble", "cloud"], default="usb")
    parser.add_argument("--expected-device")
    parser.add_argument("--device", help="BLE address selected from discovery")
    parser.add_argument("--endpoint")
    parser.add_argument("--workspace-file", type=Path)
    parser.add_argument("--cloud-device-id")
    parser.add_argument("--cloud-session", help="Resume a durable server capture")
    parser.add_argument("--cloud-duration", type=int, default=90)
    parser.add_argument("--cloud-rate", type=int, default=2)
    parser.add_argument("--cloud-count", type=int, default=20)
    parser.add_argument("--require-no-browser", action="store_true")
    parser.add_argument("--unlabeled", action="store_true")
    parser.add_argument("--samples", type=int, help="Bounded unattended capture count")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--group-size", type=int, default=1)
    parser.add_argument("--disable-content-filter", action="store_true", help="Disable only the scene-similarity filter; source integrity and identity remain mandatory")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--session", help="Resume or name a capture session")
    parser.add_argument("--label", choices=[item["name"] for item in class_config()])
    parser.add_argument("--target-per-class", type=int)
    parser.add_argument("--samples-per-burst", type=int)
    parser.add_argument("--save-fps", type=float)
    args = parser.parse_args()
    if (args.session is not None and
            (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.session)
             or args.session in {".", ".."})):
        parser.error(
            "--session must be 1-64 letters, digits, dot, underscore or hyphen; "
            "path separators are not allowed"
        )
    if args.target_per_class is not None and args.target_per_class <= 0:
        parser.error("--target-per-class must be positive")
    if args.samples_per_burst is not None and args.samples_per_burst <= 0:
        parser.error("--samples-per-burst must be positive")
    if args.save_fps is not None and args.save_fps <= 0:
        parser.error("--save-fps must be positive")
    if args.samples is not None:
        cfg = load_json(CONFIG_ROOT / "preprocessing.json")
        capture_cfg = load_json(CONFIG_ROOT / "training.json")["capture"]
        store = SampleStore(TRAINING_ROOT, PROJECT_MANIFEST, cfg,
                            args.session or datetime.now().strftime("%Y%m%d_%H%M%S"),
                            contract_roots=[TRAINING_ENTRY_ROOT])
        try:
            source = create_source(args.transport, **source_options(args))
            report = collect(source, store, samples=args.samples, timeout=args.timeout,
                             label=None if args.unlabeled else args.label,
                             group_size=args.group_size, save_fps=args.save_fps,
                             near_duplicate_mm=None if args.disable_content_filter else capture_cfg["near_duplicate_mean_mm"])
            report["session"] = store.session
            report["project_id"] = PROJECT_MANIFEST["project_id"] if PROJECT_MANIFEST else "legacy-rps"
            if args.report:
                atomic_json(args.report, report)
            print(json.dumps(report, ensure_ascii=True, indent=2))
            return 0 if report["status"] == "PASS" else 1
        finally:
            store.close()
    if NON_INTERACTIVE:
        raise RuntimeError("BLOCKED: unattended capture requires --samples and a bounded --timeout.")
    root = tk.Tk()
    launch_capture(root, args)
    root.mainloop()
    return 0


def source_options(args):
    return dict(port=args.port, expected_device=args.expected_device, address=args.device,
                endpoint=args.endpoint, workspace_path=args.workspace_file, device_id=args.cloud_device_id,
                capture_session=args.cloud_session, project_id=PROJECT_ID, state_root=STATE_ROOT,
                capture_duration=args.cloud_duration, capture_rate=args.cloud_rate,
                capture_count=args.samples if args.samples is not None else args.cloud_count,
                require_no_browser=args.require_no_browser)


def launch_capture(root, args):
    from tkinter import ttk, filedialog
    defaults = dict(endpoint=None, workspace_file=None, cloud_device_id=None, cloud_session=None,
                    cloud_duration=90, cloud_rate=2, cloud_count=20, require_no_browser=False, samples=None)
    for key, value in defaults.items():
        if not hasattr(args,key): setattr(args,key,value)
    root.title("N6 project capture")
    panel = ttk.Frame(root, padding=16); panel.pack()
    source = tk.StringVar(value=args.transport)
    session = tk.StringVar(value=args.session or datetime.now().strftime("%Y%m%d_%H%M%S"))
    device = tk.StringVar(value=args.device or "")
    setup_path = STATE_ROOT / 'capture_setup.json'
    setup = load_json(setup_path) if setup_path.exists() else {}
    endpoint = tk.StringVar(value=args.endpoint or setup.get('endpoint',''))
    workspace = tk.StringVar(value=str(args.workspace_file or setup.get('workspace_file','')))
    cloud_device = tk.StringVar(value=args.cloud_device_id or setup.get('cloud_device_id',''))
    last_verified_device = ''
    if not args.expected_device and not setup.get('canonical_device'):
        for path in sorted(RAW_ROOT.glob('*/metadata.jsonl'), key=lambda p:p.stat().st_mtime, reverse=True):
            for row in reversed(list(iter_jsonl(path))):
                candidate = row.get('device',{}).get('id','')
                if re.fullmatch(r'n6:[0-9a-f]{2}(:[0-9a-f]{2}){5}',candidate):
                    last_verified_device = candidate;break
            if last_verified_device:break
    canonical = tk.StringVar(value=args.expected_device or setup.get('canonical_device',last_verified_device))
    cloud_session = tk.StringVar(value=args.cloud_session or '')
    cloud_count = tk.StringVar(value=str(args.cloud_count))
    cloud_duration = tk.StringVar(value=str(args.cloud_duration))
    cloud_rate = tk.StringVar(value=str(args.cloud_rate))
    unlabeled = tk.BooleanVar(value=args.unlabeled or args.label is None)
    message = tk.StringVar(value="Select a source and session. Existing records are preserved.")
    ttk.Label(panel, text=f"Project: {PROJECT_MANIFEST.get('display_name', PROJECT_MANIFEST.get('name', 'Selected')) if PROJECT_MANIFEST else 'RPS'}").pack(anchor="w")
    ttk.Label(panel, text="Source").pack(anchor="w")
    ttk.Combobox(panel, textvariable=source, values=["usb", "ble", "cloud"], state="readonly").pack(fill="x")
    ble_panel = ttk.Frame(panel)
    ble_panel.pack(fill='x')
    ttk.Label(ble_panel, text="BLE device address (Discover selects an advertised N6)").pack(anchor="w")
    devices = ttk.Combobox(ble_panel, textvariable=device); devices.pack(fill="x")
    def discover():
        from ble_sample_source import discover_ble
        message.set("Discovering N6 BLE devices...")
        def worker():
            try:
                found = discover_ble()
                def update():
                    devices.configure(values=[d['address'] for d in found])
                    if len(found) == 1: device.set(found[0]['address'])
                    message.set("; ".join(d['name']+" "+d['address'] for d in found) or "No N6 devices advertised. No Pair operation performed.")
                root.after(0, update)
            except Exception as exc:
                root.after(0, lambda value=str(exc): message.set(value))
        threading.Thread(target=worker, daemon=True).start()
    ttk.Button(ble_panel, text="Discover BLE", command=discover).pack(anchor="w")
    cloud_panel = ttk.LabelFrame(panel, text="Cloud: existing endpoint and authorization", padding=8)
    cloud_panel.pack(fill='x',pady=8)
    for title,variable in [('HTTPS endpoint',endpoint),('Existing workspace file',workspace),
                           ('Workspace device ID',cloud_device),('Verified device identity (n6:MAC)',canonical),
                           ('Server session (empty creates a bounded capture)',cloud_session),
                           ('Maximum samples',cloud_count),('Duration seconds',cloud_duration),('Rate Hz (1-4)',cloud_rate)]:
        ttk.Label(cloud_panel,text=title).pack(anchor='w')
        ttk.Entry(cloud_panel,textvariable=variable).pack(fill='x')
    def choose_workspace():
        path=filedialog.askopenfilename(filetypes=[('N6 workspace','*.n6workspace.json')])
        if not path:return
        try:
            value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if value.get('format')!='n6-workspace-v1':raise ValueError('Invalid existing workspace file.')
            workspace.set(path)
            if len(value.get('devices',[]))==1:cloud_device.set(value['devices'][0]['id'])
            message.set('Existing authorization selected. Tokens are never copied to project records.')
        except Exception as exc:message.set(str(exc))
    ttk.Button(cloud_panel,text='Choose existing workspace',command=choose_workspace).pack(anchor='w')
    ttk.Label(cloud_panel,text='Closing TRAINING preserves the bounded server capture. Resume by server session; review labels locally.',wraplength=500).pack()
    def source_changed(*_):
        if source.get()=='ble':ble_panel.pack(fill='x',before=cloud_panel if cloud_panel.winfo_manager() else session_label)
        else:ble_panel.pack_forget()
        if source.get()=='cloud':cloud_panel.pack(fill='x',pady=8,before=session_label)
        else:cloud_panel.pack_forget()
    session_label = ttk.Label(panel, text="Session (new or resume)")
    session_label.pack(anchor='w')
    source.trace_add('write',source_changed)
    source_changed()
    ttk.Label(panel, text="").pack(anchor="w")
    ttk.Entry(panel, textvariable=session).pack(fill="x")
    ttk.Checkbutton(panel, text="Collect without labels; review later", variable=unlabeled).pack(anchor="w")
    ttk.Label(panel, textvariable=message, wraplength=500).pack(pady=8)
    def start():
        args.transport, args.session, args.unlabeled = source.get(), session.get(), unlabeled.get()
        args.device = device.get() or None
        args.endpoint, args.workspace_file = endpoint.get(), Path(workspace.get()) if workspace.get() else None
        args.cloud_device_id, args.cloud_session = cloud_device.get() or None, cloud_session.get() or None
        args.expected_device = canonical.get() or args.expected_device
        try:
            args.cloud_count,args.cloud_duration,args.cloud_rate=int(cloud_count.get()),int(cloud_duration.get()),int(cloud_rate.get())
        except ValueError:
            message.set('Capture count, duration and rate must be integers.');return
        if args.transport=='cloud':
            atomic_json(setup_path,{'endpoint':args.endpoint,'workspace_file':str(args.workspace_file or ''),
                                   'cloud_device_id':args.cloud_device_id,'canonical_device':args.expected_device})
        try:
            app = CaptureApp(root, args)
        except Exception as exc:
            message.set(str(exc))
            return
        panel.destroy()
        root.capture_app = app
    ttk.Button(panel, text="Start capture", command=start).pack()


if __name__ == "__main__":
    raise SystemExit(main())
