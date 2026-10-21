"""Run BAT and Tk checks, keeping separate service/UI evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

training = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(training / "scripts"))
from project_context import atomic, ProjectService, resolve_context
from test_project_context import fixture

report_root = training / "reports/project_workflow"
report_root.mkdir(parents=True, exist_ok=True)
results = []


def run(name, command, *, expected=0, timeout=45):
    start = time.monotonic()
    completed = subprocess.run(command, cwd=training, text=True, encoding="utf-8", errors="replace",
                               capture_output=True, timeout=timeout)
    (report_root / f"{name}.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    value = {"check": name, "result": "PASS" if completed.returncode == expected else "FAIL",
             "exit_code": completed.returncode, "expected_exit_code": expected,
             "duration_seconds": round(time.monotonic() - start, 3)}
    results.append(value)
    print(json.dumps(value), flush=True)
    if completed.returncode != expected:
        raise RuntimeError(f"{name}: see retained output in {report_root}")


bat = lambda name, *args: ["cmd.exe", "/d", "/c", str(training / name), *args]
python = str(training / ".venv/Scripts/python.exe")
run("service", [python, "-B", str(training / "scripts/test_project_context.py"), "-v"])
with tempfile.TemporaryDirectory(prefix="n6-m1-ui-") as temp:
    root = fixture(Path(temp) / "training")
    run("ui_bat", bat("00_PROJECT.bat", "--ui-smoke", "--training-root", str(root),
                      "--report", str(report_root / "ui.json")))
    ui = json.loads((report_root / "ui.json").read_text(encoding="utf-8"))
    assert ui["result"] == "PASS"
    run("unicode_cli_bat", bat("00_PROJECT.bat", "--non-interactive", "--training-root", str(root),
                              "--action", "create", "--id", "unicode-check", "--name", "בדיקה 🧪"))
run("unattended_missing_input", bat("00_PROJECT.bat", "--non-interactive"), expected=2)
service = ProjectService(training)
service.recover()
if not (service.root / "m1-workflow-check").exists():
    service.create("m1-workflow-check", "M1 isolated BAT smoke", select=False)
run("status_bat_isolated", bat("99_STATUS_RESUME.bat", "--project", "m1-workflow-check", "--non-interactive"))
run("legacy_self_test", [python, "-B", str(training / "scripts/self_test.py")])
atomic(report_root / "m1.json", {"schema": 1, "checks": results,
       "result": "PASS", "scope": "M1 service, Tk widget automation through BAT, and isolated status BAT; no HIL.",
       "ui_limit": "No independent screenshot/pixel/native-input verification.",
       "firmware_modified": False})
