"""Stage 00: verify the isolated Python environment and create directories."""

from __future__ import annotations

import argparse
import sys

from common import REPORTS_ROOT, atomic_json, environment_report, mark_stage, utc_now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(
            f"This project pins Python 3.11; running {sys.version.split()[0]}. "
            "Launch training\\00_SETUP.bat first."
        )
    report = environment_report()
    report["checked_utc"] = utc_now()
    report_path = REPORTS_ROOT / "environment.json"
    atomic_json(report_path, report)
    required = ("numpy", "PIL", "serial", "yaml", "bleak")
    missing = [name for name in required
               if str(report["modules"][name]).startswith("missing")]
    if missing:
        raise RuntimeError(f"Missing Python packages: {', '.join(missing)}")
    mark_stage("00_setup", status="complete", outputs=[str(report_path)],
               details=report)
    print("Python environment is ready.")
    print(f"STEdgeAI: {report['stedgeai'] or 'not installed yet (needed at stage 07)'}")
    if args.check_only:
        print("Check-only mode: no packages or firmware were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

