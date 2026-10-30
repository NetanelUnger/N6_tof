from pathlib import Path
from datetime import datetime,timezone
import subprocess,sys,json,hashlib

ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=Path(__file__).resolve().parent/'evidence/st67-cp2-20261028'
OUT.mkdir(exist_ok=True)
names=['test_wifi_assoc_admission.py','test_ble_recovery_barrier.py',
       'test_cloud_socket_recovery.py','test_wifi_link_restore.py',
       'test_ble_recovery_notice.py','test_cloud_radio_barrier.py']
results=[]
for name in names:
    p=ROOT/'hil_tests'/name
    start=datetime.now(timezone.utc).isoformat()
    command=[sys.executable,'-B',str(p)]
    done=subprocess.run(command,cwd=ROOT,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=120)
    log=done.stdout+'\nSTDERR:\n'+done.stderr
    (OUT/(name+'.log')).write_text(log,encoding='utf-8')
    result={'test':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'command':command,
        'started_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),
        'exit_code':done.returncode,'pass_lines':[line for line in done.stdout.splitlines() if line.startswith('PASS')],
        'result':'PASS' if done.returncode==0 else 'FAIL'}
    results.append(result);print(json.dumps(result),flush=True)
    if done.returncode:break
(OUT/'native-tests.json').write_text(json.dumps({'scope':'Host actual-C with mocked boundaries; no HIL or firmware writes',
    'source_revision':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
    'tests':results},indent=2)+'\n',encoding='utf-8')
sys.exit(0 if len(results)==len(names) and all(x['exit_code']==0 for x in results) else 1)
