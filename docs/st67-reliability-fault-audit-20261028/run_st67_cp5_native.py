"""Independent native fault/ownership regressions; no board or network access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, sys

ROOT = Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT = Path(__file__).resolve().parent / 'evidence/st67-cp5-20261028'
OUT.mkdir(exist_ok=True)
NAMES = (
    'test_spi_fault_snapshot.py', 'test_radio_spi_shutdown.py',
    'test_spi_fs_framing.py', 'test_spi_flow_probe.py',
    'test_notify_transaction.py', 'test_raw_send_response.py',
    'test_radio_modem_shutdown.py', 'test_radio_coordinated_recovery.py',
    'test_ble_control_worker.py', 'test_wifi_scan_admission.py',
    'test_cloud_send_slices.py', 'test_cloud_request_budget.py',
    'test_radio_service_status.py', 'test_xip_rx_backpressure.py',
)
summary = OUT / 'native-tests.json'
assert not summary.exists(), 'Preserve the earlier run; use a new run ID.'
results = []
for name in NAMES:
    source = ROOT / 'hil_tests' / name
    command = [sys.executable, '-B', str(source)]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=120)
    (OUT / (name + '.log')).write_text(result.stdout + '\nSTDERR:\n' + result.stderr,
                                      encoding='utf-8')
    row = dict(test=name, command=command, started_utc=started,
               finished_utc=datetime.now(timezone.utc).isoformat(),
               sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
               exit_code=result.returncode, result='PASS' if result.returncode == 0 else 'FAIL',
               pass_lines=[x for x in result.stdout.splitlines() if x.startswith('PASS')])
    results.append(row)
    print(json.dumps(row), flush=True)
    summary.write_text(json.dumps(dict(scope='Actual-C host regressions with mocked hardware boundaries; no HIL',
        source_revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        tests=results), indent=2) + '\n', encoding='utf-8')
sys.exit(0 if all(row['exit_code'] == 0 for row in results) else 1)
