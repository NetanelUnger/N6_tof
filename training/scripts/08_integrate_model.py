"""Stage 08: install a signed, atomic Neural-ART model into the firmware tree."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from common import (CONFIG_ROOT, GENERATED_ROOT, MODELS_ROOT, PROJECT_ROOT,
                    atomic_json, find_executable, load_json, mark_stage,
                    relative, sha256_file, stable_hash, utc_now)


RUNTIME_SOURCES = (
    "ll_aton.c",
    "ll_aton_cipher.c",
    "ll_aton_lib.c",
    "ll_aton_lib_sw_operators.c",
    "ll_aton_osal_threadx.c",
    "ll_aton_rt_main.c",
    "ll_aton_runtime.c",
    "ll_aton_stai_internal.c",
    "ll_aton_util.c",
    "ll_sw_float.c",
    "ll_sw_integer.c",
)

WEIGHTS_NPU_RAM_BASE = 0x24350000
WEIGHTS_NPU_RAM_CAPACITY = 448 * 1024
NPU_SRAM3_BASE = 0x24200000
NPU_SRAM3_END = 0x24270000


def copy_file(source: Path, target: Path, installed: list[Path]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    installed.append(target)


def write_weights_c(blob: bytes, model_dir: Path, installed: list[Path]) -> None:
    header = model_dir / "rps_model_weights.h"
    source = model_dir / "rps_model_weights.c"
    header.write_text(
        "#ifndef RPS_MODEL_WEIGHTS_H\n"
        "#define RPS_MODEL_WEIGHTS_H\n\n"
        "#include <stddef.h>\n"
        "#include <stdint.h>\n\n"
        f"#define RPS_MODEL_WEIGHTS_SIZE ({len(blob)}UL)\n"
        f"#define RPS_MODEL_WEIGHTS_NPU_ADDRESS (0x{WEIGHTS_NPU_RAM_BASE:08X}UL)\n\n"
        "extern const uint8_t rps_model_weights[RPS_MODEL_WEIGHTS_SIZE];\n\n"
        "#endif /* RPS_MODEL_WEIGHTS_H */\n",
        encoding="utf-8",
    )
    lines = []
    for offset in range(0, len(blob), 16):
        chunk = ", ".join(f"0x{value:02X}" for value in blob[offset:offset + 16])
        lines.append(f"  {chunk},")
    source.write_text(
        "#include \"rps_model_weights.h\"\n\n"
        "/* Generated from STEdgeAI's raw initializer.  Keeping this const array\n"
        " * inside the Non-Secure image makes code and weights one signed A/B unit. */\n"
        "const uint8_t rps_model_weights[RPS_MODEL_WEIGHTS_SIZE] "
        "__attribute__((aligned(64), used)) =\n{\n"
        + "\n".join(lines)
        + "\n};\n",
        encoding="utf-8",
    )
    installed.extend((header, source))


def patch_network_for_nonsecure_sram(text: str) -> str:
    # The default STM32N6 descriptor emits Secure aliases (0x34xxxxxx).  This
    # application executes in Non-Secure state, whose AXI SRAM aliases are
    # 0x24xxxxxx.  ST's SNS reference project uses the same aliases.
    text = re.sub(r"0x34([0-9A-Fa-f]{6})", r"0x24\1", text)
    text = re.sub(r"0x71000000", f"0x{WEIGHTS_NPU_RAM_BASE:08X}",
                  text, flags=re.IGNORECASE)
    # STEdgeAI places initializer blobs in the cacheable xSPI2 pool by
    # default.  Merely relocating the addresses to SRAM6 is insufficient:
    # the generated DMA descriptors would still select the xSPI/cache BUSIF
    # path and Neural-ART raises a BUSIF1 fault on its first weight fetch.
    # All cacheable DMA descriptors in this generated network belong to that
    # one initializer pool; SRAM6 is an NPU-local, non-cacheable memory pool.
    text = re.sub(r"(\.cacheable\s*=\s*)1(\s*,)", r"\g<1>0\2", text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.parse_args()

    generated = GENERATED_ROOT / "st_ai_output"
    generation_manifest = GENERATED_ROOT / "generation_manifest.json"
    contract_path = MODELS_ROOT / "model_contract.json"
    if not generation_manifest.exists() or not contract_path.exists():
        raise RuntimeError("Run 06_QUANTIZE.bat and 07_GENERATE_N6.bat first.")

    generation = load_json(generation_manifest)
    contract = load_json(contract_path)
    training_config = load_json(CONFIG_ROOT / "training.json")
    network_name = generation.get("network_name", "rps_tof")
    generated_model_files = (
        generated / f"{network_name}.c",
        generated / f"{network_name}.h",
        generated / f"stai_{network_name}.c",
        generated / f"stai_{network_name}.h",
    )
    weights = sorted(generated.glob(f"{network_name}_atonbuf.*.raw"))
    if any(not path.exists() for path in generated_model_files):
        raise RuntimeError("Generated Neural-ART C files are incomplete.")
    if len(weights) != 1 or ".xSPI2." not in weights[0].name:
        raise RuntimeError(
            "This integration expects exactly one xSPI2 raw weight initializer; "
            f"found {[path.name for path in weights]}."
        )
    if weights[0].stat().st_size > WEIGHTS_NPU_RAM_CAPACITY:
        raise RuntimeError(
            f"Weights need {weights[0].stat().st_size} bytes, but NPU SRAM6 has "
            f"only {WEIGHTS_NPU_RAM_CAPACITY}."
        )
    firmware_weight_budget = int(
        training_config.get("maximum_embedded_weight_bytes", 64 * 1024)
    )
    if weights[0].stat().st_size > firmware_weight_budget:
        raise RuntimeError(
            f"Generated weights need {weights[0].stat().st_size} bytes, but the "
            f"firmware integration budget is {firmware_weight_budget}. Larger "
            "embedded weights reduce the Non-Secure C heap required by the "
            "VL53L9 transform. Reduce the model and rerun stages 05-08."
        )

    tools = load_json(CONFIG_ROOT / "tools.json")
    executable = find_executable(tools["stedgeai_executable"],
                                 tools["stedgeai_env"])
    if executable is None:
        raise RuntimeError("STEdgeAI is required so its matching runtime can be installed.")
    st_root = Path(executable).resolve().parents[2]
    ai_root = st_root / "Middlewares" / "ST" / "AI"
    ll_aton = ai_root / "Npu" / "ll_aton"
    device = ai_root / "Npu" / "Devices" / "STM32N6xx"
    runtime_library = (ai_root / "Lib" / "GCC" / "ARMCortexM55" /
                       "NetworkRuntime1201_CM55_GCC.a")
    required_vendor = [runtime_library]
    required_vendor.extend(ll_aton / name for name in RUNTIME_SOURCES)
    required_vendor.append(ll_aton / "ll_aton_osal_rtos_template.c")
    required_vendor.extend((device / "mcu_cache.c", device / "npu_cache.c"))
    missing_vendor = [str(path) for path in required_vendor if not path.exists()]
    if missing_vendor:
        raise RuntimeError("Matching STEdgeAI runtime is incomplete: " +
                           ", ".join(missing_vendor))

    fingerprint = stable_hash({
        "generation": generation,
        "contract": contract,
        "stedgeai": str(executable),
        "runtime_library": sha256_file(runtime_library),
        "integration_schema": 3,
        "firmware_weight_budget": firmware_weight_budget,
    })

    firmware_ai = PROJECT_ROOT / "AppliNonSecure" / "AI"
    model_dir = firmware_ai / "Model"
    runtime_dir = firmware_ai / "Runtime"
    include_dir = firmware_ai / "Inc"
    device_dir = firmware_ai / "Device"
    library_dir = firmware_ai / "Lib"
    installed: list[Path] = []

    model_dir.mkdir(parents=True, exist_ok=True)
    network_source = generated_model_files[0].read_text(
        encoding="utf-8", errors="strict"
    )
    patched_network = patch_network_for_nonsecure_sram(network_source)
    if re.search(r"0x34[0-9A-Fa-f]{6}", patched_network):
        raise RuntimeError("A Secure NPU SRAM alias remains in generated network.c.")
    if re.search(r"0x71000000", patched_network, flags=re.IGNORECASE):
        raise RuntimeError("The generated network still references external xSPI2 weights.")
    if re.search(r"\.cacheable\s*=\s*1\s*,", patched_network):
        raise RuntimeError(
            "A cacheable xSPI DMA descriptor remains after relocating weights "
            "to non-cacheable NPU SRAM6."
        )
    network_code = re.sub(r"/\*.*?\*/", "", patched_network,
                          flags=re.DOTALL)
    network_code = re.sub(r"//.*", "", network_code)
    generated_addresses = {
        int(value, 16)
        for value in re.findall(r"0x([0-9A-Fa-f]{8})", network_code)
    }
    if any(NPU_SRAM3_BASE <= address < NPU_SRAM3_END
           for address in generated_addresses):
        raise RuntimeError(
            "The generated network uses NPU SRAM3, which this firmware reserves "
            "for USB CDC and preprocessing workspaces. Regenerate with activations "
            "in SRAM4/5 or revise the linker reservation deliberately."
        )
    network_target = model_dir / generated_model_files[0].name
    network_target.write_text(patched_network, encoding="utf-8")
    installed.append(network_target)
    for source in generated_model_files[1:]:
        copy_file(source, model_dir / source.name, installed)
    write_weights_c(weights[0].read_bytes(), model_dir, installed)

    # Headers are copied as a matched SDK snapshot.  Only the small, explicit
    # source list below is compiled, keeping incremental rebuilds quick.
    for source in sorted((ai_root / "Inc").glob("*.h")):
        copy_file(source, include_dir / source.name, installed)
    for source in sorted(ll_aton.glob("*.h")):
        copy_file(source, runtime_dir / source.name, installed)
    for name in RUNTIME_SOURCES:
        copy_file(ll_aton / name, runtime_dir / name, installed)
    # The ThreadX adapter textually includes this implementation template.  It
    # must not keep a .c extension in the Eclipse source tree, otherwise the
    # managed builder also compiles it as an invalid standalone translation
    # unit.
    template_source = ll_aton / "ll_aton_osal_rtos_template.c"
    template_target = runtime_dir / "ll_aton_osal_rtos_template.inc"
    copy_file(template_source, template_target, installed)
    threadx_target = runtime_dir / "ll_aton_osal_threadx.c"
    threadx_text = threadx_target.read_text(encoding="utf-8")
    threadx_target.write_text(
        threadx_text.replace('"ll_aton_osal_rtos_template.c"',
                             '"ll_aton_osal_rtos_template.inc"'),
        encoding="utf-8",
    )
    stale_template = runtime_dir / "ll_aton_osal_rtos_template.c"
    if stale_template.exists():
        stale_template.unlink()
    for source in sorted(device.glob("*.h")):
        copy_file(source, device_dir / source.name, installed)
    for name in ("mcu_cache.c", "npu_cache.c"):
        copy_file(device / name, device_dir / name, installed)
    npu_cache_target = device_dir / "npu_cache.c"
    npu_cache_text = npu_cache_target.read_text(encoding="utf-8")
    npu_cache_target.write_text(
        npu_cache_text.replace(
            "#define USE_HAL_DRIVER  // Define here to fix header issues, must clean projects using only stm32n6xx.h for application code",
            "#ifndef USE_HAL_DRIVER\n#define USE_HAL_DRIVER\n#endif /* USE_HAL_DRIVER */",
        ),
        encoding="utf-8",
    )
    copy_file(runtime_library, library_dir / runtime_library.name, installed)
    for license_name in ("LICENSE.txt", "APACHE-2.0.txt"):
        license_path = ai_root / license_name
        if license_path.exists():
            copy_file(license_path, firmware_ai / license_name, installed)

    manifest = {
        "schema": 3,
        "created_utc": utc_now(),
        "network_name": network_name,
        "model_contract_sha256": sha256_file(contract_path),
        "weights": {
            "source": relative(weights[0]),
            "size": weights[0].stat().st_size,
            "sha256": sha256_file(weights[0]),
            "runtime_address": f"0x{WEIGHTS_NPU_RAM_BASE:08X}",
            "storage": "const array inside signed Non-Secure image",
            "firmware_budget": firmware_weight_budget,
        },
        "atomic_update_contract": {
            "status": "complete",
            "package_format": ".n6fw v1",
            "reason": (
                "The raw initializer is embedded in the signed Non-Secure image "
                "and copied to NPU SRAM6 at runtime, so A/B firmware rollback "
                "also rolls back its exact weights."
            ),
        },
        "stedgeai_root": str(st_root),
        "installed_files": [
            {"path": relative(path), "size": path.stat().st_size,
             "sha256": sha256_file(path)}
            for path in installed
        ],
    }
    manifest_path = GENERATED_ROOT / "firmware_integration" / "integration_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(manifest_path, manifest)
    mark_stage("08_integrate", status="complete", inputs=fingerprint,
               outputs=[relative(manifest_path)] +
                       [relative(path) for path in installed],
               details={"weights_bytes": weights[0].stat().st_size,
                        "installed_files": len(installed),
                        "atomic_update": True})
    print(f"Installed {len(installed)} firmware/runtime files.")
    print(f"Embedded {weights[0].stat().st_size} weight bytes in the signed app image.")
    print("Atomic A/B contract: firmware and its exact weights now roll back together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
