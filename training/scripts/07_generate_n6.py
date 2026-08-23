"""Stage 07: compile the quantized model for STM32N6 Neural-ART (NPU)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess

from common import (CONFIG_ROOT, GENERATED_ROOT, MODELS_ROOT, atomic_json,
                    find_executable, load_json, mark_stage, relative,
                    sha256_file, stable_hash, stage_state, utc_now)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    model = MODELS_ROOT / "rps_int8.tflite"
    if not model.exists():
        raise RuntimeError("Run 06_QUANTIZE.bat first.")
    tools = load_json(CONFIG_ROOT / "tools.json")
    executable = find_executable(tools["stedgeai_executable"],
                                 tools["stedgeai_env"])
    if not executable:
        raise RuntimeError(
            "STEdgeAI Core CLI was not found. Install STM32Cube.AI / STEdgeAI "
            "Core, then set STEDGEAI_PATH to stedgeai.exe or its directory. "
            "This stage refuses to substitute a CPU-only model because the "
            "deployment target is the STM32N6 Neural-ART NPU."
        )
    output = GENERATED_ROOT / "st_ai_output"
    network_name = tools["network_name"]
    fingerprint = stable_hash({"model": sha256_file(model),
                               "tool": str(executable),
                               "target": tools["stm32_target"],
                               "network_name": network_name})
    prior = stage_state("07_generate_n6")
    prior_manifest = GENERATED_ROOT / "generation_manifest.json"
    if (not args.force and prior.get("status") == "complete" and
            prior.get("input_fingerprint") == fingerprint and
            prior_manifest.exists() and
            all((GENERATED_ROOT.parent / path).exists()
                for path in prior.get("outputs", []))):
        print("Neural-ART output is current; reusing it. Pass --force to regenerate.")
        return 0
    if args.force and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable), "generate", "-m", str(model),
               "--target", tools["stm32_target"], "--st-neural-art",
               "-n", network_name, "-o", str(output)]
    print("\nExecuting the vendor compiler:\n  " + subprocess.list2cmdline(command))
    completed = subprocess.run(command, cwd=GENERATED_ROOT, check=False)
    if completed.returncode:
        raise RuntimeError(f"stedgeai failed with exit code {completed.returncode}")
    required = [output / f"{network_name}.c", output / f"{network_name}.h",
                output / f"stai_{network_name}.c",
                output / f"stai_{network_name}.h"]
    missing = [str(path) for path in required if not path.exists()]
    weights = sorted(output.glob(f"{network_name}_atonbuf.*.raw"))
    epoch_blobs = sorted(output.glob(f"{network_name}_ecblobs*"))
    if missing or not weights:
        raise RuntimeError(
            "Neural-ART output is incomplete. Missing: " +
            ", ".join(missing +
                      ([f"{network_name}_atonbuf.*.raw"] if not weights else []))
        )
    network_text = (output / f"{network_name}.c").read_text(
        encoding="utf-8", errors="replace"
    )
    if "LL_ATON" not in network_text and "ll_aton" not in network_text.lower():
        raise RuntimeError("Generated network.c does not appear to target Neural-ART")
    manifest = {
        "schema": 1, "created_utc": utc_now(),
        "stedgeai": str(executable), "command": command,
        "network_name": network_name,
        "input_model_sha256": sha256_file(model),
        "generated_files": [
            {"path": relative(path), "size": path.stat().st_size,
             "sha256": sha256_file(path)}
            for path in required + weights + epoch_blobs
        ],
        "weights_are_separate": True,
        "note": "Stage 08 embeds Neural-ART constants in the signed app for atomic A/B rollback.",
    }
    manifest_path = GENERATED_ROOT / "generation_manifest.json"
    atomic_json(manifest_path, manifest)
    mark_stage("07_generate_n6", status="complete",
               inputs=fingerprint,
               outputs=[relative(path) for path in
                        required + weights + epoch_blobs + [manifest_path]],
               details={"weights": len(weights),
                        "epoch_blobs": len(epoch_blobs)})
    print(f"Neural-ART generation complete; {len(weights)} weight blob(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
