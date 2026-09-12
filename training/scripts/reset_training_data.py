"""Safely remove generated Rock/Paper/Scissors training artifacts.

This deliberately preserves the training tools, configuration, virtual
environment and the last model integrated in AppliNonSecure/AI.  The latter
keeps the board usable for capturing a fresh dataset; stage 08 replaces it
after a new model has been generated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import time
from datetime import datetime, timezone
from pathlib import Path


TRAINING_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TRAINING_ROOT.parent
TRAINING_TARGETS = (
    TRAINING_ROOT / "data" / "raw",
    TRAINING_ROOT / "data" / "prepared",
    TRAINING_ROOT / "models",
    TRAINING_ROOT / "generated",
    TRAINING_ROOT / "reports",
    TRAINING_ROOT / "state",
    TRAINING_ROOT / "review",
)
EXTERNAL_TARGETS = (PROJECT_ROOT / "st_ai_output",)
KEEP_NAMES = {".gitkeep"}
DELETE_ATTEMPTS = 10
DELETE_INITIAL_DELAY_SECONDS = 0.25


def _validate_targets() -> None:
    expected_training = {path.resolve() for path in TRAINING_TARGETS}
    for target in TRAINING_TARGETS:
        if target.is_symlink():
            raise RuntimeError(f"Reset target must not be a symlink: {target}")
        resolved = target.resolve()
        if resolved not in expected_training or TRAINING_ROOT.resolve() not in resolved.parents:
            raise RuntimeError(f"Unsafe training reset target: {resolved}")

    expected_external = (PROJECT_ROOT / "st_ai_output").resolve()
    if len(EXTERNAL_TARGETS) != 1 or EXTERNAL_TARGETS[0].resolve() != expected_external:
        raise RuntimeError("Unsafe external reset target")
    if EXTERNAL_TARGETS[0].is_symlink():
        raise RuntimeError(f"Reset target must not be a symlink: {EXTERNAL_TARGETS[0]}")


def _measure(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file() or path.is_symlink():
        return 1, path.stat().st_size if path.is_file() else 0
    files = 0
    size = 0
    for item in path.rglob("*"):
        if item.is_file() and item.name not in KEEP_NAMES:
            files += 1
            try:
                size += item.stat().st_size
            except FileNotFoundError:
                pass
    return files, size


def _rmtree_onerror(function, filename: str, exc_info) -> None:
    """Retry read-only entries, but leave sharing violations to the outer loop."""
    error = exc_info[1]
    if isinstance(error, PermissionError) and getattr(error, "winerror", None) == 5:
        os.chmod(filename, stat.S_IWRITE)
        function(filename)
        return
    raise error


def _remove_once(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=_rmtree_onerror)
        return
    try:
        path.unlink()
    except PermissionError as error:
        if getattr(error, "winerror", None) != 5:
            raise
        path.chmod(stat.S_IWRITE)
        path.unlink()


def _remove_with_retries(path: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(1, DELETE_ATTEMPTS + 1):
        try:
            _remove_once(path)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            last_error = error
            if attempt == DELETE_ATTEMPTS:
                break
            delay = min(
                DELETE_INITIAL_DELAY_SECONDS * (2 ** (attempt - 1)), 2.0
            )
            print(
                f"Windows is still using {path}; retry "
                f"{attempt}/{DELETE_ATTEMPTS} in {delay:.2f}s...",
                flush=True,
            )
            time.sleep(delay)
    assert last_error is not None
    winerror = getattr(last_error, "winerror", None)
    detail = f"WinError {winerror}" if winerror is not None else type(last_error).__name__
    raise RuntimeError(f"{detail}: {path}: {last_error}") from last_error


def _clear_directory(path: Path, dry_run: bool) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return failures
    for child in list(path.iterdir()):
        if child.name in KEEP_NAMES:
            continue
        if dry_run:
            continue
        try:
            _remove_with_retries(child)
        except RuntimeError as error:
            failures.append(str(error))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", help="Must be exactly DELETE for a real reset")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be removed")
    args = parser.parse_args()

    _validate_targets()
    if not args.dry_run and args.confirm != "DELETE":
        raise RuntimeError("Reset refused. Pass --confirm DELETE after reading the warning.")

    rows = []
    for target in (*TRAINING_TARGETS, *EXTERNAL_TARGETS):
        files, size = _measure(target)
        rows.append({"path": str(target), "files": files, "bytes": size})
        print(f"{'Would remove' if args.dry_run else 'Removing'}: {target} ({files} files, {size} bytes)")

    if args.dry_run:
        print("Dry run only; nothing was changed.")
        return 0

    failures = []
    for target in TRAINING_TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        failures.extend(_clear_directory(target, dry_run=False))
    for target in EXTERNAL_TARGETS:
        if target.exists():
            try:
                _remove_with_retries(target)
            except RuntimeError as error:
                failures.append(str(error))

    if failures:
        print("\nReset incomplete. These paths remained locked:")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "Close Capture/VIEW_LIVE/dataset review windows and any File "
            "Explorer window inside training. If necessary, pause Dropbox "
            "sync briefly, then run RESET_TRAINING_DATA.bat again. The reset "
            "is idempotent and will only remove what remains."
        )
        return 2

    report = {
        "reset_utc": datetime.now(timezone.utc).isoformat(),
        "completed": True,
        "removed": rows,
        "total_files": sum(row["files"] for row in rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "preserved": [
            str(TRAINING_ROOT / ".venv"),
            str(TRAINING_ROOT / "scripts"),
            str(TRAINING_ROOT / "config"),
            str(PROJECT_ROOT / "AppliNonSecure" / "AI"),
        ],
        "note": "The integrated firmware model is preserved only so capture firmware remains runnable; stage 08 replaces it.",
    }
    report_path = TRAINING_ROOT / "reset_log.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Reset complete: {report['total_files']} files, {report['total_bytes']} bytes removed.")
    print(f"Audit log: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
