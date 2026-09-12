"""Stage 10: call the project's proven RAM or signed XMODEM deployment lane."""

from __future__ import annotations

import argparse
import re

from common import (PROJECT_ROOT, mark_stage, npu_deployment_fingerprint, run,
                    stage_state)


def current_version() -> int:
    header = (PROJECT_ROOT / "Common" / "Update" /
              "firmware_build_version.h").read_text(encoding="utf-8")
    match = re.search(r"NATI_LAB_FIRMWARE_VERSION\s+\((\d+)UL\)", header)
    if not match:
        raise RuntimeError("Cannot read current firmware version")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--ram", action="store_true")
    modes.add_argument("--flash", action="store_true")
    parser.add_argument("--version", type=int)
    parser.add_argument("--port")
    parser.add_argument("--skip-boot-verification", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    if args.ram and args.package_only:
        raise RuntimeError("--package-only is valid only with --flash.")
    fingerprint = npu_deployment_fingerprint()
    integration = stage_state("08_integrate")
    if integration.get("status") != "complete":
        raise RuntimeError("Run 08_INTEGRATE_MODEL.bat before building firmware.")
    powershell = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                  "-File"]
    if args.ram:
        command = powershell + [str(PROJECT_ROOT / "Tools" /
                                    "Debug-NonSecureRam.ps1"), "-Run"]
        run(command, cwd=PROJECT_ROOT)
        mark_stage("10_ram", status="complete", inputs=fingerprint,
                   details={"external_flash_modified": False})
        return 0
    if not args.package_only:
        bootstrap = stage_state("09_secure_bootstrap")
        if bootstrap.get("status") != "complete":
            # Accept state written by releases that used the old 08B filename.
            bootstrap = stage_state("08_secure_bootstrap")
        if bootstrap.get("status") != "complete":
            raise RuntimeError(
                "The one-time persistent FSBL + Secure Neural-ART bootstrap "
                "has not been installed/recorded. The RAM image and CN8 CDC "
                "can be healthy while this prerequisite is still missing. "
                "Run 09_BOOTSTRAP_NPU_SWD.bat once; it preserves both "
                "Non-Secure A/B slots and asks for BOOTCHAIN before SWD writes."
            )
        hil = stage_state("11_hil")
        if hil.get("status") != "complete":
            # Accept a matching PASS written before the stages were renumbered.
            hil = stage_state("09_hil")
        if (hil.get("status") != "complete" or
                hil.get("input_fingerprint") != fingerprint):
            raise RuntimeError(
                "Run 10_LOAD_RAM.bat and then 11_HIL.bat successfully for this "
                "exact integrated model before persistent installation."
            )
    expected = current_version() + 1
    version = args.version
    if version is None:
        entered = input(f"New persistent firmware version [{expected}]: ").strip()
        version = int(entered) if entered else expected
    if version != expected:
        raise RuntimeError(
            f"Safe release lane requires current+1, which is {expected}; got {version}."
        )
    if not args.package_only:
        confirmation = input(
            f"This will sign v{version}, send .n6fw over CN8/XMODEM and reset. "
            "Type FLASH to continue: "
        ).strip()
        if confirmation != "FLASH":
            print("Cancelled; no firmware or version file was changed.")
            return 2
    command = powershell + [str(PROJECT_ROOT / "Tools" /
                                "Install-NonSecureUpdate.ps1"),
                            "-FirmwareVersion", str(version)]
    if args.port:
        command += ["-Port", args.port]
    if args.skip_boot_verification:
        command.append("-SkipBootVerification")
    if args.package_only:
        command.append("-PackageOnly")
    run(command, cwd=PROJECT_ROOT)
    stage = "12_package" if args.package_only else "12_flash"
    mark_stage(stage, status="complete", inputs=fingerprint,
               details={"firmware_version": version,
                        "board_modified": not args.package_only})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
