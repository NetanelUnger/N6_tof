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


def flatten_binary_silhouette(image: np.ndarray, *, threshold: int = 0,
                              dilation_iterations: int = 1,
                              foreground_value: int = 255,
                              background_value: int = 0) -> np.ndarray:
    """Turn every non-black stage-5 pixel white and repair thin dropouts."""
    source = np.asarray(image, dtype=np.uint8)
    if source.ndim != 2:
        raise ValueError(f"binary silhouette expects a 2-D image, got {source.shape}")
    binary = source > int(threshold)
    height, width = source.shape
    for _ in range(int(dilation_iterations)):
        padded = np.pad(binary, 1, mode="constant", constant_values=False)
        binary = np.logical_or.reduce([
            padded[row:row + height, column:column + width]
            for row in range(3) for column in range(3)
        ])
    return np.where(binary, int(foreground_value),
                    int(background_value)).astype(np.uint8)


def _round_even_ratio(numerator: int, denominator: int) -> int:
    """Exact integer equivalent of the firmware's positive round-to-even."""
    quotient, remainder = divmod(int(numerator), int(denominator))
    twice = remainder * 2
    if twice > denominator or (twice == denominator and quotient & 1):
        quotient += 1
    return quotient


def resize_nearest_centered(image: np.ndarray, target_width: int,
                            target_height: int, background_value: int, *,
                            preserve_aspect: bool = True,
                            border_pixels: int = 0) -> np.ndarray:
    """Bit-exact counterpart of firmware rps_resize_nearest()."""
    source = np.asarray(image, dtype=np.uint8)
    if source.ndim != 2 or source.shape[0] == 0 or source.shape[1] == 0:
        raise ValueError(f"nearest resize expects a non-empty 2-D image, got {source.shape}")
    border = int(border_pixels)
    maximum_width = int(target_width) - (2 * border)
    maximum_height = int(target_height) - (2 * border)
    if maximum_width <= 0 or maximum_height <= 0:
        raise ValueError("model border leaves no resize area")
    source_height, source_width = source.shape
    if preserve_aspect:
        if maximum_width * source_height <= maximum_height * source_width:
            resized_width = maximum_width
            resized_height = _round_even_ratio(
                source_height * maximum_width, source_width
            )
        else:
            resized_height = maximum_height
            resized_width = _round_even_ratio(
                source_width * maximum_height, source_height
            )
    else:
        resized_width = maximum_width
        resized_height = maximum_height
    resized_width = max(1, resized_width)
    resized_height = max(1, resized_height)
    source_columns = (
        ((2 * np.arange(resized_width, dtype=np.uint32) + 1) * source_width) //
        (2 * resized_width)
    )
    source_rows = (
        ((2 * np.arange(resized_height, dtype=np.uint32) + 1) * source_height) //
        (2 * resized_height)
    )
    resized = source[source_rows[:, None], source_columns[None, :]]
    canvas = np.full((target_height, target_width), int(background_value),
                     dtype=np.uint8)
    x_offset = (target_width - resized_width) // 2
    y_offset = (target_height - resized_height) // 2
    canvas[y_offset:y_offset + resized_height,
           x_offset:x_offset + resized_width] = resized
    return canvas


