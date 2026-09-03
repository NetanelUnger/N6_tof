"""Full-rate atomic viewer for complete CRC-validated N6DF v3 frames."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import tkinter as tk
from collections import deque

import numpy as np
from PIL import Image, ImageTk
from serial import Serial
from serial.tools import list_ports

from common import CONFIG_ROOT, load_json
from dataset import preprocess_depth, preview_rgb
from protocol import VERSION_V3, DepthFrame, FrameReader


def choose_n6_port(requested: str | None) -> str:
    if requested:
        selected = requested.upper()
        print(f"Using explicitly requested port: {selected}", flush=True)
        return selected

    ports = sorted(list_ports.comports(), key=lambda item: item.device)
    if not ports:
        raise RuntimeError("No serial COM ports were found")
    recommended = [port for port in ports
                   if port.vid == 0x0483 and port.pid == 0x5740]
    ordered = recommended + [port for port in ports if port not in recommended]
    print("Available serial ports:", flush=True)
    for index, port in enumerate(ordered, start=1):
        marker = "  [CN8 - recommended]" if port in recommended else ""
        description = port.description or "Unknown serial device"
        print(f"  {index}. {port.device:<6} {description}{marker}", flush=True)
    default_index = 1
    while True:
        try:
            answer = input(f"Select COM port [default {default_index}]: ").strip()
        except EOFError:
            if len(recommended) == 1:
                answer = str(default_index)
            else:
                raise RuntimeError(
                    "Interactive COM selection is unavailable; pass --port COMx"
                ) from None
        if not answer:
            selected_index = default_index
        elif answer.isdigit():
            selected_index = int(answer)
        else:
            print("Enter the number shown at the left of the COM port.",
                  flush=True)
            continue
        if 1 <= selected_index <= len(ordered):
            selected = ordered[selected_index - 1].device.upper()
            print(f"Opening N6DF v3 live stream on {selected}.", flush=True)
            return selected
        print(f"Choose a number from 1 to {len(ordered)}.", flush=True)


class LiveViewer:
    def __init__(self, root: tk.Tk, port: str):
        self.root = root
        self.port = port
        self.config = load_json(CONFIG_ROOT / "preprocessing.json")
        self.stop_event = threading.Event()
        self.frames: queue.Queue[DepthFrame] = queue.Queue(maxsize=1)
        self.frame_times: deque[float] = deque(maxlen=120)
        self.dropped_for_latency = 0
        self.fault: str | None = None
        self.raw_photo: ImageTk.PhotoImage | None = None
        self.model_photo: ImageTk.PhotoImage | None = None

        self.serial = Serial(port, 115200, timeout=0.2, write_timeout=2)
        self.serial.dtr = True
        self.reader = FrameReader(self.serial)
        self._build_ui()
        self._start_stream()
        self.worker = threading.Thread(target=self._reader_loop, daemon=True)
        self.worker.start()
        self.root.after(15, self._poll)

    def _build_ui(self) -> None:
        self.root.title("N6 live ToF — atomic N6DF v3 frames")
        self.root.geometry("1160x610")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        columns = tk.Frame(self.root)
        columns.pack(padx=12, pady=12)
        raw_column = tk.Frame(columns)
        raw_column.pack(side=tk.LEFT, padx=10)
        model_column = tk.Frame(columns)
        model_column.pack(side=tk.LEFT, padx=10)
        tk.Label(raw_column, text="RAW DEPTH — complete frame",
                 font=("Segoe UI", 11, "bold")).pack()
        tk.Label(model_column, text="EXACT NPU INPUT — complete frame",
                 font=("Segoe UI", 11, "bold")).pack()
        self.raw_label = tk.Label(raw_column, bg="black")
        self.raw_label.pack()
        self.model_label = tk.Label(model_column, bg="black")
        self.model_label.pack()
        self.status = tk.StringVar(value=f"Opening {self.port}...")
        tk.Label(self.root, textvariable=self.status, font=("Consolas", 11),
                 justify=tk.LEFT).pack(padx=12, pady=8)
        tk.Label(
            self.root,
            text=("Each image is swapped only after magic, dimensions, payload "
                  "length, frame ID and both CRC32 values are valid.  ESC closes."),
            font=("Segoe UI", 10),
        ).pack()

    def _start_stream(self) -> None:
        time.sleep(0.25)
        self.serial.reset_input_buffer()
        self.serial.write(b"\rDATASET STREAM OFF\rMAP OFF\r")
        self.serial.flush()
        time.sleep(0.25)
        self.serial.reset_input_buffer()
        self.serial.write(b"DATASET STREAM ON\r")
        self.serial.flush()

    def _reader_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                frame = self.reader.read_frame(timeout=1.0)
                if (frame.protocol_version != VERSION_V3 or
                        frame.model_input is None or
                        frame.model_width is None or
                        frame.model_height is None):
                    raise RuntimeError("firmware did not send an N6DF v3 model frame")
                while True:
                    try:
                        self.frames.get_nowait()
                        self.dropped_for_latency += 1
                    except queue.Empty:
                        break
                self.frames.put_nowait(frame)
            except TimeoutError:
                continue
            except Exception as exc:  # surfaced in the UI; cleanup stays safe
                self.fault = f"{type(exc).__name__}: {exc}"
                self.stop_event.set()
                return

    def _poll(self) -> None:
        latest: DepthFrame | None = None
        while True:
            try:
                latest = self.frames.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self._show_frame(latest)
        elif self.fault:
            self.status.set(f"STREAM ERROR: {self.fault}")
        if not self.stop_event.is_set():
            self.root.after(15, self._poll)

    def _show_frame(self, frame: DepthFrame) -> None:
        raw = preview_rgb(frame.depth_mm, self.config["near_mm"],
                          self.config["far_mm"], frame.invalid_mm)
        raw_image = Image.fromarray(raw).resize((540, 420),
                                                Image.Resampling.NEAREST)
        model_image = Image.fromarray(frame.model_input).resize(
            (512, 400), Image.Resampling.NEAREST
        )
        self.raw_photo = ImageTk.PhotoImage(raw_image)
        self.model_photo = ImageTk.PhotoImage(model_image)
        # Tk changes each widget image as one complete object; no partial rows
        # from a subsequent serial frame can enter the displayed bitmap.
        self.raw_label.configure(image=self.raw_photo)
        self.model_label.configure(image=self.model_photo)

        host = preprocess_depth(frame.depth_mm, self.config)[..., 0]
        different = int(np.count_nonzero(host != frame.model_input))
        exact = different == 0
        now = time.monotonic()
        self.frame_times.append(now)
        fps = 0.0
        if len(self.frame_times) > 1:
            fps = ((len(self.frame_times) - 1) /
                   (self.frame_times[-1] - self.frame_times[0]))
        raw_bytes = frame.width * frame.height * 2
        model_bytes = frame.model_width * frame.model_height
        self.status.set(
            f"N6DF v{frame.protocol_version}  frame={frame.frame_id}  "
            f"viewer={fps:.1f} fps\n"
            f"RAW: {frame.width}x{frame.height} uint16 = {raw_bytes} bytes  "
            f"CRC32=0x{frame.payload_crc32:08X}\n"
            f"NPU: {frame.model_width}x{frame.model_height} uint8 = "
            f"{model_bytes} bytes  CRC32=0x{frame.model_payload_crc32:08X}  "
            f"DEVICE/PYTHON={'BIT-EXACT' if exact else f'MISMATCH {different} px'}\n"
            f"Complete old frames skipped for low latency: "
            f"{self.dropped_for_latency}  parser CRC errors: "
            f"{self.reader.crc_errors}"
        )

    def close(self) -> None:
        if self.stop_event.is_set() and not self.root.winfo_exists():
            return
        self.stop_event.set()
        try:
            self.serial.write(b"DATASET STREAM OFF\r")
            self.serial.flush()
        except Exception:
            pass
        try:
            self.serial.close()
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="CN8 CDC port, for example COM8")
    args = parser.parse_args()
    try:
        port = choose_n6_port(args.port)
        root = tk.Tk()
        LiveViewer(root, port)
        root.mainloop()
        return 0
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
