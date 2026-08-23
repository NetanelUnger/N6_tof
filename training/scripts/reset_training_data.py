"""Safely remove generated Rock/Paper/Scissors training artifacts.

This deliberately preserves the training tools, configuration, virtual
environment and the last model integrated in AppliNonSecure/AI.  The latter
keeps the board usable for capturing a fresh dataset; stage 08 replaces it
after a new model has been generated.
"""

from __future__ import annotations

import argparse
import json
import shutil
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
)
EXTERNAL_TARGETS = (PROJECT_ROOT / "st_ai_output",)
KEEP_NAMES = {".gitkeep"}


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


def _clear_directory(path: Path, dry_run: bool) -> None:
    if not path.exists():
        return
    for child in list(path.iterdir()):
        if child.name in KEEP_NAMES:
            continue
        if dry_run:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


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

    for target in TRAINING_TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        _clear_directory(target, dry_run=False)
    for target in EXTERNAL_TARGETS:
        if target.exists():
            shutil.rmtree(target)

    report = {
        "reset_utc": datetime.now(timezone.utc).isoformat(),
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
