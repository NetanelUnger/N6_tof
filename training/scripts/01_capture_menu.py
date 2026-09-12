"""Interactive launcher for the Stage 01 ToF dataset capture tool."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from common import (CONFIG_ROOT, RAW_ROOT, apply_review, class_config,
                    iter_jsonl, load_json, load_review_decisions)


CAPTURE_SCRIPT = Path(__file__).with_name("01_capture.py")
SESSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def prompt_positive_int(prompt: str, default: int) -> int:
    while True:
        value = read_line(f"{prompt} [{default}]: ")
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
        print("Please enter a positive whole number.")


def prompt_positive_float(prompt: str, default: float) -> float:
    while True:
        value = read_line(f"{prompt} [{default:g}]: ")
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            parsed = 0.0
        if parsed > 0.0:
            return parsed
        print("Please enter a positive number.")


def load_session(path: Path, class_names: list[str],
                 review_decisions: dict) -> dict:
    state_path = path / "session.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    counts: Counter[str] = Counter()
    for raw_row in iter_jsonl(path / "metadata.jsonl"):
        row = apply_review(raw_row, review_decisions)
        if row.get("accepted", True):
            counts[str(row.get("label", "unknown"))] += 1
    return {
        "id": path.name,
        "path": path,
        "status": state.get("status", "unknown"),
        "target": state.get("target_per_class"),
        "counts": {name: counts[name] for name in class_names},
    }


def sessions(class_names: list[str]) -> list[dict]:
    if not RAW_ROOT.exists():
        return []
    review_decisions = load_review_decisions()
    return [
        load_session(path, class_names, review_decisions)
        for path in sorted(
            (item for item in RAW_ROOT.iterdir() if item.is_dir()),
            key=lambda item: item.name,
            reverse=True,
        )
    ]


def print_sessions(rows: list[dict], class_names: list[str]) -> None:
    if not rows:
        print("\nNo saved capture sessions were found.\n")
        return
    print("\nSaved capture sessions:")
    for index, row in enumerate(rows, start=1):
        counts = ", ".join(
            f"{name}={row['counts'][name]}" for name in class_names
        )
        target = f", target={row['target']}" if row["target"] else ""
        print(
            f"  [{index}] {row['id']}  ({counts}; "
            f"status={row['status']}{target})"
        )
    print()


def choose_session(rows: list[dict], class_names: list[str]) -> dict | None:
    print_sessions(rows, class_names)
    if not rows:
        return None
    while True:
        answer = read_line("Select a session number, or Q to cancel: ").lower()
        if answer == "q":
            return None
        try:
            index = int(answer) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(rows):
            return rows[index]
        print("Invalid session selection.")


def choose_label(class_names: list[str]) -> str | None:
    print("\nInitial label (you can still change it with R/P/S/N in the window):")
    print("  [0] Automatic / first incomplete class")
    for index, name in enumerate(class_names, start=1):
        print(f"  [{index}] {name}")
    while True:
        answer = read_line("Select initial label [0]: ")
        if not answer or answer == "0":
            return None
        try:
            index = int(answer) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(class_names):
            return class_names[index]
        print("Invalid label selection.")


def run_capture(arguments: list[str]) -> int:
    command = [sys.executable, str(CAPTURE_SCRIPT), *arguments]
    print("\nStarting capture with:")
    print("  " + subprocess.list2cmdline(command))
    print("IMPORTANT: save a burst only when the complete gesture is clear in MODEL INPUT.\n")
    return subprocess.run(command, check=False).returncode


def new_session(capture_cfg: dict) -> int:
    print("\nNEW SESSION — a timestamped folder will be created automatically.")
    print("For the three-session plan, 48 samples per class per session is a good start.")
    target = prompt_positive_int(
        "Final saved images per class in this session",
        int(capture_cfg["target_per_class"]),
    )
    return run_capture(["--target-per-class", str(target)])


def resume_session(rows: list[dict], class_names: list[str],
                   capture_cfg: dict) -> int | None:
    selected = choose_session(rows, class_names)
    if selected is None:
        return None
    counts = selected["counts"]
    old_target = int(selected["target"] or capture_cfg["target_per_class"])
    if any(counts[name] < old_target for name in class_names):
        suggested_target = old_target
    else:
        suggested_target = max(counts.values(), default=old_target) + 48
    print(
        "The target below is the FINAL total per class in this session, "
        "not the number to add."
    )
    target = prompt_positive_int(
        "Final target per class", suggested_target
    )
    return run_capture([
        "--session", selected["id"],
        "--target-per-class", str(target),
    ])


def advanced_capture(class_names: list[str], capture_cfg: dict) -> int | None:
    print("\nADVANCED CAPTURE SETTINGS")
    print("Leave the session blank to create an automatic timestamped session.")
    session_id = read_line("Session ID [automatic]: ")
    if session_id and (not SESSION_PATTERN.fullmatch(session_id) or
                       session_id in {".", ".."}):
        print("Invalid session ID. Use only letters, digits, dot, underscore or hyphen.")
        return None
    port = read_line("Serial port [automatic detection, e.g. COM12]: ")
    target = prompt_positive_int(
        "Final saved images per class",
        int(capture_cfg["target_per_class"]),
    )
    samples_per_burst = prompt_positive_int(
        "Maximum saved images per burst",
        int(capture_cfg["samples_per_burst"]),
    )
    save_fps = prompt_positive_float(
        "Saved frames per second",
        float(capture_cfg["save_fps"]),
    )
    label = choose_label(class_names)
    arguments = [
        "--target-per-class", str(target),
        "--samples-per-burst", str(samples_per_burst),
        "--save-fps", str(save_fps),
    ]
    if session_id:
        arguments.extend(["--session", session_id])
    if port:
        arguments.extend(["--port", port])
    if label:
        arguments.extend(["--label", label])
    answer = read_line("Start capture with these settings? [Y/n]: ").lower()
    if answer not in {"", "y", "yes"}:
        print("Advanced capture cancelled.")
        return None
    return run_capture(arguments)


def main() -> int:
    training_cfg = load_json(CONFIG_ROOT / "training.json")
    capture_cfg = training_cfg["capture"]
    class_names = [item["name"] for item in class_config()]

    while True:
        print("\n============================================================")
        print("N6 DATASET CAPTURE MENU")
        print("============================================================")
        print("  [1] START A NEW SESSION  (recommended for more diversity)")
        print("  [2] RESUME AN EXISTING SESSION")
        print("  [3] ADVANCED CAPTURE SETTINGS")
        print("  [4] SHOW SAVED SESSIONS")
        print("  [Q] CANCEL")
        answer = read_line("Select 1, 2, 3, 4, or Q: ").lower()
        rows = sessions(class_names)
        if answer == "1":
            return new_session(capture_cfg)
        if answer == "2":
            result = resume_session(rows, class_names, capture_cfg)
            if result is not None:
                return result
        elif answer == "3":
            result = advanced_capture(class_names, capture_cfg)
            if result is not None:
                return result
        elif answer == "4":
            print_sessions(rows, class_names)
        elif answer == "q":
            print("Capture cancelled. Nothing was changed.")
            return 0
        else:
            print("Invalid menu selection.")


if __name__ == "__main__":
    raise SystemExit(main())
