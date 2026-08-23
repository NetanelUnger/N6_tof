"""One-time signed SWD installation of the Secure Neural-ART bootstrap."""

from __future__ import annotations

import argparse
import re

from common import (PROJECT_ROOT, mark_stage, npu_deployment_fingerprint,
                    run, sha256_file)


def current_version() -> int:
    header = (PROJECT_ROOT / "Common" / "Update" /
              "firmware_build_version.h").read_text(encoding="utf-8")
    match = re.search(r"NATI_LAB_FIRMWARE_VERSION\s+\((\d+)UL\)", header)
    if not match:
        raise RuntimeError("Cannot read current firmware version")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-only", action="store_true",
        help="build/sign the complete chain but do not program the board",
    )
    args = parser.parse_args()
    fingerprint = npu_deployment_fingerprint()
    powershell = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                  "-File"]
    version = current_version()
    run(powershell + [str(PROJECT_ROOT / "Tools" / "build_and_sign.ps1"),
                      "-FirmwareVersion", str(version)], cwd=PROJECT_ROOT)
    if args.build_only:
        print("Secure/Non-Secure NPU images were built and signed; board unchanged.")
        return 0

    confirmation = input(
        "This one-time operation writes only FSBL + Secure through SWD and "
        "preserves both application slots. Set BOOT0=1-2, BOOT1=2-3, press "
        "RESET, then type BOOTCHAIN: "
    ).strip()
    if confirmation != "BOOTCHAIN":
        print("Cancelled; the signed artifacts remain available and the board was not changed.")
        return 2
    run(powershell + [str(PROJECT_ROOT / "Tools" / "program_flash.ps1"),
                      "-BootChainOnly"], cwd=PROJECT_ROOT)
    secure_image = PROJECT_ROOT / "FlashImages" / "N6_AppliSecure-trusted.bin"
    mark_stage(
        "08_secure_bootstrap",
        status="complete",
        inputs=fingerprint,
        outputs=[str(secure_image)],
        details={
            "firmware_version_preserved": version,
            "secure_image_sha256": sha256_file(secure_image),
            "application_slots_preserved": True,
        },
    )
    print("Secure Neural-ART bootstrap installed. Return BOOT0/BOOT1 to 1-2 and reset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
