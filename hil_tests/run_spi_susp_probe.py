"""Explicit one-shot SUSP exercise, no NOR write or external server request.

Cloud is disabled in RAM first. Wait for ordinary radio traffic; if none meets
the256byte gate, one local Wi-Fi scan supplies larger read-only radio replies.
Never associate/change credentials. Do not retain ambient scan SSID results.
"""

def main():
    import argparse,hashlib,importlib.util,json,re,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--owner-thread');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()!='feature/n6-xip-ota-usb':raise RuntimeError('Wrong branch')
    binary=root/'.local-dependencies/xip/v31-B-susp-probe/N6-XIP-B-v31.n6fw'
    if hashlib.sha256(binary.read_bytes()).hexdigest()!='ef3a8c27e99f34aefed8dddd05a6409dbdd031b4f4a7ca8bebdd6ebbafa08288':raise RuntimeError('Probe artifact mismatch')
    proof=json.loads((root/'.local-dependencies/xip/usb-update-b31-susp-probe/result.json').read_text())
    if not proof['passed'] or not proof['boot_confirmation_seen'] or proof['target_version']!=31:raise RuntimeError('Confirmed source proof missing')
    print('HOST PREFLIGHT PASS exact signed probe and captured confirmed31; no hardware opened',flush=True)
    if not a.execute:return
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if not a.owner_thread or owner['thread']!=a.owner_thread:raise RuntimeError('Wrong owner')
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    lease=load('susp_lease',root/'hil_tests/n6_hardware_lease.py');identity=lease.windows_process_identity(owner['pid'])
    if identity.get('state')!='alive' or identity.get('created_utc')!=owner['process_created_utc']:raise RuntimeError('Owner identity mismatch')
    protocol=load('susp_protocol',root/'hil_tests/run_xip_usb_reject.py')
    output=a.output.resolve()
    if not output.is_relative_to(root):raise RuntimeError('Output outside feature')
    output.mkdir(parents=True,exist_ok=False)
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    if not any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports) or not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports):raise RuntimeError('Exact owned ports absent')
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    stop=threading.Event();result={'NOR_write_requested':False,'server_request_requested':False,'probe_arm_count':0,'passed':False}
    pattern=r'\[SPI-FLOW-TEST\] stage=(\d+) transfer=(\d+) len=(\d+) suspend=(\d+) resume=(\d+) sr=([0-9A-Fa-f]+) rx-left=(\d+) completed=(\d+) resumes=(\d+)'
    try:
        with (output/'uart.log').open('xb') as trace:
            def collect():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:trace.write(data);trace.flush()
                except BaseException as error:result['uart_error']=repr(error)
            thread=threading.Thread(target=collect);thread.start()
            try:
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.3)
                    result['before']={x:protocol.status(port,x) for x in ['version','cloud disable','radio status','cloud status']}
                    if 'Firmware version: 31\r\n' not in result['before']['version'] or 'ToF: sent 0' not in result['before']['cloud status']:raise RuntimeError('Unexpected live state')
                    result['arm']=protocol.status(port,'radio flow-test');result['probe_arm_count']=1
                    if 'One RX DMA suspension test armed' not in result['arm']:raise RuntimeError('Arm not admitted; no retry')
                    print('ONE probe armed, waiting20seconds for ordinary radio reply; Cloud disabled.',flush=True)
                    started=time.monotonic();scan=False;matches=[]
                    while time.monotonic()-started<65:
                        matches=list(re.finditer(pattern,(output/'uart.log').read_text(errors='replace')))
                        if matches and int(matches[-1][1]) in (5,9):break
                        if time.monotonic()-started>=20 and not scan:
                            scan=True;result['local_wifi_scan_requested']=True
                            # Only control acceptance is retained; no AP/SSID list.
                            reply=protocol.status(port,'wifi scan')
                            result['scan_admitted']='Wi-Fi scan request accepted' in reply
                            print('One local read-only scan requested; no server access/credential change.',flush=True)
                        time.sleep(.25)
                    if matches:
                        m=matches[-1];result['probe']=dict(stage=int(m[1]),transfer=int(m[2]),length=int(m[3]),suspend_status=int(m[4]),resume_status=int(m[5]),SR=hex(int(m[6],16)),RX_remaining=int(m[7]),completed=int(m[8]),resume_count=int(m[9]))
                    result['after']={x:protocol.status(port,x) for x in ['version','debug ping 3131','radio status','rps status','cloud status','tof status','dataset stream status']}
                    f=result.get('probe',{})
                    result['passed']=bool(f.get('stage')==5 and f.get('suspend_status')==0 and f.get('resume_status')==0 and int(f.get('SR','0'),16)&0x800 and f.get('RX_remaining',0)>0 and f.get('completed')==1 and f.get('resume_count',0)>0 and 'SPI fault: count=0' in result['after']['radio status'] and 'PONG 3131 ' in result['after']['debug ping 3131'])
                    if not result['passed']:result['blocker']='NOT_ACCEPTED: inspect exact probe fields, no automatic rearm/reset'
            finally:
                stop.set();thread.join(timeout=2)
    finally:
        uart.close();result['owned_handles_closed']=True
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('before','after','arm')}),flush=True)

if __name__=='__main__':main()
