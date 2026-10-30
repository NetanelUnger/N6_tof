"""Bounded local timebase diagnosis; no clock change, signed image or NOR write.

Requires the exact confirmed A34 diagnostic package. Each phase has a finite
30sample firmware watch; interrupted packet recovery uses a badCRC tail then
CAN, or closes USB on failure. No debugger, reset or network request.
"""
def main():
    import argparse,hashlib,importlib.util,json,re,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--owner-thread');p.add_argument('--label',required=True)
    p.add_argument('--version',type=int,default=34)
    p.add_argument('--build',default='.local-dependencies/xip/v34-A-timebase-probe-repaired')
    p.add_argument('--boot-proof',default='.local-dependencies/xip/usb-update-a34-timebase-probe/result.json');a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    build=(root/a.build).resolve();assert build.is_relative_to(root);meta=json.loads((build/'build.json').read_text())
    package=build/f'N6-XIP-{meta["slot"]}-v{a.version}.n6fw';assert hashlib.sha256(package.read_bytes()).hexdigest()==meta['hashes'][package.name]['sha256'].lower()
    proof_path=(root/a.boot_proof).resolve();assert proof_path.is_relative_to(root);proof=json.loads(proof_path.read_text())
    assert proof['passed'] and proof['target_version']==a.version and proof['boot_confirmation_seen']
    assert re.fullmatch('[a-z0-9-]+',a.label)
    print(f'HOST PREFLIGHT PASS exact confirmed{a.version}, local watch only, no NOR/reset/network',flush=True)
    if not a.execute:return
    def load(n,p):
        s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    lease=load('timelease',root/'hil_tests/n6_hardware_lease.py')
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert a.owner_thread and a.owner_thread==owner['thread']
    ident=lease.windows_process_identity(owner['pid']);assert ident['state']=='alive' and ident['created_utc']==owner['process_created_utc']
    protocol=load('timeprotocol',root/'hil_tests/run_xip_usb_reject.py')
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports());assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports)
    assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
    out=root/('.local-dependencies/xip/timebase-'+a.label);out.mkdir(exist_ok=False)
    result={'network':False,'NOR_write':False,'clock_configuration_changes':False,'phases':[]}
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6'
    stop=threading.Event();reader=None
    try:
        uart.open()
        with (out/'uart.log').open('xb') as log,(out/'arrivals.jsonl').open('x',encoding='utf-8') as arrivals:
            def collect():
                try:
                    offset=0
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:
                            arrivals.write(json.dumps({'host_monotonic':time.monotonic(),'offset':offset,'length':len(data)})+'\n');arrivals.flush()
                            log.write(data);log.flush();offset+=len(data)
                except BaseException as e:result['uart_error']=repr(e)
            reader=threading.Thread(target=collect);reader.start()
            try:
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.3)
                    before={s:protocol.status(port,s) for s in ['version','cloud disable','tof status','dataset stream status','cloud status']}
                    assert f'Firmware version: {a.version}\r\n' in before['version'] and 'ToF: sent 0' in before['cloud status']
                    assert 'Dataset stream: off' in before['dataset stream status'] and 'requested NONE, active NONE' in before['tof status']
                    result['before']=before
                    def cmd(s,phase):
                        v=protocol.status(port,s);phase.setdefault('commands',[]).append({'line':s,'host_monotonic':time.monotonic(),'reply':v});return v
                    idle={'name':'active-paused-active','started':time.monotonic()};result['phases'].append(idle)
                    cmd('debug timeprobe',idle);time.sleep(3);cmd('tof pause',idle);time.sleep(9)
                    idle['paused_status']=cmd('tof status',idle);assert 'ToF state: paused' in idle['paused_status']
                    cmd('debug ping 3401',idle);cmd('tof resume',idle)
                    while time.monotonic()-idle['started']<32:time.sleep(.25)
                    print('PASS first32second observation; ToF resumed, firmware watch expired.',flush=True)
                    phase={'name':'truncated-packet','started':time.monotonic()};result['phases'].append(phase)
                    cmd('debug timeprobe',phase)
                    port.reset_input_buffer();port.write(b'update\r');port.flush()
                    protocol.until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
                    old=(root/'.local-dependencies/xip/v13-B-abi-compat4/N6-XIP-B-v13.n6fw').read_bytes()
                    frame=protocol.packet(old[:128],corrupt_crc=True)
                    port.write(frame[:17]);port.flush();phase['partial_sent_at']=time.monotonic();data=bytearray()
                    while time.monotonic()-phase['partial_sent_at']<12:
                        data.extend(port.read(64))
                        if b'\x15' in data:phase['NAK_seconds']=time.monotonic()-phase['partial_sent_at'];break
                    phase['wire_hex_before_recovery']=data.hex();phase['wall_timeout_within12s']=b'\x15' in data
                    if not phase['wall_timeout_within12s']:
                        port.write(frame[17:]);port.flush()
                        phase['badCRC_tail_reply']=protocol.until(port,lambda b:b'\x15' in b or b'\x18\x18' in b,5).hex()
                    port.write(b'\x18\x18');port.flush()
                    phase['terminal']=protocol.until(port,lambda b:b.endswith(b'n6> '),5).decode('utf-8','replace')
                    assert 'transfer cancelled or rejected' in phase['terminal']
                    phase['version_after']=cmd('version',phase);phase['ping_after']=cmd('debug ping 3402',phase)
                    assert f'Firmware version: {a.version}\r\n' in phase['version_after'] and 'PONG 3402 ' in phase['ping_after']
                    phase['parser_recovery_without_DTR_close']=True
                    while time.monotonic()-phase['started']<32:time.sleep(.25)
                    result['after']={s:protocol.status(port,s) for s in ['version','tof status','rps status','radio status','debug uart','cloud status','dataset stream status']}
                    assert 'ToF: sent 0' in result['after']['cloud status'] and 'ToF state: ready' in result['after']['tof status']
                    print('OBSERVATION',json.dumps({k:v for k,v in phase.items() if k not in ('commands','terminal','version_after','ping_after')}),flush=True)
            finally:stop.set();reader.join(timeout=2)
    except BaseException as e:result['error']=repr(e);raise
    finally:
        stop.set()
        if reader is not None:reader.join(timeout=2)
        uart.close();result['owned_handles_closed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    text=(out/'uart.log').read_text(errors='replace')
    result['TIME_rows']=[[int(x,16) for x in m.split()] for m in re.findall(r'\[TIME\] ((?:[0-9A-F]{8} ){8})',text)]
    result['TIMER_rows']=[[int(x,16) for x in m.split()] for m in re.findall(r'\[TIMER\] ((?:[0-9A-F]{8} ){8})',text)]
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Capture closed TIME/TIMER rows',len(result['TIME_rows']),len(result['TIMER_rows']),flush=True)
if __name__=='__main__':main()
