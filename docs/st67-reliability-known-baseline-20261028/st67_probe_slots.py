"""Existing USB Begin/Abort only: four exact 256-byte manifests; no image/EOT/reset.

Requires native production-code proof in test_st67_manifest_probe.py. Probe52
headers name known old payloads only for signature/slot checks; NEVER install them.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,msvcrt,os,re,subprocess,sys,threading,time
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
from n6_hardware_lease import windows_process_identity
from run_xip_usb_reject import packet,until,status as cli
import serial
from serial.tools import list_ports
def utc():return datetime.now(timezone.utc).isoformat()
def main():
    evidence=Path(__file__).parent/'evidence/st67-cp3-20261028'
    out=evidence/'slot-probe';out.mkdir(exist_ok=False)
    old=(ROOT/'.local-dependencies/xip/v50-B-timed-demo-map/N6-XIP-B-v50.n6fw').read_bytes()
    assert hashlib.sha256(old).hexdigest()=='2a7aedb4fcd156f8eafa0bd322116452cf8fbd1f1e4aec7989ed7e84b5d9e156'
    manifests=[]
    for row in json.loads((evidence/'headers/headers.json').read_text(encoding='utf-8-sig')):
        h=(evidence/f"headers/NO-INSTALL-{row['slot']}-version52.manifest").read_bytes()
        assert len(h)==256 and hashlib.sha256(h).hexdigest()==row['headerSha256']
        assert int.from_bytes(h[20:24],'little')==52
        assert int.from_bytes(h[24:28],'little')=={'A':1,'B':2}[row['slot']]
        manifests.append((row['slot'],h))
    assert [x[0] for x in manifests]==['A','B']
    common=Path(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';owner_path=folder/'n6-hardware-owner.json'
    assert not any(x.exists() for x in (marker,owner_path,folder/'n6-hardware-recovery.lock')),'Existing owner'
    identity=windows_process_identity(os.getpid());assert identity['state']=='alive'
    owner={'thread':'n6-xip-st67-reliability-20261028','pid':os.getpid(),'started_utc':utc(),'process_created_utc':identity['created_utc'],
      'scope':'USB signed manifest-only Begin/Abort inactive-slot identification; zero image/EOT/reset/settings writes'}
    r={'started_utc':utc(),'owner':owner,'result':'INCOMPLETE','cases':[],'manifest_bytes_sent':0,'image_bytes_sent':0,'EOT_sent':False,'reset_sent':False,'handles_closed':False,'lease_released':False}
    lock=uart=port=thread=trace=None;owned=False;raw=False;stop=threading.Event()
    def collect():
        try:
            while not stop.is_set():
                b=uart.read(4096)
                if b:trace.write(b);trace.flush()
        except Exception as e:r['uart_error']=repr(e)
    def probe(name,header):
        nonlocal raw
        assert len(header)==256
        record={'name':name,'utc':utc(),'header_sha256':hashlib.sha256(header).hexdigest(),'result':'INCOMPLETE'};r['cases'].append(record)
        trace.flush();start_offset=(out/'uart.log').stat().st_size
        port.write(b'update\r');port.flush();raw=True
        record['start']=until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C')).decode('ascii','replace')
        for index in range(2):
            frame=packet(header[index*128:(index+1)*128],sequence=index+1)
            assert len(frame)==133 and frame[0]==1
            port.write(frame);port.flush();r['manifest_bytes_sent']+=128
            reply=until(port,lambda b:b'\x06' in b or b'\x18\x18' in b)
            record[f'reply{index+1}_hex']=reply.hex()
            if index==0:assert b'\x06' in reply and b'\x18' not in reply
        accepted=b'\x06' in reply
        if accepted:port.write(b'\x18\x18');port.flush()
        terminal=until(port,lambda b:b.endswith(b'n6> '));raw=False
        record['terminal']=terminal.decode('utf-8','replace')
        assert b'transfer cancelled or rejected' in terminal
        time.sleep(.5);trace.flush()
        text=(out/'uart.log').read_bytes()[start_offset:].decode('utf-8','replace');record['uart']=text
        assert '[SECURE-UPDATE] signature accepted; loading boot metadata' in text
        assert 'boot state is not confirmed' not in text
        if name.startswith('confirmed'):
            assert not accepted and 'Begin accepted; session' not in text
            versions=re.findall(r'\[SECURE-UPDATE\] confirmed version = 0x([0-9A-Fa-f]+)',text)
            assert len(versions)==1 and int(versions[0],16)==51
            record['confirmed_version']=51
        elif accepted:
            assert 'Begin accepted; session' in text and 'Secure Begin returned: status=0 ' in text
        else:
            assert 'Begin accepted; session' not in text and 'Secure Begin returned: status=1 session=0' in text
        record['accepted']=accepted
        record['version_after']=cli(port,'version');assert 'Firmware version: 51\r\n' in record['version_after']
        record['result']='PASS'
        print(json.dumps({'case':name,'accepted':accepted,'result':'PASS','image_bytes_sent':0}),flush=True)
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
        commands=('version','status','radio status','tof status','rps status','ble status','dataset stream status','cloud status')
        r['before']={c:cli(port,c) for c in commands}
        assert 'Firmware version: 51\r\n' in r['before']['version']
        assert 'requested NONE, active NONE' in r['before']['tof status'] and 'ToF state: ready' in r['before']['tof status']
        assert 'errors=0' in r['before']['rps status'] and 'Dataset stream: off' in r['before']['dataset stream status']
        assert 'BLE disconnected' in r['before']['status']
        probe('confirmed-before',old[:256])
        for slot,header in manifests:probe(slot,header)
        accepted=[c['name'] for c in r['cases'] if c['accepted']]
        assert len(accepted)==1 and accepted[0] in ('A','B')
        probe('confirmed-after',old[:256])
        r['inactive_slot']=accepted[0];r['confirmed_slot']={'A':'B','B':'A'}[accepted[0]];r['confirmed_version']=51
        r['slot_evidence']='Inference from authenticated current Secure Begin opposite-slot selection: one accepted, other parameter-rejected after authentication; not raw NOR/PC read'
        r['after']={c:cli(port,c) for c in commands}
        assert 'Firmware version: 51\r\n' in r['after']['version']
        assert 'ToF state: ready' in r['after']['tof status'] and 'errors=0' in r['after']['rps status']
        assert 'requested NONE, active NONE' in r['after']['tof status'] and 'Dataset stream: off' in r['after']['dataset stream status']
        before=int(re.search(r'Uptime: (\d+)',r['before']['status'])[1]);after=int(re.search(r'Uptime: (\d+)',r['after']['status'])[1]);assert after>before
        r['uptime_before_ms']=before;r['uptime_after_ms']=after
        assert not r.get('uart_error')
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
        print(json.dumps({k:v for k,v in r.items() if k in ('result','failure','inactive_slot','confirmed_slot','confirmed_version','manifest_bytes_sent','image_bytes_sent','EOT_sent','reset_sent','handles_closed','lease_released')}),flush=True)
if __name__=='__main__':main()
