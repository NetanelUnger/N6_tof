"""Read confirmed version through existing signed old-header rejection; no image/EOT/reset."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,msvcrt,os,re,subprocess,sys,threading,time
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
from n6_hardware_lease import windows_process_identity
from run_xip_usb_reject import packet,until,status as cli
import serial
from serial.tools import list_ports
def utc():return datetime.now(timezone.utc).isoformat()
def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    package=ROOT/'.local-dependencies/xip/v50-B-timed-demo-map/N6-XIP-B-v50.n6fw'
    data=package.read_bytes();assert hashlib.sha256(data).hexdigest()=='2a7aedb4fcd156f8eafa0bd322116452cf8fbd1f1e4aec7989ed7e84b5d9e156'
    assert int.from_bytes(data[20:24],'little')==50
    frames=[packet(data[:128],sequence=1),packet(data[128:256],sequence=2)]
    assert all(len(x)==133 for x in frames)
    common=Path(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';owner_path=folder/'n6-hardware-owner.json'
    assert not any(x.exists() for x in (marker,owner_path,folder/'n6-hardware-recovery.lock')),'Existing owner'
    identity=windows_process_identity(os.getpid());assert identity['state']=='alive'
    owner={'thread':'n6-xip-st67-reliability-20261028','pid':os.getpid(),'started_utc':utc(),'process_created_utc':identity['created_utc'],
           'scope':'read confirmed version via old signed manifest only; no image bytes, EOT, reset, settings or credential writes'}
    r={'started_utc':utc(),'owner':owner,'result':'INCOMPLETE','expected_running_version':51,'replay_manifest_version':50,
       'manifest_bytes_sent':0,'image_bytes_sent':0,'EOT_sent':False,'reset_sent':False,'handles_closed':False,'lease_released':False}
    lock=uart=port=thread=trace=None;owned=False;raw=False;stop=threading.Event()
    def collect():
        try:
            while not stop.is_set():
                b=uart.read(4096)
                if b:trace.write(b);trace.flush()
        except Exception as e:r['uart_error']=repr(e)
    try:
        lock=marker.open('x+b');lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with owner_path.open('x') as f:json.dump(owner,f,indent=2)
        owned=True
        ports=list(list_ports.comports())
        assert any(p.device=='COM8' and p.vid==0x0483 and p.pid==0x5740 and p.serial_number=='N6TOF001' for p in ports)
        assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
        uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
        trace=(out/'uart.log').open('xb');thread=threading.Thread(target=collect);thread.start()
        port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);port.dtr=True;port.rts=False;port.port='COM8';port.open();time.sleep(.3)
        r['before']={c:cli(port,c) for c in ('version','tof status','rps status','dataset stream status')}
        assert 'Firmware version: 51\r\n' in r['before']['version']
        assert 'requested NONE, active NONE' in r['before']['tof status'] and 'ToF state: ready' in r['before']['tof status']
        assert 'errors=0' in r['before']['rps status'] and 'Dataset stream: off' in r['before']['dataset stream status']
        port.write(b'update\r');port.flush();raw=True
        r['start']=until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C')).decode('ascii','replace');time.sleep(.5)
        port.write(frames[0]);port.flush();r['manifest_bytes_sent']=128
        until(port,lambda b:b'\x06' in b)
        port.write(frames[1]);port.flush();r['manifest_bytes_sent']=256
        reply=until(port,lambda b:b'\x18\x18' in b or b'\x06' in b);r['replay_reply_hex']=reply.hex()
        if b'\x06' in reply:raise RuntimeError('Unexpected old-header acceptance; cancel without image/EOT')
        r['terminal']=until(port,lambda b:b.endswith(b'n6> ')).decode('utf-8','replace');raw=False
        time.sleep(.5);trace.flush();text=(out/'uart.log').read_text(errors='replace')
        matches=re.findall(r'\[SECURE-UPDATE\] confirmed version = 0x([0-9A-Fa-f]+)',text)
        assert len(matches)==1 and int(matches[0],16)==51,'Expected Secure confirmed51 not proven'
        assert 'Begin accepted; session' not in text,'Unexpected update session acceptance'
        r['confirmed_version']=51;r['confirmed_state_proven']=True
        r['after']={c:cli(port,c) for c in ('version','debug ping ST67CONF','tof status','rps status','cloud status')}
        assert 'Firmware version: 51\r\n' in r['after']['version'] and 'PONG ST67CONF ' in r['after']['debug ping ST67CONF']
        assert 'ToF state: ready' in r['after']['tof status'] and 'errors=0' in r['after']['rps status']
        r['slot_and_fallback']='Not exposed by this rejection; unknown, not inferred from odd/even version'
        r['result']='PASS'
    except BaseException as e:r['result']='FAIL';r['failure']=repr(e);raise
    finally:
        if raw and port is not None and port.is_open:
            try:
                port.write(b'\x18\x18');port.flush();r['cleanup_cancel']=until(port,lambda b:b.endswith(b'n6> '),5).decode('utf-8','replace')
            except Exception as e:r['cleanup_error']=repr(e)
        if port is not None:port.close()
        stop.set()
        if thread is not None:thread.join(timeout=2)
        if uart is not None:uart.close()
        if trace is not None:trace.close()
        r['handles_closed']=(port is None or not port.is_open) and (uart is None or not uart.is_open) and (thread is None or not thread.is_alive())
        if lock is not None:
            lock.close()
            if owned and owner_path.exists() and json.loads(owner_path.read_text())==owner:
                marker.unlink();owner_path.unlink();r['lease_released']=True
        r['finished_utc']=utc();(out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in r.items() if k in ('result','failure','confirmed_version','confirmed_state_proven','image_bytes_sent','EOT_sent','reset_sent','handles_closed','lease_released')}),flush=True)
if __name__=='__main__':main()
