"""Full-field depth profile: absolute range and position are preserved."""
import numpy as np


def preprocess(depth, config):
    depth = np.asarray(depth, dtype=np.uint16)
    near, far = int(config["near_mm"]), int(config["far_mm"])
    if not 0 < near < far < int(config["invalid_mm"]) <= 65535:
        raise ValueError("Invalid spatial depth range.")
    height, width = depth.shape
    rows = ((2 * np.arange(config["model_height"]) + 1) * height) // (2 * config["model_height"])
    columns = ((2 * np.arange(config["model_width"]) + 1) * width) // (2 * config["model_width"])
    values = depth[rows[:, None], columns[None, :]].astype(np.int32)
    valid = (values > 0) & (values != config["invalid_mm"])
    clipped = np.clip(values, near, far)
    encoded = 1 + ((far - clipped) * 254 + (far - near) // 2) // (far - near)
    return np.where(valid, encoded, 0).astype(np.uint8)[..., None]
