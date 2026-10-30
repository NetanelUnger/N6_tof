"""Lease and cleanup wrapper for the existing exact-tensor/NPU USB HIL100 test."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,msvcrt,os,subprocess,sys,time
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
from n6_hardware_lease import windows_process_identity
from run_xip_usb_reject import status as cli
import serial
def main():
    out=Path(__file__).parent/'evidence/st67-cp4-20261028';out.mkdir(exist_ok=True)
    result_path=out/'image120-v2-wrapper.json';assert not result_path.exists()
    install=json.loads((Path(__file__).parent/'evidence/st67-cp3-20261028/install52/result.json').read_text());assert install['result']=='PASS'
    common=Path(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';owner_path=folder/'n6-hardware-owner.json'
    assert not any(p.exists() for p in (marker,owner_path,folder/'n6-hardware-recovery.lock'))
    identity=windows_process_identity(os.getpid());assert identity['state']=='alive'
    owner={'thread':'n6-xip-st67-reliability-20261028','pid':os.getpid(),'started_utc':datetime.now(timezone.utc).isoformat(),'process_created_utc':identity['created_utc'],'scope':'B52 BLE image/NPU/CLI120s with existing Wi-Fi/Cloud; restore map off; no reset/firmware/pair/settings writes'}
    r={'owner':owner,'result':'INCOMPLETE','handles_closed':False,'lease_released':False};lock=port=child=None;owned=False
    def openusb():
        p=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);p.dtr=True;p.rts=False;p.port='COM8';p.open();time.sleep(.3);return p
    try:
        lock=marker.open('x+b');lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with owner_path.open('x') as f:json.dump(owner,f,indent=2)
        owned=True;port=openusb()
        r['before']={c:cli(port,c) for c in ('version','tof status','dataset stream status','rps status','cloud status')}
        assert 'Firmware version: 52\r\n' in r['before']['version']
        assert 'requested NONE, active NONE' in r['before']['tof status'] and 'Dataset stream: off' in r['before']['dataset stream status']
        port.close();port=None
        cmd=[str(ROOT.parent/'project/training/.venv/Scripts/python.exe'),'-B','-u',str(Path(__file__).parent/'st67_image52.py'),
             '--owner-thread',owner['thread'],'--label','st67-baseline52-images-v2','--duration','120']
        r['command']=cmd;os.environ['PYTHONPATH']=str(ROOT/'hil_tests')
        with (out/'image120-v2.log').open('x') as log:
            child=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
            r['child_pid']=child.pid
            while child.poll() is None:time.sleep(.5)
        r['exit_code']=child.returncode
        artifact=ROOT/'.local-dependencies/diagnostics/st67-baseline52-images-v2/report.json'
        if artifact.exists():r['profile']=json.loads(artifact.read_text())
        port=openusb();
        if r.get('profile',{}).get('map_on_requested'):r['map_off_cleanup']=cli(port,'MAP OFF')
        r['after']={c:cli(port,c) for c in ('version','tof status','dataset stream status','rps status','radio status','cloud status')}
        assert child.returncode==0 and r['profile']['passed']
        assert 'Dataset stream: off' in r['after']['dataset stream status'] and 'requested NONE, active NONE' in r['after']['tof status']
        assert 'ToF state: ready' in r['after']['tof status'] and 'errors=0' in r['after']['rps status']
        r['result']='PASS'
    except BaseException as e:r['failure']=repr(e);r['result']='FAIL';raise
    finally:
        while child is not None and child.poll() is None:time.sleep(.5)
        if port is not None:port.close()
        r['handles_closed']=port is None or not port.is_open
        if lock is not None:
            lock.close()
            if owned and owner_path.exists() and json.loads(owner_path.read_text())==owner:marker.unlink();owner_path.unlink();r['lease_released']=True
        r['finished_utc']=datetime.now(timezone.utc).isoformat();result_path.write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r.get(k) for k in ('result','failure','exit_code','handles_closed','lease_released')}),flush=True)
        if 'profile' in r:print(json.dumps({k:r['profile'].get(k) for k in ('soak_counts','latency_ms','image_crc_errors','image_drops_during_soak','max_result_receive_gap_s','max_image_receive_gap_s','max_event_loop_lag_s','elapsed_s','passed','failure')}),flush=True)
if __name__=='__main__':main()
