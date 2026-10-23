"""One signed B27 repair through the verified guarded RAM USB control image.

Default host-only preflight. --execute reads live status and disables Cloud in
RAM. --transfer additionally invokes the existing XMODEM sender exactly once.
Reset refusal is a verified RAM patch; expect pending metadata, no auto boot.
"""

def main():
    import argparse,hashlib,importlib.util,json,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--transfer',action='store_true');p.add_argument('--owner-thread');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];git=['git','-c','safe.directory='+str(root),'-C',str(root)]
    if subprocess.check_output(git+['branch','--show-current'],text=True).strip()!='feature/n6-xip-ota-usb':raise RuntimeError('Wrong branch')
    package=root/'.local-dependencies/xip/v27-B-resource-margin/N6-XIP-B-v27.n6fw'
    if hashlib.sha256(package.read_bytes()).hexdigest()!='e1302494519bdce727cb03de79da22b683209d362323bfafd0e824ac225e6bc6':raise RuntimeError('Candidate mismatch')
    launch=json.loads((root/'.local-dependencies/xip/recovery-ram-20261023-1205/result.json').read_text())
    if launch.get('reset_refusal_RAM_patch')!='0x24110998' or launch.get('A23_entered') is not False or launch.get('nor_written') is not False:raise RuntimeError('Guarded RAM proof missing')
    print('HOST PREFLIGHT PASS B27 hash and verified RAM reset refusal; no hardware opened',flush=True)
    if not a.execute:return
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    owner=json.loads((common.parent/'.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if not a.owner_thread or owner['thread']!=a.owner_thread:raise RuntimeError('Wrong owner')
    spec=importlib.util.spec_from_file_location('repair_lease',root/'hil_tests/n6_hardware_lease.py');lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid'])
    if identity.get('state')!='alive' or identity.get('created_utc')!=owner['process_created_utc']:raise RuntimeError('Owner identity mismatch')
    output=a.output.resolve()
    if not output.is_relative_to(root):raise RuntimeError('Output outside feature')
    output.mkdir(parents=True,exist_ok=False)
    import serial
    from serial.tools import list_ports
    if not any(x.device=='COM8' and x.serial_number=='N6TOF001' for x in list_ports.comports()):raise RuntimeError('Exact app USB absent; no open')
    def command(port,line):
        port.reset_input_buffer();port.write((line+'\r').encode());port.flush();data=bytearray();deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            data.extend(port.read(8192))
            if data.endswith(b'n6> '):return data.decode('utf8','replace')
        raise TimeoutError('Incomplete CLI: '+line)
    result={'sender_started':False,'sender_invocations':0,'passed':False,'source':'guarded RAM27, not A23 or XIP','package_sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
    stop=threading.Event();uart=None;thread=None
    try:
        with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
            port.dtr=True;time.sleep(.3)
            result['before']={}
            for line in ['version','cloud disable','cloud status','tof status','rps status','dataset stream status','debug ping 2727']:
                result['before'][line]=command(port,line)
                print(line,ascii(result['before'][line][:180]),flush=True)
            before=result['before']
            if 'Firmware version: 27\r\n' not in before['version'] or 'disable queued' not in before['cloud disable']:raise RuntimeError('Unexpected RAM control')
            if 'ToF: sent 0' not in before['cloud status'] or 'requested NONE, active NONE' not in before['tof status'] or 'Dataset stream: off' not in before['dataset stream status']:raise RuntimeError('Unexpected export state; no update')
            if 'errors=0' not in before['rps status'] or 'PONG 2727 ' not in before['debug ping 2727']:raise RuntimeError('RAM control unhealthy')
        if not a.transfer:
            result['passed']=True;return
        uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
        with (output/'uart.log').open('xb') as trace,(output/'sender.log').open('w') as sendlog:
            def collect():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:trace.write(data);trace.flush()
                except BaseException as error:result['uart_error']=repr(error)
            thread=threading.Thread(target=collect);thread.start()
            try:
                pwsh='C:/Users/netan/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
                sender=subprocess.Popen([pwsh,'-NoProfile','-File',str(root/'Tools/Send-Xmodem.ps1'),'-File',str(package),'-Port','COM8','-StartTimeoutSeconds','10','-BlockTimeoutSeconds','10','-FinalizeTimeoutSeconds','30','-MaxRetries','2'],stdout=sendlog,stderr=subprocess.STDOUT,creationflags=0x08000000)
                result.update(sender_started=True,sender_invocations=1,sender_pid=sender.pid)
                deadline=time.monotonic()+480;last=''
                while sender.poll() is None:
                    if time.monotonic()>deadline:
                        result['sender_still_running']=True;raise TimeoutError('Sender still running: inspect before any retry/open')
                    time.sleep(1)
                    lines=(output/'sender.log').read_text(errors='replace').splitlines()
                    progress=next((x for x in reversed(lines) if x.startswith('XMODEM:')),'')
                    if progress and progress!=last:print(progress,flush=True);last=progress
                result['sender_exit']=sender.returncode
                text=(output/'sender.log').read_text(errors='replace')
                if sender.returncode!=0 or 'XMODEM transfer and device-side finalization completed successfully.' not in text:raise RuntimeError('Finalization unconfirmed; inspect before retry')
                time.sleep(3)
                result['reset_refused_observed']='reset blocked; cold restart required' in (output/'uart.log').read_text(errors='replace')
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.2)
                    result['after']={line:command(port,line) for line in ['version','debug ping 2728','cloud status','tof status']}
                if not result['reset_refused_observed'] or 'PONG 2728 ' not in result['after']['debug ping 2728']:raise RuntimeError('Expected RAM control after commit not proven')
                result.update(passed=True,candidate='B27 authenticated/finalized; pending boot, not confirmed',bytes=package.stat().st_size)
            finally:
                stop.set();thread.join(timeout=2)
    finally:
        if uart is not None:uart.close()
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')}),flush=True)

if __name__=='__main__':main()
