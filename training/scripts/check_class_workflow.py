import json
from pathlib import Path
import subprocess
import sys

training = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(training / "scripts"))
from test_label_service import Labels

case = Labels("test_rename_merge_delete_and_split_preserve_identity_and_data")
case.setUp()
report = training / "reports/class_workflow/m2-ui.json"
report.parent.mkdir(parents=True, exist_ok=True)
try:
    command = ["cmd.exe", "/d", "/c", str(training / "00_PROJECT.bat"), "--class-ui-smoke",
        "--training-root", str(case.projects.training), "--id", "fixture", "--report", str(report)]
    result = subprocess.run(command, cwd=training, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=40)
    (report.parent / "m2-ui.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout + result.stderr)
    assert result.returncode == 0
    case.assert_originals()
    print("M2 BAT-launched class UI + raw sensor/metadata byte preservation: PASS")
finally:
    case.tearDown()
