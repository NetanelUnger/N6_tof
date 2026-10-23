"""Explicit A14 OTA with passive UART under an existing verified owner."""
def main():
    import argparse, importlib.util, json, subprocess, threading, time
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread',required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--source',type=int,default=13)
    parser.add_argument('--target',type=int,default=14)
    parser.add_argument('--package',default='.local-dependencies/xip/v14-A-reset-clkp/N6-XIP-A-v14.n6fw')
    parser.add_argument('--usb-proof',default='.local-dependencies/xip/resume-20261022/before-cloud-b13-status.json')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if not args.execute:
        print('PASS preflight; no serial, subprocess or network');return
    import re,serial
    from serial.tools import list_ports
    assert re.fullmatch('[a-z0-9-]+',args.label)
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert owner['thread']==args.owner_thread
    spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid'])
    assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in list_ports.comports())
    folder=root/('.local-dependencies/xip/ota-uart-'+args.label);folder.mkdir(exist_ok=False)
    result={'serial_writes':0,'dtr':False,'rts':False,'sender_started':False}
    stop=threading.Event();reader=None;child=None
    port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1)
    port.dtr=False;port.rts=False;port.port='COM6'
    try:
        port.open()
        with (folder/'uart.log').open('xb') as log:
            def collect():
                try:
                    while not stop.is_set():
                        data=port.read(8192)
                        if data:log.write(data);log.flush()
                except BaseException as error:result['uart_error']=repr(error)
            reader=threading.Thread(target=collect);reader.start()
            print('PASSIVE UART READY DTR/RTS0; starting existing OTA client',flush=True)
            command=['C:/Program Files/nodejs/node.exe',str(root/'hil_tests/run_xip_cloud_update.mjs'),
                '--execute','--owner-thread',args.owner_thread,'--label',args.label,'--from',str(args.source),'--to',str(args.target),
                '--package',args.package,'--usb-proof',args.usb_proof]
            child=subprocess.Popen(command,cwd=root);result.update(sender_started=True,sender_pid=child.pid)
            deadline=time.monotonic()+1260
            while child.poll() is None and time.monotonic()<deadline:time.sleep(.5)
            if child.poll() is None:
                result['deadline_expired']=True;child.terminate();child.wait(timeout=10)
            result['sender_exit']=child.returncode
            time.sleep(3)
    finally:
        stop.set()
        if reader is not None:reader.join(timeout=2)
        port.close();result['owned_uart_closed']=True
        (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('OTA CAPTURE FINAL',json.dumps(result),flush=True)
    if result.get('uart_error') or result.get('sender_exit')!=0:raise RuntimeError('Inspect retained OTA/UART evidence; no automatic retry')

if __name__=='__main__':main()