def preprocess_depth(depth_mm: np.ndarray,
                     config: dict[str, Any] | None = None) -> np.ndarray:
    cfg = config or load_json(CONFIG_ROOT / "preprocessing.json")
    depth = np.asarray(depth_mm, dtype=np.uint16)
    expected = (cfg["source_height"], cfg["source_width"])
    if depth.shape != expected:
        raise ValueError(f"depth shape {depth.shape}, expected {expected}")
    model_max_distance = int(cfg.get("model_max_distance_mm", cfg["far_mm"]))
    invalid = ((depth == cfg["invalid_mm"]) | (depth == 0) |
               (depth < cfg["near_mm"]) | (depth > model_max_distance))
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
    target_width = int(cfg["model_width"])
    target_height = int(cfg["model_height"])
    image = resize_nearest_centered(
        image, target_width, target_height, int(cfg["far_value"]),
        preserve_aspect=bool(cfg.get("preserve_aspect_and_center", False)),
        border_pixels=int(cfg.get("model_border_pixels", 0)),
    )
    if cfg.get("flatten_foreground_after_normalization", False):
        # Match the exact firmware NPU path: keep normalized OBJECT 5 pixels
        # above the promoted near-surface threshold, then repair thin sensor
        # dropout stripes with a 3x3 binary dilation. A completely empty image
        # stays completely black.
        image = flatten_binary_silhouette(
            image,
            threshold=int(cfg.get("binary_foreground_threshold", 0)),
            dilation_iterations=int(cfg.get("binary_dilation_iterations", 0)),
            foreground_value=int(cfg["flat_foreground_value"]),
            background_value=int(cfg["far_value"]),
        )
    return image[..., np.newaxis]


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
        threshold = min(float(cfg.get("model_max_distance_mm", cfg["far_mm"])),
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
            # The global foreground band finds a reliable near seed. Continue
            # across a sloped object using local depth continuity so a sheet
            # spanning more than the global 220 mm band is not cut into
            # parallel strips. `valid` still enforces the absolute 600 mm cap.
            maximum_neighbor_jump = int(
                cfg.get("component_neighbor_depth_jump_mm", 0)
            )
            if maximum_neighbor_jump > 0:
                stack = [(int(row), int(column))
                         for row, column in selected]
                while stack:
                    row, column = stack.pop()
                    current_depth = int(depth[row, column])
                    for row_delta, column_delta in neighbors:
                        next_row = row + row_delta
                        next_column = column + column_delta
                        if not (0 <= next_row < depth.shape[0] and
                                0 <= next_column < depth.shape[1]):
                            continue
                        if result[next_row, next_column] or not valid[
                                next_row, next_column]:
                            continue
                        if abs(int(depth[next_row, next_column]) -
                               current_depth) > maximum_neighbor_jump:
                            continue
                        result[next_row, next_column] = True
                        stack.append((next_row, next_column))
            return result
    return np.zeros(depth.shape, dtype=bool)


def save_depth_sample(session_root: Path, label: str, stem: str,
                      depth_mm: np.ndarray, metadata: dict[str, Any], *,
                      device_model_input: np.ndarray | None = None) -> dict[str, Any]:
    cfg = load_json(CONFIG_ROOT / "preprocessing.json")
    depth = np.asarray(depth_mm, dtype="<u2", order="C")
    host_model_input = preprocess_depth(depth, cfg)[..., 0]
    exact_device_input = None
    if device_model_input is not None:
        exact_device_input = np.asarray(
            device_model_input, dtype=np.uint8, order="C"
        )
        if exact_device_input.shape != host_model_input.shape:
            raise ValueError(
                "device model-input shape mismatch: "
                f"device={exact_device_input.shape}, host={host_model_input.shape}"
            )
        if not np.array_equal(exact_device_input, host_model_input):
            mismatch = int(np.count_nonzero(exact_device_input != host_model_input))
            maximum_delta = int(np.max(np.abs(
                exact_device_input.astype(np.int16) -
                host_model_input.astype(np.int16)
            )))
            raise ValueError(
                "device/Python preprocessing mismatch: "
                f"{mismatch} pixels differ, maximum delta {maximum_delta}"
            )
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
    if exact_device_input is None:
        np.savez_compressed(npz_path, depth_mm=depth)
    else:
        np.savez_compressed(
            npz_path, depth_mm=depth,
            device_model_input_u8=exact_device_input,
        )
    Image.fromarray(depth).save(png_path, compress_level=1)
    preview = preview_rgb(depth, cfg["near_mm"], cfg["far_mm"],
                          cfg["invalid_mm"])
    Image.fromarray(preview).resize(
        (cfg["source_width"] * 8, cfg["source_height"] * 8),
        Image.Resampling.NEAREST).save(preview_path, compress_level=1)
    model_input = (exact_device_input if exact_device_input is not None
                   else host_model_input)
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
        "model_input_source": (
            "device_n6df_v3_verified_against_python"
            if exact_device_input is not None else "python_preprocessing"
        ),
        "device_model_input_sha256": (
            hashlib.sha256(exact_device_input.tobytes(order="C")).hexdigest()
            if exact_device_input is not None else None
        ),
        "accepted": True,
    })
    return record


def load_depth_record(record: dict[str, Any]) -> np.ndarray:
    npz_path = TRAINING_ROOT / record["npz"]
    with np.load(npz_path, allow_pickle=False) as archive:
        return np.asarray(archive["depth_mm"], dtype=np.uint16)


def load_device_model_input_record(
        record: dict[str, Any]) -> np.ndarray | None:
    npz_path = TRAINING_ROOT / record["npz"]
    with np.load(npz_path, allow_pickle=False) as archive:
        if "device_model_input_u8" not in archive:
            return None
        return np.asarray(archive["device_model_input_u8"], dtype=np.uint8)
