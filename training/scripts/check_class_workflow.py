import json
import os
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
    env = {**os.environ, "N6_TRAINING_CONTEXT_ROOT": str(case.projects.training)}
    continuation = subprocess.run(["cmd.exe", "/d", "/c", str(training / "99_STATUS_RESUME.bat"),
                                   "--project", "fixture", "--non-interactive"], cwd=training,
                                  env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    (report.parent / "m7-continue-bat.log").write_text(continuation.stdout + continuation.stderr, encoding="utf-8")
    assert continuation.returncode == 0, continuation.stderr
    assert "Fixture [fixture]" in continuation.stdout
    ui = json.loads(report.read_text())
    summary = {"status": "PASS", "wizard_select": ui["selection_events"], "label_ui": ui["events"],
               "continued_bat": "99_STATUS_RESUME.bat", "same_project": "fixture", "fixture_only": True,
               "native_pixel_assertions": False, "source_bytes_preserved": True}
    (report.parent / "m7-ui-workflow.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    print("M2 BAT-launched class UI + raw sensor/metadata byte preservation: PASS")
finally:
    case.tearDown()
