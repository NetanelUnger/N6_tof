"""Bounded capture shared by the desktop window and unattended hardware checks."""
from __future__ import annotations
import time
import uuid
import numpy as np
from sample_store import DuplicateSample


def collect(source, store, *, samples, timeout, label=None, group_size=1,
            near_duplicate_mm=None, save_fps=None):
    if samples <= 0 or timeout <= 0 or group_size <= 0:
        raise ValueError("Positive sample count, timeout and group size are required.")
    started = time.monotonic()
    accepted = duplicates = content_skips = 0
    last_depth = None
    last_saved = 0.
    error = None
    group_prefix = uuid.uuid4().hex
    try:
        source.open()
        deadline = started + timeout
        while accepted < samples and time.monotonic() < deadline:
            try:
                sample = source.read(min(1., max(.01, deadline - time.monotonic())))
            except TimeoutError:
                continue
            now = time.monotonic()
            if save_fps and now - last_saved < 1. / save_fps:
                continue
            depth = sample.frame.depth_mm
            if near_duplicate_mm is not None and last_depth is not None:
                valid = (depth != sample.frame.invalid_mm) & (last_depth != sample.frame.invalid_mm)
                if valid.any() and float(np.abs(depth[valid].astype(np.int32) - last_depth[valid]).mean()) < near_duplicate_mm:
                    content_skips += 1
                    continue
            try:
                store.commit(sample, label=label, group=f"{group_prefix}-{accepted // group_size}")
            except DuplicateSample:
                duplicates += 1
                continue
            accepted += 1
            last_depth, last_saved = depth.copy(), now
        if accepted != samples:
            error = f"Capture deadline: {accepted}/{samples} committed."
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            source.stop()
        except Exception as exc:
            error = f"Source stop failed: {exc}"
    status = source.status()
    if status.get("restore_error"):
        error = "Runtime restoration failed: " + status["restore_error"]
    return {"status": "FAIL" if error else "PASS", "requested": samples,
            "committed": accepted, "duplicate_identities": duplicates,
            "content_skips": content_skips, "seconds": time.monotonic() - started,
            "content_filter_enabled": near_duplicate_mm is not None,
            "source": status, "error": error}
