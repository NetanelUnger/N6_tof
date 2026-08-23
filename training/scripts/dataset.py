"""Depth-image storage and the one canonical PC/device preprocessing contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from common import CONFIG_ROOT, TRAINING_ROOT, load_json


def depth_sha256(depth_mm: np.ndarray) -> str:
    depth = np.asarray(depth_mm, dtype="<u2", order="C")
    return hashlib.sha256(depth.tobytes()).hexdigest()


def preview_rgb(depth_mm: np.ndarray, near_mm: int, far_mm: int,
                invalid_mm: int = 0xFFFF) -> np.ndarray:
    depth = np.asarray(depth_mm, dtype=np.uint16)
    valid = (depth != invalid_mm) & (depth > 0)
    span = max(1, far_mm - near_mm)
    normalized = 1.0 - np.clip((depth.astype(np.float32) - near_mm) / span,
                               0.0, 1.0)
    # Compact turbo-like educational palette: blue -> cyan -> yellow -> red.
    r = np.clip(1.5 - np.abs(4.0 * normalized - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * normalized - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * normalized - 1.0), 0.0, 1.0)
    rgb = (np.stack((r, g, b), axis=-1) * 255.0).astype(np.uint8)
    rgb[~valid] = 0
    return rgb


def preprocess_depth(depth_mm: np.ndarray,
                     config: dict[str, Any] | None = None) -> np.ndarray:
    cfg = config or load_json(CONFIG_ROOT / "preprocessing.json")
    depth = np.asarray(depth_mm, dtype=np.uint16)
    expected = (cfg["source_height"], cfg["source_width"])
    if depth.shape != expected:
        raise ValueError(f"depth shape {depth.shape}, expected {expected}")
    invalid = ((depth == cfg["invalid_mm"]) | (depth == 0) |
               (depth < cfg["near_mm"]) | (depth > cfg["far_mm"]))
    image = np.full(depth.shape, cfg["far_value"], dtype=np.uint8)
    foreground = np.zeros(depth.shape, dtype=bool)
    if cfg.get("foreground_mode") == "nearest_connected_component_relative":
        foreground = nearest_connected_component(depth, ~invalid, cfg)
        if np.any(foreground):
            values = depth[foreground]
            reference_mm = float(np.percentile(
                values, cfg["relative_reference_percentile"]
            ))
            delta = np.clip(values.astype(np.float32) - reference_mm, 0.0,
                            float(cfg["relative_depth_span_mm"]))
            floor = int(cfg["foreground_floor_value"])
            encoded = floor + np.rint(
                (cfg["relative_depth_span_mm"] - delta) * (255 - floor) /
                cfg["relative_depth_span_mm"]
            ).astype(np.uint8)
            image[foreground] = encoded
    else:
        clipped = np.clip(depth.astype(np.float32), cfg["near_mm"], cfg["far_mm"])
        scale = 255.0 / max(1, cfg["far_mm"] - cfg["near_mm"])
        image = np.rint((cfg["far_mm"] - clipped) * scale).astype(np.uint8)
        image[invalid] = cfg["far_value"]
        foreground = ~invalid
    if np.any(foreground):
        rows, columns = np.nonzero(foreground)
        margin = int(cfg["foreground_margin_pixels"])
        top = max(0, int(rows.min()) - margin)
        bottom = min(depth.shape[0], int(rows.max()) + margin + 1)
        left = max(0, int(columns.min()) - margin)
        right = min(depth.shape[1], int(columns.max()) + margin + 1)
        image = image[top:bottom, left:right]
    pil = Image.fromarray(image)
    target_width = int(cfg["model_width"])
    target_height = int(cfg["model_height"])
    if cfg.get("preserve_aspect_and_center", False):
        source_width, source_height = pil.size
        resize_scale = min(target_width / max(1, source_width),
                           target_height / max(1, source_height))
        resized_width = max(1, int(round(source_width * resize_scale)))
        resized_height = max(1, int(round(source_height * resize_scale)))
        pil = pil.resize((resized_width, resized_height),
                         Image.Resampling.NEAREST)
        canvas = Image.new("L", (target_width, target_height),
                           color=int(cfg["far_value"]))
        canvas.paste(pil, ((target_width - resized_width) // 2,
                           (target_height - resized_height) // 2))
        pil = canvas
    else:
        pil = pil.resize((target_width, target_height),
                         Image.Resampling.NEAREST)
    return np.asarray(pil, dtype=np.uint8)[..., np.newaxis]


def nearest_connected_component(depth: np.ndarray, valid: np.ndarray,
                                cfg: dict[str, Any]) -> np.ndarray:
    """Select the nearest non-trivial 8-connected depth object.

    Search thresholds grow gradually so a hand wins before a disconnected
    wall. Tiny close speckles are ignored. The implementation is deliberately
    simple so the firmware can reproduce it without an allocator.
    """
    if not np.any(valid):
        return np.zeros(depth.shape, dtype=bool)
    connectivity = int(cfg.get("component_connectivity", 8))
    if connectivity not in (4, 8):
        raise ValueError("component_connectivity must be 4 or 8")
    neighbors = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if connectivity == 8:
        neighbors += ((-1, -1), (-1, 1), (1, -1), (1, 1))
    valid_values = depth[valid]
    for percentile in cfg["component_search_percentiles"]:
        reference = float(np.percentile(valid_values, percentile))
        threshold = min(float(cfg["far_mm"]),
                        reference + float(cfg["foreground_band_mm"]))
        candidate = valid & (depth <= threshold)
        visited = np.zeros(depth.shape, dtype=bool)
        components: list[tuple[int, int, list[tuple[int, int]]]] = []
        for start_row, start_column in np.argwhere(candidate):
            if visited[start_row, start_column]:
                continue
            stack = [(int(start_row), int(start_column))]
            visited[start_row, start_column] = True
            pixels: list[tuple[int, int]] = []
            minimum_depth = int(cfg["far_mm"])
            while stack:
                row, column = stack.pop()
                pixels.append((row, column))
                minimum_depth = min(minimum_depth, int(depth[row, column]))
                for row_delta, column_delta in neighbors:
                    next_row = row + row_delta
                    next_column = column + column_delta
                    if (0 <= next_row < depth.shape[0] and
                            0 <= next_column < depth.shape[1] and
                            candidate[next_row, next_column] and
                            not visited[next_row, next_column]):
                        visited[next_row, next_column] = True
                        stack.append((next_row, next_column))
            if len(pixels) >= int(cfg["component_min_pixels"]):
                components.append((minimum_depth, -len(pixels), pixels))
        if components:
            _, _, selected = min(components, key=lambda item: (item[0], item[1]))
            result = np.zeros(depth.shape, dtype=bool)
            rows, columns = zip(*selected)
            result[np.asarray(rows), np.asarray(columns)] = True
            return result
    return np.zeros(depth.shape, dtype=bool)


def save_depth_sample(session_root: Path, label: str, stem: str,
                      depth_mm: np.ndarray, metadata: dict[str, Any]) -> dict[str, Any]:
    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    depth = np.asarray(depth_mm, dtype="<u2", order="C")
    class_root = session_root / label
    preview_root = session_root / "previews" / label
    model_input_root = session_root / "model_inputs" / label
    class_root.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    model_input_root.mkdir(parents=True, exist_ok=True)
    npz_path = class_root / f"{stem}.npz"
    png_path = class_root / f"{stem}.depth.png"
    preview_path = preview_root / f"{stem}.preview.png"
    model_input_path = model_input_root / f"{stem}.model.png"
    np.savez_compressed(npz_path, depth_mm=depth)
    Image.fromarray(depth).save(png_path, compress_level=1)
    preview = preview_rgb(depth, cfg["near_mm"], cfg["far_mm"],
                          cfg["invalid_mm"])
    Image.fromarray(preview).resize(
        (cfg["source_width"] * 8, cfg["source_height"] * 8),
        Image.Resampling.NEAREST).save(preview_path, compress_level=1)
    model_input = preprocess_depth(depth, cfg)[..., 0]
    Image.fromarray(model_input).resize(
        (cfg["model_width"] * 6, cfg["model_height"] * 6),
        Image.Resampling.NEAREST).save(model_input_path, compress_level=1)
    record = dict(metadata)
    record.update({
        "label": label,
        "depth_sha256": depth_sha256(depth),
        "npz": str(npz_path.resolve().relative_to(TRAINING_ROOT.resolve())),
        "depth_png": str(png_path.resolve().relative_to(TRAINING_ROOT.resolve())),
        "preview_png": str(preview_path.resolve().relative_to(TRAINING_ROOT.resolve())),
        "model_input_png": str(
            model_input_path.resolve().relative_to(TRAINING_ROOT.resolve())
        ),
        "shape": list(depth.shape),
        "dtype": "uint16_mm",
        "accepted": True,
    })
    return record


def load_depth_record(record: dict[str, Any]) -> np.ndarray:
    npz_path = TRAINING_ROOT / record["npz"]
    with np.load(npz_path, allow_pickle=False) as archive:
        return np.asarray(archive["depth_mm"], dtype=np.uint16)
