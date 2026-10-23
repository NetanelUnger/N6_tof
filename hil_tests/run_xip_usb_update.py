"""One explicit signed inactive-slot USB update from a measured XIP application.

Uses existing Send-Xmodem.ps1. Never programs FSBL/Secure or retries a whole
image. Optional trial testing sends one explicit CLI reboot before confirmation.
The confirmed source stays protected; original recovery artifacts stay on host.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def command(port,line):
    port.reset_input_buffer();port.write((line+'\r').encode());port.flush()
    data=bytearray();deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        data.extend(port.read(4096))
        if data.endswith(b'n6> '):return data.decode('utf-8','replace')
    raise TimeoutError('No complete CLI response to '+line)


def wait_usb_disconnect(enumerate_ports,now=time.monotonic,sleep=time.sleep,seconds=15):
    """Wait for source disappearance before any candidate-open attempt."""
    deadline=now()+seconds
    while any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in enumerate_ports()):
        if now()>deadline:raise RuntimeError('No automatic USB disconnect observed; no candidate reset/open attempted')
        sleep(.05)


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--label')
    parser.add_argument('--source-version',type=int,default=12)
    parser.add_argument('--target-version',type=int,default=13)
    parser.add_argument('--package',default='.local-dependencies/xip/v13-B-reset-safe3/N6-XIP-B-v13.n6fw')
    parser.add_argument('--hil-proof',default='.local-dependencies/xip/hil-A12-persistent-cold-1959.json')
    parser.add_argument('--source-confirmation-proof',help='Explicit verified Secure confirmed-version artifact instead of claiming a source HIL100 result, for diagnostic repair')
    parser.add_argument('--trial-reboot',action='store_true',help='One reboot while candidate trial is unconfirmed, to measure rollback; no automatic retry')
    parser.add_argument('--interrupt-first',action='store_true',
                        help='Explicit controlled cancel after one valid1024-byte packet, before full transfer')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source_version,target_version=args.source_version,args.target_version
    package=(root/args.package).resolve();assert package.is_relative_to(root)
    build=package.parent;name=package.name;info=json.loads((build/'build.json').read_text())
    assert hashlib.sha256(package.read_bytes()).hexdigest()==info['hashes'][name]['sha256'].lower()
    backup=root/'.local-dependencies/xip/inspection-after-bootchain-program/nor-first.bin'
    assert hashlib.sha256(backup.read_bytes()).hexdigest()=='6cc2cfb51d893b06e75d32c1614818406bcc2a6219f68cb2b98a9c9cae43faaf'
    assert info['slot'] in ('A','B') and info['version']==target_version and target_version>source_version
    if args.source_confirmation_proof:
        proof=(root/args.source_confirmation_proof).resolve();assert proof.is_relative_to(root)
        accepted=json.loads(proof.read_text())
        assert accepted['passed']
        if 'confirmed_version' in accepted:
            assert accepted['confirmed_version']==source_version
            assert accepted['image_bytes_sent']==0 and not accepted['EOT_sent'] and not accepted['reset_sent']
            source_admission='Verified Secure confirmed-version, HIL100 not claimed for this source'
        else:
            assert accepted['target_version']==source_version and accepted['candidate_running'] and accepted['boot_confirmation_seen']
            source_admission='Captured USB source boot/confirmation, HIL100 not claimed for this source'
    else:
        hil_proof=(root/args.hil_proof).resolve();assert hil_proof.is_relative_to(root)
        accepted=json.loads(hil_proof.read_text());assert accepted['passed'] and accepted['frames']==100
        source_admission='Existing HIL100 artifact'
    if args.preflight_only or not args.execute:
        print(f'HOST PREFLIGHT PASS signed build hash, recovery backup, {source_admission}; source{source_version} target{target_version} trial-reboot={args.trial_reboot}; no hardware opened')
        return
    import importlib.util,threading,serial
    from serial.tools import list_ports
    spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    identity=lease.windows_process_identity(owner['pid'])
    assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/usb-update-'+args.label);output.mkdir(exist_ok=False)
    result={'scope':f'Signed v{target_version} while v{source_version} executes XIP, existing USB path','package_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),
            'source_admission':source_admission,
            'source_version':source_version,'target_version':target_version,'trial_reboot_requested':args.trial_reboot,
            'bytes':package.stat().st_size,'confirmed_fallback_before':source_version,
            'B11_original_preserved_as_host_backup':True,'sender_started':False,'passed':False}
    stop=threading.Event();thread=None;uart=None
    try:
        with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
            port.dtr=True;time.sleep(.3)
            result['before']={line:command(port,line) for line in ['version','tof status','rps status','cloud status','dataset stream status']}
            assert f'Firmware version: {source_version}\r\n' in result['before']['version']
            assert 'ToF: sent 0' in result['before']['cloud status'] and 'requested NONE, active NONE' in result['before']['tof status']
            assert 'Dataset stream: off' in result['before']['dataset stream status']
        uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
        uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
        with (output/'uart.log').open('xb') as trace,(output/'sender.log').open('w') as sendlog:
            def collect():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:trace.write(data);trace.flush()
                except BaseException as error:result['uart_error']=repr(error)
            thread=threading.Thread(target=collect);thread.start()
            if args.interrupt_first:
                spec=importlib.util.spec_from_file_location('negative_protocol',root/'hil_tests/run_xip_usb_reject.py')
                protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;port.reset_input_buffer();port.write(b'update\r');port.flush()
                    protocol.until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
                    time.sleep(.5)
                    frame=protocol.packet(package.read_bytes()[:1024])
                    port.write(frame);port.flush()
                    ack=protocol.until(port,lambda b:b'\x06' in b or b'\x18\x18' in b,15)
                    result['partial_interruption']={'valid_packet_sent':True,'image_bytes':768,'receiver_ack':b'\x06' in ack}
                    assert b'\x06' in ack,'Valid partial packet rejected; no full-transfer retry'
                    port.write(b'\x18\x18');port.flush()
                    cancelled=protocol.until(port,lambda b:b.endswith(b'n6> '))
                    result['partial_interruption']['cancel_response']=cancelled.decode('utf-8','replace')
                    assert b'transfer cancelled or rejected' in cancelled
                    time.sleep(.5)
                    after={line:command(port,line) for line in ['version','debug ping 1313','tof status','rps status','cloud status']}
                    result['partial_interruption']['after']=after
                    assert f'Firmware version: {source_version}\r\n' in after['version'] and 'PONG 1313 ' in after['debug ping 1313']
                    assert 'ToF state: ready' in after['tof status'] and 'errors=0' in after['rps status']
                    assert 'ToF: sent 0' in after['cloud status']
                    result['partial_interruption']['passed']=True
                    print(f'PASS controlled USB interruption after authenticated image768bytes; source v{source_version} healthy',flush=True)
            pwsh='C:/Users/netan/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
            sender=subprocess.Popen([pwsh,'-NoProfile','-File',str(root/'Tools/Send-Xmodem.ps1'),'-File',str(package),'-Port','COM8',
                                     '-StartTimeoutSeconds','10','-BlockTimeoutSeconds','10','-FinalizeTimeoutSeconds','30','-MaxRetries','2'],
                                     stdout=sendlog,stderr=subprocess.STDOUT,creationflags=0x08000000)
            result.update(sender_started=True,sender_pid=sender.pid)
            deadline=time.monotonic()+480;last=''
            while sender.poll() is None:
                if time.monotonic()>deadline:
                    # Do not terminate a potentially committing sender silently.
                    result['sender_still_running']=True
                    raise TimeoutError('Owned sender still running; inspect PID/log before any other COM8 operation')
                time.sleep(1)
                lines=(output/'sender.log').read_text(errors='replace').splitlines()
                progress=next((x for x in reversed(lines) if x.startswith('XMODEM:')),'')
                if progress and progress!=last:print(progress,flush=True);last=progress
            result['sender_exit']=sender.returncode
            text=(output/'sender.log').read_text(errors='replace')
            result['authenticated_finalization']='XMODEM transfer and device-side finalization completed successfully.' in text and sender.returncode==0
            if not result['authenticated_finalization']:raise RuntimeError('USB sender did not confirm finalization; inspect before retry')
            print('SIGNED IMAGE TRANSFER/FINALIZATION PASS',result['bytes'],flush=True)
            # All modes must distinguish the old source port from the candidate.
            # A fixed sleep raced the source disconnect in the first A17 check.
            wait_usb_disconnect(list_ports.comports)
            result['automatic_USB_disconnect_seen']=True
            deadline=time.monotonic()+75
            while time.monotonic()<deadline:
                found=any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports())
                if found:
                    if not args.trial_reboot:time.sleep(.2)
                    with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                        port.dtr=True
                        result['version_after']=command(port,'version')
                        if f'Firmware version: {target_version}\r\n' in result['version_after']:
                            if args.trial_reboot:
                                trace.flush();before_trial_reset=(output/'uart.log').read_text(errors='replace')
                                if 'boot confirmed; rollback window closed' in before_trial_reset:
                                    raise RuntimeError('Trial confirmation already occurred; no rollback reboot sent; no automatic image retry')
                                port.reset_input_buffer();port.write(b'reboot yes\r');port.flush()
                                result['trial_reboot_sent']=True
                                print('ONE trial reboot sent before observed confirmation; awaiting actual rollback evidence',flush=True)
                                break
                    if f'Firmware version: {target_version}\r\n' in result.get('version_after',''):break
                time.sleep(.05 if args.trial_reboot else 1)
            if args.trial_reboot and result.get('trial_reboot_sent'):
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    trace.flush();trial_text=(output/'uart.log').read_text(errors='replace')
                    if 'boot confirmed; rollback window closed' in trial_text:break
                    time.sleep(.1)
                if any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports()):
                    with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                        port.dtr=True;time.sleep(.2)
                        result['rollback_version']=command(port,'version')
                        result['after']={line:command(port,line) for line in ['tof status','rps status','cloud status','dataset stream status']}
            # App USB is ready before the ten-second boot-confirmation worker.
            # Retain the live UART through confirmation; never re-send an image
            # just because an early version response preceded that message.
            if not args.trial_reboot and f'Firmware version: {target_version}\r\n' in result.get('version_after',''):
                confirmation_deadline=time.monotonic()+30
                while time.monotonic()<confirmation_deadline:
                    trace.flush()
                    if 'boot confirmed; rollback window closed' in (output/'uart.log').read_text(errors='replace'):break
                    time.sleep(.25)
                # USB enumerates before application startup/control ownership
                # settles. Query health only after actual boot confirmation;
                # retain the original five-second per-command limit.
                trace.flush()
                if 'boot confirmed; rollback window closed' in (output/'uart.log').read_text(errors='replace'):
                    with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                        port.dtr=True;time.sleep(.2)
                        result['after']={line:command(port,line) for line in ['tof status','rps status','cloud status','dataset stream status']}
            stop.set();thread.join(timeout=2);trace.flush()
            captured=(output/'uart.log').read_text(errors='replace')
            result['boot_confirmation_seen']='boot confirmed; rollback window closed' in captured
            result['candidate_running']=f'Firmware version: {target_version}\r\n' in result.get('version_after','')
            result['passed']=result['authenticated_finalization'] and result['candidate_running'] and result['boot_confirmation_seen']
            if args.trial_reboot:
                result['rollback_to_source']=f'Firmware version: {source_version}\r\n' in result.get('rollback_version','')
                result['rollback_UART_lines']=[line for line in captured.splitlines() if 'rollback' in line.lower() or 'metadata:' in line]
                result['FSBL_rollback_seen']='unconfirmed trial detected; rolling back to slot' in captured
                result['passed']=result['authenticated_finalization'] and result.get('trial_reboot_sent',False) and result['rollback_to_source'] and result['boot_confirmation_seen'] and result['FSBL_rollback_seen']
            if not result['passed']:result['blocker']='Inspect retained candidate/rollback evidence; no whole-transfer retry or additional reset issued.'
    except BaseException as error:
        result['error']=repr(error);raise
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=2)
        if uart is not None:uart.close()
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('USB RESULT',json.dumps({k:v for k,v in result.items() if not isinstance(v,dict)}),flush=True)


if __name__=='__main__':cli_main()
