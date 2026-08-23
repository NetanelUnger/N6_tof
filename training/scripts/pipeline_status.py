"""Show resumable pipeline state and real artifact counts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from common import (CONFIG_ROOT, MODELS_ROOT, RAW_ROOT, STATE_ROOT,
                    class_names, iter_jsonl, load_json,
                    npu_deployment_fingerprint)


STAGES = (
    ("00_setup", "00_SETUP.bat"),
    ("01_capture", "01_CAPTURE.bat"),
    ("03_validate", "03_VALIDATE.bat"),
    ("04_prepare", "04_PREPARE.bat"),
    ("05_train", "05_TRAIN.bat"),
    ("06_quantize", "06_QUANTIZE.bat"),
    ("07_generate_n6", "07_GENERATE_N6.bat"),
    ("08_integrate", "08_INTEGRATE_MODEL.bat"),
    ("10_ram", "10_LOAD_RAM.bat"),
    ("09_hil", "09_HIL.bat"),
    ("08_secure_bootstrap", "08B_BOOTSTRAP_NPU_SWD.bat"),
    ("11_flash", "11_FLASH_RELEASE.bat"),
)


def main() -> int:
    counts: Counter[str] = Counter()
    bursts: defaultdict[str, set[str]] = defaultdict(set)
    sessions = 0
    for metadata in RAW_ROOT.glob("*/metadata.jsonl"):
        sessions += 1
        for row in iter_jsonl(metadata):
            if row.get("accepted", True):
                label = row.get("label", "unknown")
                counts[label] += 1
                if row.get("burst_id"):
                    bursts[label].add(row["burst_id"])
    print("\nDataset")
    print(f"  sessions: {sessions}")
    minimum_bursts = load_json(CONFIG_ROOT / "training.json")["capture"][
        "minimum_bursts_per_class"
    ]
    for name in class_names():
        burst_count = len(bursts[name])
        missing = max(0, minimum_bursts - burst_count)
        suffix = f"  [NEED {missing} MORE BURST(S)]" if missing else ""
        print(f"  {name:9s}: {counts[name]} frames, "
              f"{burst_count} bursts{suffix}")
    print("\nStages")
    deployment = None
    try:
        deployment = npu_deployment_fingerprint()
    except RuntimeError:
        pass
    first_action = None
    for stage, bat in STAGES:
        state_path = STATE_ROOT / f"{stage}.json"
        if not state_path.exists():
            print(f"  {stage:20s} not-run     -> {bat}")
            if first_action is None:
                first_action = bat
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            status = state.get("status", "?")
            if (stage == "09_hil" and status == "complete" and deployment and
                    state.get("input_fingerprint") != deployment):
                status = "stale"
            print(f"  {stage:20s} {status:10s} "
                  f"{state.get('updated_utc', '')}  [{bat}]")
            if first_action is None and status not in {"complete"}:
                first_action = bat
        except Exception as exc:
            print(f"  {stage:20s} INVALID: {exc}  [{bat}]")
            if first_action is None:
                first_action = bat
    if first_action:
        print(f"\nSuggested next command: {first_action}")
    print("\nModels")
    for path in sorted(MODELS_ROOT.glob("*")):
        if path.is_file() and not path.name.startswith("."):
            print(f"  {path.name}: {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
