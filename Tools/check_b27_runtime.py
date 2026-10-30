"""B27 status/confirmation and sampled memory, without reset or image writing.

Sends only an old signed A23 manifest as two128byte blocks: zero image bytes,
no EOT. Begin can authenticate/read metadata, but cannot erase/program without
image bytes. Capture the VERSION rejection to prove confirmed27, then request
deferred resource telemetry. Default preflight has no hardware actions.
"""

def main():
    import argparse,binascii,hashlib,importlib.util,json,subprocess,threading,time
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread');parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',type=int,default=27);a=parser.parse_args()
    if a.version<=23:raise RuntimeError('Old fixture must precede expected version')
    root=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip() not in ('main', 'feature/n6-xip-ota-usb'):raise RuntimeError('Wrong branch')
    package=(root/'.local-dependencies/xip/v23-A-rx-resume-probe-tifre/N6-XIP-A-v23.n6fw').read_bytes()
    if hashlib.sha256(package).hexdigest()!='c7f03bda984741b82d1332aaa64e2a27d2827a6abc7ea3f2184e50b9659cc953':raise RuntimeError('Old fixture mismatch')
    print('HOST PREFLIGHT PASS old signed manifest256bytes only, no image/EOT/reset; no hardware opened',flush=True)
    if not a.execute:return
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if owner['thread']!=a.owner_thread:raise RuntimeError('Wrong owner')
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    lease=load('b27_lease',root/'hil_tests/n6_hardware_lease.py');identity=lease.windows_process_identity(owner['pid'])
    if identity.get('state')!='alive' or identity.get('created_utc')!=owner['process_created_utc']:raise RuntimeError('Owner identity mismatch')
    out=a.output.resolve()
    if not out.is_relative_to(root):raise RuntimeError('Output outside feature')
    out.mkdir(parents=True,exist_ok=False)
    protocol=load('b27_protocol',root/'hil_tests/run_xip_usb_reject.py')
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    if not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports):raise RuntimeError('Exact application USB absent')
    if not any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports):raise RuntimeError('Exact passive UART absent')
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    stop=threading.Event();result={'image_bytes_sent':0,'EOT_sent':False,'reset_sent':False,'boot_capture_available':False,'passed':False}
    try:
        with (out/'uart.log').open('xb') as trace:
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
                    result['before_version']=protocol.status(port,'version')
                    if f'Firmware version: {a.version}\r\n' not in result['before_version']:raise RuntimeError('Unexpected version; no test')
                    port.reset_input_buffer();port.write(b'update\r');port.flush()
                    protocol.until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
                    time.sleep(.5)
                    for index in (0,1):
                        port.write(protocol.packet(package[index*128:(index+1)*128],sequence=index+1));port.flush()
                        reply=protocol.until(port,lambda b:b'\x06' in b or b'\x18\x18' in b)
                        result['header_reply_'+str(index+1)]=reply.hex()
                        if index==0 and b'\x06' not in reply:raise RuntimeError('Partial old manifest rejected unexpectedly')
                    if b'\x06' in reply:port.write(b'\x18\x18');port.flush()
                    result['terminal']=protocol.until(port,lambda b:b.endswith(b'n6> ')).decode('utf8','replace')
                    time.sleep(.5);trace.flush()
                    text=(out/'uart.log').read_text(errors='replace')
                    if '[SECURE-UPDATE] confirmed version = 0x%08X'%a.version not in text:raise RuntimeError('Expected confirmed version not proven; no further tests')
                    if '[SECURE-UPDATE] signature accepted; loading boot metadata' not in text:raise RuntimeError('Signature path not proven')
                    result['confirmed_version']=a.version
                    result['after']={line:protocol.status(port,line) for line in ['cloud disable','tof resume','debug resources','debug uart','rps status','cloud status','dataset stream status','debug ping 2702']}
                    if 'Resource snapshot scheduled' not in result['after']['debug resources']:raise RuntimeError('Resource profile not active')
                    if 'ToF: sent 0' not in result['after']['cloud status'] or 'Dataset stream: off' not in result['after']['dataset stream status']:raise RuntimeError('Unexpected export state')
                    print(f'PASS actual Secure confirmed{a.version}; no image bytes/EOT/reset. Resource profile active, deferred snapshot collecting75s.',flush=True)
                deadline=time.monotonic()+75
                while time.monotonic()<deadline:time.sleep(.25)
                result['passed']=True
            finally:
                stop.set();thread.join(timeout=2)
    finally:
        uart.close();result['owned_handles_closed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('after','before_version','terminal')}),flush=True)

if __name__=='__main__':main()
