"""Stage 02: import an existing labeled folder of exact 16-bit depth PNGs."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from common import (CONFIG_ROOT, RAW_ROOT, append_jsonl, class_names,
                    iter_jsonl, load_json, mark_stage, relative, sha256_file,
                    utc_now)
from dataset import save_depth_sample


def infer_label(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    known = set(class_names())
    for parent in path.parents:
        if parent.name.lower() in known:
            return parent.name.lower()
    raise RuntimeError(
        f"Cannot infer label for {path}; put it under none/rock/paper/scissors "
        "or pass --label."
    )


def read_depth_png(path: Path, allow_8bit: bool) -> tuple[np.ndarray, str]:
    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    with Image.open(path) as image:
        array = np.asarray(image)
    if array.ndim != 2:
        raise RuntimeError(
            f"{path} is RGB/preview data, not recoverable depth. Import the "
            "*.depth.png or *.npz source instead."
        )
    if array.dtype in (np.uint16, np.int32, np.uint32):
        depth = np.asarray(array, dtype=np.uint16)
        fidelity = "exact_uint16_mm"
    elif array.dtype == np.uint8 and allow_8bit:
        # Approximate inverse of the documented near=255/far=0 preview scale.
        span = cfg["far_mm"] - cfg["near_mm"]
        depth = np.rint(cfg["far_mm"] - array.astype(np.float32) *
                        span / 255.0).astype(np.uint16)
        fidelity = "approximate_from_uint8"
    else:
        raise RuntimeError(
            f"{path} is {array.dtype}; only 16-bit millimetre PNG is lossless. "
            "Use --allow-8bit only when approximate distances are acceptable."
        )
    expected = (cfg["source_height"], cfg["source_width"])
    if depth.shape != expected:
        raise RuntimeError(f"{path}: shape {depth.shape}, expected {expected}")
    return depth, fidelity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="PNG file or labeled folder")
    parser.add_argument("--label", choices=class_names())
    parser.add_argument("--session")
    parser.add_argument("--allow-8bit", action="store_true")
    args = parser.parse_args()
    source_text = args.source or input("Path to PNG file/folder: ").strip(' "')
    source = Path(source_text).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    files = [source] if source.is_file() else sorted(source.rglob("*.png"))
    files = [path for path in files if ".preview." not in path.name.lower()]
    if not files:
        raise RuntimeError(f"No importable PNG files found under {source}")
    # A stable default session makes a plain rerun resume the same import.
    # Global source hashes also prevent duplication if the folder was renamed
    # or an explicit session is supplied later.
    source_identity = hashlib.sha256(
        str(source).casefold().encode("utf-8")
    ).hexdigest()[:12]
    session_id = args.session or f"import_{source_identity}"
    session_root = RAW_ROOT / session_id
    metadata_path = session_root / "metadata.jsonl"
    imported_sources = {
        row.get("source_sha256")
        for existing_metadata in RAW_ROOT.glob("*/metadata.jsonl")
        for row in iter_jsonl(existing_metadata)
        if row.get("source_sha256")
    }
    imported = skipped = failed = 0
    for index, path in enumerate(files):
        source_hash = sha256_file(path)
        if source_hash in imported_sources:
            skipped += 1
            continue
        try:
            label = infer_label(path, args.label)
            depth, fidelity = read_depth_png(path, args.allow_8bit)
            stem = f"import_{source_hash[:12]}_{index:05d}"
            record = save_depth_sample(session_root, label, stem, depth, {
                "schema": 1,
                "session_id": session_id,
                "burst_id": "import_" + hashlib.sha256(
                    str(path.parent.resolve()).encode("utf-8")
                ).hexdigest()[:12],
                "source": "png_import",
                "source_path": str(path),
                "source_sha256": source_hash,
                "source_fidelity": fidelity,
                "captured_utc": utc_now(),
            })
            append_jsonl(metadata_path, record)
            imported_sources.add(source_hash)
            imported += 1
        except Exception as exc:
            failed += 1
            print(f"SKIP {path}: {exc}")
    status = "complete" if failed == 0 else "complete_with_warnings"
    mark_stage("02_import_png", status=status,
               outputs=[relative(session_root)],
               details={"imported": imported, "already_present": skipped,
                        "failed": failed})
    print(f"Imported {imported}; already present {skipped}; rejected {failed}.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
