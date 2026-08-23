"""Stage 01: guided, resumable capture of continuous ToF gesture bursts."""

from __future__ import annotations

import argparse
import logging
import math
import queue
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
from serial import Serial
from serial.tools import list_ports

from common import (CONFIG_ROOT, RAW_ROOT, append_jsonl, atomic_json,
                    class_config, iter_jsonl, load_json, mark_stage, relative,
                    utc_now)
from dataset import preview_rgb, save_depth_sample
from protocol import DepthFrame, FrameReader


def find_n6_port(requested: str | None) -> str:
    if requested:
        return requested.upper()
    candidates = [port.device for port in list_ports.comports()
                  if port.vid == 0x0483 and port.pid == 0x5740]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one CN8 USB CDC device (VID 0483, PID 5740); "
            f"found {candidates or 'none'}. Pass --port COMx when needed."
        )
    return candidates[0]


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
        for row in iter_jsonl(self.metadata_path):
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
        self.current_label = args.label or self._first_incomplete_label()
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
        self.stream_faulted = False
        self.last_fault: str | None = None
        self.stop_event = threading.Event()
        self.frame_queue: queue.Queue[DepthFrame] = queue.Queue(maxsize=2)
        selected_port = find_n6_port(args.port)
        self.logger.info(
            "capture_start session=%s port=%s target_per_class=%d "
            "samples_per_burst=%d save_fps=%.3f existing_counts=%s",
            self.session_id, selected_port, self.target,
            self.samples_per_burst, 1.0 / self.save_period, dict(self.counts),
        )
        self.serial = Serial(selected_port, 115200, timeout=0.2,
                             write_timeout=2)
        self.serial.dtr = True
        self.reader = FrameReader(self.serial)
        self._write_session_state("active")
        self._build_ui()
        self._start_stream()
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
        self.root.geometry("850x650")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.image_label = tk.Label(self.root, bg="black")
        self.image_label.pack(padx=12, pady=12)
        self.title_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Connecting to N6DF stream...")
        tk.Label(self.root, textvariable=self.title_var,
                 font=("Segoe UI", 22, "bold")).pack()
        tk.Label(self.root, textvariable=self.status_var,
                 font=("Consolas", 11), justify="left").pack(pady=8)
        tk.Label(
            self.root,
            text=("SPACE: start/stop a burst while moving the hand in position and depth\n"
                  "R/P/S/N: select rock/paper/scissors/none   ESC: safe exit\n"
                  "A burst is a split group: capture several separate bursts per class."),
            font=("Segoe UI", 11), justify="center"
        ).pack(pady=8)
        self.root.bind("<space>", lambda _event: self.toggle_capture())
        self.root.bind("<Escape>", lambda _event: self.close())
        for item in self.classes:
            self.root.bind(item["key"],
                           lambda _event, label=item["name"]: self.set_label(label))
            self.root.bind(item["key"].upper(),
                           lambda _event, label=item["name"]: self.set_label(label))
        self._refresh_text()

    def _start_stream(self) -> None:
        self.logger.info("stream_start_sequence begin")
        time.sleep(0.35)
        self.serial.reset_input_buffer()
        # Stop first and drain any partial record left by an interrupted PC run.
        # CR is harmless if the menu is already active and restores it after MAP ON.
        self.serial.write(b"\rDATASET STREAM OFF\rMAP OFF\r")
        self.serial.flush()
        time.sleep(0.3)
        self.serial.reset_input_buffer()
        self.serial.write(b"DATASET STREAM ON\r")
        self.serial.flush()
        self.logger.info("stream_start_sequence complete")

    def _reader_loop(self) -> None:
        while not self.stop_event.is_set():
            crc_before = self.reader.crc_errors
            framing_before = self.reader.framing_errors
            try:
                frame = self.reader.read_frame(timeout=1.0)
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
                        self.frame_queue.put_nowait(frame)
                        break
                    except queue.Full:
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
            except TimeoutError as exc:
                if self.stop_event.is_set():
                    break
                self.reader_timeouts += 1
                self.logger.warning(
                    "reader_timeout count=%d buffered=%d crc_total=%d "
                    "framing_total=%d last_error=%r detail=%s",
                    self.reader_timeouts, len(self.reader.buffer),
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
            if self.latest is not None:
                delta = (newest.frame_id - self.latest.frame_id) & 0xFFFFFFFF
                if delta == 0 or delta > 1000:
                    self._set_stream_fault(
                        "firmware frame sequence repeated/reversed: "
                        f"{self.latest.frame_id} -> {newest.frame_id}; "
                        "capture stopped before saving this frame"
                    )
                    newest = None
        if newest is not None:
            self.latest = newest
            self.last_frame_time = time.monotonic()
            self.frames_received += 1
            self._show_frame(newest)
            self._maybe_save(newest)
        stale = time.monotonic() - self.last_frame_time
        if self.last_frame_time and stale > self.capture_cfg["stale_frame_seconds"]:
            self._set_stream_fault(
                f"no valid N6DF frame for {stale:.1f}s; capture paused automatically"
            )
        self._refresh_text()
        if not self.stop_event.is_set():
            self.root.after(30, self._poll)

    def _show_frame(self, frame: DepthFrame) -> None:
        rgb = preview_rgb(frame.depth_mm, self.pre_cfg["near_mm"],
                          self.pre_cfg["far_mm"], frame.invalid_mm)
        image = Image.fromarray(rgb).resize((648, 504),
                                            Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=photo)
        self.image_label.image = photo

    def _maybe_save(self, frame: DepthFrame) -> None:
        now = time.monotonic()
        if (not self.capturing or now < self.capture_armed_at or
                now - self.last_saved_time < self.save_period):
            return
        if self.last_saved_depth is not None:
            both_valid = ((frame.depth_mm != frame.invalid_mm) &
                          (self.last_saved_depth != frame.invalid_mm))
            if both_valid.any():
                mean_delta = float(np.mean(np.abs(
                    frame.depth_mm[both_valid].astype(np.int32) -
                    self.last_saved_depth[both_valid].astype(np.int32))))
                if mean_delta < self.duplicate_threshold:
                    self.frames_rejected_duplicate += 1
                    return
        # A firmware reset restarts both counters. The suffix makes resuming an
        # existing session append-only even if the same counters recur.
        stem = (f"f{frame.frame_id:010d}_t{frame.timestamp_ms:010d}_"
                f"{uuid.uuid4().hex[:8]}")
        record = save_depth_sample(self.session_root, self.current_label, stem,
                                   frame.depth_mm, {
            "schema": 1,
            "session_id": self.session_id,
            "burst_id": self.burst_id,
            "source": "n6df_v1_cdc",
            "captured_utc": utc_now(),
            "firmware_frame_id": frame.frame_id,
            "firmware_timestamp_ms": frame.timestamp_ms,
            "payload_crc32": f"{frame.payload_crc32:08x}",
            "valid_count": frame.valid_count,
            "minimum_mm": frame.minimum_mm,
            "maximum_mm": frame.maximum_mm,
            "processing_filter": frame.processing_filter,
            "protocol_flags": frame.flags,
        })
        append_jsonl(self.metadata_path, record)
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
            if target_reached:
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
        self.title_var.set(f"{self.current_label.upper()}  [{state}]")
        frame = self.latest.frame_id if self.latest else "waiting"
        count_text = "  ".join(
            f"{name}:{self.counts[name]}/{self.target} "
            f"({len(self.bursts_by_class[name])} bursts)"
            for name in self.class_names
        )
        if not self.stream_faulted:
            self.status_var.set(
                f"port={self.serial.port}  session={self.session_id}  frame={frame}\n"
                f"{count_text}\nreceived={self.frames_received}  "
                f"near-duplicates skipped={self.frames_rejected_duplicate}  "
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
            "port": getattr(getattr(self, "serial", None), "port", None),
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
            self.serial.write(b"DATASET STREAM OFF\r")
            self.serial.flush()
            time.sleep(0.3)
        except Exception as exc:
            self.logger.warning("stream_stop_failed: %s", exc)
        try:
            if hasattr(self, "thread"):
                self.thread.join(timeout=1.5)
            self.serial.close()
            if hasattr(self, "thread") and self.thread.is_alive():
                self.thread.join(timeout=0.5)
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
    parser.add_argument("--session", help="Resume or name a capture session")
    parser.add_argument("--label", choices=[item["name"] for item in class_config()])
    parser.add_argument("--target-per-class", type=int)
    parser.add_argument("--samples-per-burst", type=int)
    parser.add_argument("--save-fps", type=float)
    args = parser.parse_args()
    if args.target_per_class is not None and args.target_per_class <= 0:
        parser.error("--target-per-class must be positive")
    if args.samples_per_burst is not None and args.samples_per_burst <= 0:
        parser.error("--samples-per-burst must be positive")
    if args.save_fps is not None and args.save_fps <= 0:
        parser.error("--save-fps must be positive")
    root = tk.Tk()
    CaptureApp(root, args)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
