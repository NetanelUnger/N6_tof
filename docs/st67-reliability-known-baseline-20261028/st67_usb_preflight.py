"""Bounded read-only CN8 stability check using the project's shared lease protocol."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
import msvcrt
import os
import re
import subprocess
import time

ROOT = Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OWNER = 'n6-xip-st67-reliability-20261028'

def now():
    return datetime.now(timezone.utc).isoformat()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=120)
    ap.add_argument('--output', type=Path, required=True)
    args=ap.parse_args()
    assert 30 <= args.seconds <= 600
    args.output.mkdir(parents=True, exist_ok=False)
    import serial
    from serial.tools import list_ports
    spec=importlib.util.spec_from_file_location('n6_lease', ROOT/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    git=['git','-C',str(ROOT)]  # Existing trusted worktree; no added safe.directory.
    assert subprocess.check_output(git+['branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics'
    marker=folder/'n6-hardware-owner.lock';status=folder/'n6-hardware-owner.json'
    assert not (folder/'n6-hardware-recovery.lock').exists(), 'Lease recovery in progress'
    assert not status.exists() and not marker.exists(), 'Existing hardware owner; no takeover'
    identity=lease.windows_process_identity(os.getpid())
    assert identity['state']=='alive', 'Own process identity unknown'
    owner={'thread':OWNER,'pid':os.getpid(),'started_utc':now(),'process_created_utc':identity['created_utc'],
           'scope':'read-only CN8 version/status and bounded USB stability; no reset, update, settings, or pairing writes'}
    report={'started_utc':now(),'owner':owner,'source_revision':subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip(),
            'requested_seconds':args.seconds,'result':'INCOMPLETE','commands':[],'pings':[], 'enumerations':[],
            'hardware_handles_closed':False,'lease_released':False,'firmware_bytes_sent':0,'resets_sent':0}
    lock=port=None;status_owned=False
    def enumerate_app():
        found=[{'device':p.device,'vid':p.vid,'pid':p.pid,'serial':p.serial_number} for p in list_ports.comports()]
        report['enumerations'].append({'utc':now(),'ports':found})
        app=[p for p in found if p['vid']==0x0483 and p['pid']==0x5740 and p['serial']=='N6TOF001']
        assert len(app)==1, 'Exact CN8 identity absent or ambiguous; no reconnect/reset attempt'
        return app[0]['device']
    def command(line, timeout=5):
        start=time.monotonic(); port.write((line+'\r').encode('ascii'));port.flush()
        data=bytearray()
        while time.monotonic()-start < timeout:
            data.extend(port.read(8192))
            if len(data)>65536: raise RuntimeError('Unbounded CLI response')
            if data.endswith(b'n6> '):
                text=data.decode('utf-8','replace')
                report['commands'].append({'utc':now(),'command':line,'latency_ms':round((time.monotonic()-start)*1000,3),'response':text})
                return text
        report['commands'].append({'utc':now(),'command':line,'partial':data.decode('utf-8','replace')})
        raise TimeoutError('Incomplete CLI response: '+line)
    try:
        lock=marker.open('x+b');lock.write(b'1');lock.flush();lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with status.open('x',encoding='utf-8') as f:json.dump(owner,f,indent=2)
        status_owned=True
        (args.output/'owner-start.json').write_text(json.dumps(owner,indent=2)+'\n')
        name=enumerate_app()
        port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=2)
        port.dtr=True;port.rts=False;port.port=name;port.open()
        time.sleep(.4)
        startup=bytearray(); deadline=time.monotonic()+1
        while time.monotonic()<deadline: startup.extend(port.read(8192))
        report['open_output']=startup.decode('utf-8','replace')
        for line in ('version','status','radio info','radio status','ble status','tof status','rps status','cloud status','dataset stream status'):
            command(line)
        version=report['commands'][0]['response']
        m=re.search(r'Firmware version:\s*(\d+)',version);assert m, 'Live version missing'
        report['running_version']=int(m[1])
        print(json.dumps({'phase':'identity_read','version':int(m[1]),'port':name,'utc':now()}),flush=True)
        begin=time.monotonic();last_progress=begin;previous_uptime=None
        while time.monotonic()-begin<args.seconds:
            assert enumerate_app()==name, 'CN8 identity/port changed'
            token=f'ST67P0-{len(report["pings"]):04d}'
            response=command('debug ping '+token,3)
            assert response.count('PONG '+token+' ')==1, 'Missing/duplicate PONG'
            m=re.search(r'PONG '+re.escape(token)+r'\s+(\d+)',response)
            assert m,'PONG uptime missing'
            uptime=int(m[1])
            assert previous_uptime is None or uptime>=previous_uptime, 'MCU uptime regressed; possible reset'
            previous_uptime=uptime
            report['pings'].append({'uptime_ms':uptime,'latency_ms':report['commands'][-1]['latency_ms']})
            if time.monotonic()-last_progress>=30:
                print(json.dumps({'phase':'stability','elapsed_s':round(time.monotonic()-begin,2),'pings':len(report['pings'])}),flush=True)
                last_progress=time.monotonic()
            time.sleep(min(2,max(0,args.seconds-(time.monotonic()-begin))))
        report['elapsed_s']=time.monotonic()-begin
        for line in ('version','radio status','tof status','rps status','cloud status'):
            command(line)
        versions=[re.search(r'Firmware version:\s*(\d+)',r['response']).group(1) for r in report['commands'] if r['command']=='version']
        assert len(set(versions))==1, 'Version changed during probe'
        values=sorted(p['latency_ms'] for p in report['pings'])
        report['latency_ms']={k:values[math.ceil(len(values)*q)-1] for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]}
        report['result']='PASS'
    except BaseException as exc:
        report['result']='FAIL';report['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        if port is not None:port.close()
        report['hardware_handles_closed']=port is None or not port.is_open
        if lock is not None:
            lock.close()
            if status_owned and status.exists() and json.loads(status.read_text())==owner:
                marker.unlink();status.unlink();report['lease_released']=True
        report['finished_utc']=now()
        (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k in ('result','failure','running_version','elapsed_s','latency_ms','hardware_handles_closed','lease_released','finished_utc')}),flush=True)

if __name__=='__main__':main()
