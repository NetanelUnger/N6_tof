"""One signed B52 USB update; preserve confirmed A51. No whole-image retry.

Uses existing Send-Xmodem.ps1 and original per-block limits. Quiet builds are
confirmed through authenticated old-header rejection, never an absent NS log.
"""
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
    base=Path(__file__).parent/'evidence/st67-cp3-20261028';out=base/'install52';out.mkdir(exist_ok=False)
    build=ROOT/'.local-dependencies/xip/v52-B-st67-known-baseline';package=build/'N6-XIP-B-v52.n6fw'
    info=json.loads((build/'build.json').read_text());assert info['version']==52 and info['slot']=='B'
    assert info['source_commit']=='5432d4ae2b10ef7ecdfaedad586038792f0a4db5'
    assert info['watchdog'] and info['resource_diagnostics'] and info['ncp_preserve'] and not info['fault_probe'] and not info['cloud_auto_map']
    expected='8e1266cfde906c545277d9eb9a0fb01ef986202bb44b9e161510fbbdbb8df36b'
    assert hashlib.sha256(package.read_bytes()).hexdigest()==expected==info['hashes'][package.name]['sha256'].lower()
    old=(ROOT/'.local-dependencies/xip/v50-B-timed-demo-map/N6-XIP-B-v50.n6fw').read_bytes()
    assert hashlib.sha256(old).hexdigest()=='2a7aedb4fcd156f8eafa0bd322116452cf8fbd1f1e4aec7989ed7e84b5d9e156'
    # The prior diagnostic failed a redundant asynchronous NS-log assertion.
    # Require its actual direct Secure and wire evidence, plus independent
    # subsequent confirmed51 proof; do not rewrite its failed result.
    probe=json.loads((base/'slot-probe/result.json').read_text());cases={c['name']:c for c in probe['cases']}
    assert cases['A']['reply2_hex']=='1818' and 'Secure Begin returned: status=1 session=0' in cases['A']['uart']
    assert cases['B']['reply2_hex']=='06' and '[SECURE-UPDATE] Begin accepted; session = ' in cases['B']['uart']
    assert 'transfer cancelled or rejected' in cases['B']['terminal']
    confirmation=json.loads((base/'post-probe-confirmation/result.json').read_text())
    assert confirmation['result']=='PASS' and confirmation['confirmed_version']==51
    assert confirmation['image_bytes_sent']==0 and not confirmation['EOT_sent'] and not confirmation['reset_sent']
    common=Path(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()==info['source_commit']
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';owner_path=folder/'n6-hardware-owner.json'
    assert not any(x.exists() for x in (marker,owner_path,folder/'n6-hardware-recovery.lock')),'Existing owner'
    identity=windows_process_identity(os.getpid());assert identity['state']=='alive'
    owner={'thread':'n6-xip-st67-reliability-20261028','pid':os.getpid(),'started_utc':utc(),'process_created_utc':identity['created_utc'],
           'scope':'One signed USB B52 baseline installation, confirmed A51 protected; passive UART and confirmed-state verification; no bootchain/security/settings writes'}
    r={'started_utc':utc(),'owner':owner,'result':'INCOMPLETE','source_version':51,'source_confirmed_slot':'A','target_version':52,'target_slot':'B',
       'package_sha256':expected,'bytes':package.stat().st_size,'sender_started':False,'reset_commands':0,'whole_transfer_retries':0,
       'source51_host_artifact':'NOT_FOUND; A51 retained on board by signed A/B installer, original B50 retained on host',
       'automatic_disconnect_seen':False,'handles_closed':False,'lease_released':False}
    lock=uart=port=thread=trace=sendlog=sender=None;owned=False;raw=False;stop=threading.Event()
    def collect():
        try:
            while not stop.is_set():
                b=uart.read(4096)
                if b:trace.write(b);trace.flush()
        except Exception as e:r['uart_error']=repr(e)
    def open_usb():
        p=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);p.dtr=True;p.rts=False;p.port='COM8';p.open();time.sleep(.3);return p
    def confirmed(version):
        nonlocal raw
        trace.flush();offset=(out/'uart.log').stat().st_size
        record={'expected':version,'image_bytes_sent':0,'EOT_sent':False,'reset_sent':False}
        r.setdefault('confirmations',[]).append(record)
        port.write(b'update\r');port.flush();raw=True
        until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
        for i in range(2):
            frame=packet(old[i*128:(i+1)*128],sequence=i+1);assert len(frame)==133
            port.write(frame);port.flush();reply=until(port,lambda b:b'\x06' in b or b'\x18\x18' in b)
            if i==0:assert reply==b'\x06'
        if b'\x06' in reply:raise RuntimeError('Unexpected old-manifest acceptance; cancel and stop')
        record['terminal']=until(port,lambda b:b.endswith(b'n6> ')).decode('utf-8','replace');raw=False
        time.sleep(.5);trace.flush();text=(out/'uart.log').read_bytes()[offset:].decode('utf-8','replace')
        record['uart']=text
        assert '[SECURE-UPDATE] signature accepted; loading boot metadata' in text
        assert f'[SECURE-UPDATE] confirmed version = 0x{version:08X}' in text
        assert 'Begin accepted; session' not in text
        record['result']='PASS'
        print(json.dumps({'phase':'confirmed_metadata','version':version,'result':'PASS'}),flush=True)
    try:
        lock=marker.open('x+b');lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with owner_path.open('x') as f:json.dump(owner,f,indent=2)
        owned=True
        ports=list(list_ports.comports())
        assert any(p.device=='COM8' and p.vid==0x0483 and p.pid==0x5740 and p.serial_number=='N6TOF001' for p in ports)
        assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
        uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
        trace=(out/'uart.log').open('xb');thread=threading.Thread(target=collect);thread.start();port=open_usb()
        commands=('version','status','radio status','tof status','rps status','dataset stream status','cloud status','debug uart')
        r['before']={c:cli(port,c) for c in commands}
        assert 'Firmware version: 51\r\n' in r['before']['version']
        assert 'requested NONE, active NONE' in r['before']['tof status'] and 'ToF state: ready' in r['before']['tof status']
        assert 'errors=0' in r['before']['rps status'] and 'Dataset stream: off' in r['before']['dataset stream status']
        assert 'BLE disconnected' in r['before']['status']
        confirmed(51);port.close();port=None
        pwsh=r'C:\Users\netan\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
        command=[pwsh,'-NoProfile','-File',str(ROOT/'Tools/Send-Xmodem.ps1'),'-File',str(package),'-Port','COM8',
                 '-StartTimeoutSeconds','10','-BlockTimeoutSeconds','10','-FinalizeTimeoutSeconds','30','-MaxRetries','2']
        r['sender_command']=command;sendlog=(out/'sender.log').open('x')
        sender=subprocess.Popen(command,stdout=sendlog,stderr=subprocess.STDOUT,creationflags=0x08000000)
        r.update(sender_started=True,sender_pid=sender.pid);start=time.monotonic();last_progress='';last_report=start
        while sender.poll() is None:
            time.sleep(.2)
            if not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports()):r['automatic_disconnect_seen']=True
            if time.monotonic()-last_report>=15:
                lines=(out/'sender.log').read_text(errors='replace').splitlines()
                progress=next((s for s in reversed(lines) if s.startswith('XMODEM:')),'')
                print(json.dumps({'phase':'sender','elapsed_s':round(time.monotonic()-start,1),'progress':progress}),flush=True);last_report=time.monotonic()
            if time.monotonic()-start>900:r['observation_budget_exceeded']=True
        r['sender_exit']=sender.returncode;r['transfer_seconds']=round(time.monotonic()-start,3);sendlog.flush()
        text=(out/'sender.log').read_text(errors='replace')
        r['authenticated_finalization']=sender.returncode==0 and 'XMODEM transfer and device-side finalization completed successfully.' in text
        assert r['authenticated_finalization'],'Sender did not prove finalization; inspect existing outcome, never retransmit blindly'
        print(json.dumps({'phase':'signed_transfer_finalized','elapsed_s':r['transfer_seconds'],'version_consumed':52}),flush=True)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            found=any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports())
            if not found:r['automatic_disconnect_seen']=True
            trace.flush();boot=(out/'uart.log').read_text(errors='replace')
            if found and '[BOOT] Application firmware version 52' in boot:break
            time.sleep(.2)
        else:raise RuntimeError('Candidate startup not observed; no reset/reflash attempted')
        # Original quiet builds do not emit NS confirmation logs. Wait the existing
        # 50-second watchdog observation window, then require Secure metadata proof.
        ready=time.monotonic();last_report=ready
        while time.monotonic()-ready<50:
            time.sleep(.25)
            if time.monotonic()-last_report>=15:print(json.dumps({'phase':'waiting_trial_confirmation','elapsed_s':round(time.monotonic()-ready,1)}),flush=True);last_report=time.monotonic()
        port=open_usb();r['version_after']=cli(port,'version');assert 'Firmware version: 52\r\n' in r['version_after']
        confirmed(52)
        r['after']={c:cli(port,c) for c in commands}
        assert 'ToF state: ready' in r['after']['tof status'] and 'errors=0' in r['after']['rps status']
        assert 'requested NONE, active NONE' in r['after']['tof status'] and 'Dataset stream: off' in r['after']['dataset stream status']
        trace.flush();boot=(out/'uart.log').read_text(errors='replace')
        r['boot_lines']=[s for s in boot.splitlines() if '[FSBL]' in s or 'XIP NonSecure vector' in s or '[BOOT] Application firmware' in s]
        assert re.search(r'\[FSBL\] update metadata: seq=\d+ state=2 confirmed=0/v51 pending=1/v52',boot)
        assert '[FSBL] candidate image hash accepted' in boot and '[FSBL] authenticated firmware v52; trial boot from slot 1' in boot
        assert '[SECURE] XIP NonSecure vector = 0x70280400' in boot
        assert r['automatic_disconnect_seen'],'USB disconnect not observed; retain as incomplete'
        assert not r.get('uart_error') and not r.get('observation_budget_exceeded')
        r['candidate_running']=True;r['confirmed_version']=52;r['confirmed_slot']='B';r['retained_previous_slot']='A';r['retained_previous_version']=51
        r['physical_rollback_test']='NOT_RUN; previous image retained by current ConfirmBoot swap, native model tested; no fresh whole-NOR read'
        r['result']='PASS'
    except BaseException as e:r['result']='FAIL';r['failure']=repr(e);raise
    finally:
        # Never release a lease or kill a sender that could still be committing.
        while sender is not None and sender.poll() is None:
            print('Owned sender still active; retaining hardware lease until its bounded protocol exits.',flush=True);time.sleep(10)
        if raw and port is not None and port.is_open:
            try:port.write(b'\x18\x18');port.flush();r['cleanup_cancel']=until(port,lambda b:b.endswith(b'n6> '),5).decode('utf-8','replace')
            except Exception as e:r['cleanup_error']=repr(e)
        if port is not None:port.close()
        stop.set()
        if thread is not None:thread.join(timeout=2)
        if uart is not None:uart.close()
        if trace is not None:trace.close()
        if sendlog is not None:sendlog.close()
        r['handles_closed']=(port is None or not port.is_open) and (uart is None or not uart.is_open) and (thread is None or not thread.is_alive())
        if lock is not None:
            lock.close()
            if owned and owner_path.exists() and json.loads(owner_path.read_text())==owner:marker.unlink();owner_path.unlink();r['lease_released']=True
        r['finished_utc']=utc();(out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in r.items() if k in ('result','failure','authenticated_finalization','confirmed_version','confirmed_slot','handles_closed','lease_released','transfer_seconds')}),flush=True)
if __name__=='__main__':main()
