"""Bounded existing UART overflow control plus deferred resource capture.

Local USB/UART only. No reset, firmware transfer, network request or sensor
stream. USB is closed before the75second capture interval, allowing separate
owned NPU HIL to exercise the sampled runtime without competing readers.
"""

def main():
    import argparse,importlib.util,json,re,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--owner-thread');p.add_argument('--output',type=Path,required=True);p.add_argument('--version',type=int,default=32)
    p.add_argument('--seconds',type=int,choices=range(8,121),default=75,help='Bounded capture; short captures do not imply all stacks sampled')
    p.add_argument('--overflow',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip() not in ('main', 'feature/n6-xip-ota-usb'):raise RuntimeError('Wrong branch')
    print('HOST PREFLIGHT PASS bounded local UART/memory control; no hardware opened',flush=True)
    if not a.execute:return
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if owner['thread']!=a.owner_thread:raise RuntimeError('Wrong owner')
    lease=load('memory_lease',root/'hil_tests/n6_hardware_lease.py');identity=lease.windows_process_identity(owner['pid'])
    if identity.get('state')!='alive' or identity.get('created_utc')!=owner['process_created_utc']:raise RuntimeError('Owner identity mismatch')
    protocol=load('memory_protocol',root/'hil_tests/run_xip_usb_reject.py')
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    if not any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports) or not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports):raise RuntimeError('Exact ports absent')
    out=a.output.resolve()
    if not out.is_relative_to(root):raise RuntimeError('Output outside feature')
    out.mkdir(parents=True,exist_ok=False)
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    stop=threading.Event();result={'passed':False,'overflow_requested':a.overflow,'serial_UART_writes':0,'network_requests':False,'capture_seconds':a.seconds}
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
                    result['before']={x:protocol.status(port,x) for x in ['version','cloud disable','debug uart','cloud status','dataset stream status']}
                    if f'Firmware version: {a.version}\r\n' not in result['before']['version'] or 'ToF: sent 0' not in result['before']['cloud status'] or 'Dataset stream: off' not in result['before']['dataset stream status']:raise RuntimeError('Unexpected baseline')
                    if a.overflow:
                        result['overflow_start']=protocol.status(port,'debug uart overflow')
                        if 'overflow: started' not in result['overflow_start']:raise RuntimeError('Overflow control not admitted')
                        time.sleep(2)
                        result['overflow_status']=protocol.status(port,'debug uart')
                        m=re.search(r'dropped_delta=(\d+)',result['overflow_status'])
                        if not m or int(m[1])==0:raise RuntimeError('Existing overflow control did not exercise drops')
                        result['controlled_drops']=int(m[1])
                    result['snapshot_request']=protocol.status(port,'debug resources')
                    result['PONG']=protocol.status(port,'debug ping 3232')
                    if 'Resource snapshot scheduled' not in result['snapshot_request'] or 'PONG 3232 ' not in result['PONG']:raise RuntimeError('Control response missing')
                print(f'USB CLOSED; UART snapshot{a.seconds}s, model HIL may now use USB separately.',flush=True)
                start=time.monotonic();reported=0
                while time.monotonic()-start<a.seconds:
                    time.sleep(.25)
                    elapsed=int(time.monotonic()-start)
                    if elapsed>=reported+20:reported=elapsed;print('UART snapshot elapsed',elapsed,'seconds',flush=True)
                text=(out/'uart.log').read_text(errors='replace')
                failures=[int(m[1],16) for m in re.finditer(r'\[RESOURCE\] 00000006 00000001 ([0-9A-F]{8})',text)]
                result['retained_LOG_ENQUEUE_counts']=failures
                result['overflow_reported_after_backpressure']=not a.overflow or bool(failures and max(failures)>=result['controlled_drops'])
                result['usage_rows']=len(re.findall(r'\[RESOURCE\] 000000FF ',text))
                result['passed']=result['overflow_reported_after_backpressure'] and result['usage_rows']>0
            finally:
                stop.set();thread.join(timeout=2)
    finally:
        uart.close();result['owned_handles_closed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('before','overflow_status','overflow_start','snapshot_request','PONG')}),flush=True)

if __name__=='__main__':main()
