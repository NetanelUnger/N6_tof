"""One owned software reset with passive boot proof; never a cold-power test.

Default preflight opens no hardware. After command submission there is no reset
retry. Requires a completed matching OTA proof, and keeps all sensor routes off.
"""
def main():
    import argparse,hashlib,importlib.util,json,re,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--owner-thread');p.add_argument('--version',type=int,required=True)
    p.add_argument('--package',required=True);p.add_argument('--ota-proof',required=True);p.add_argument('--label',required=True);a=p.parse_args()
    if not a.execute:print('PASS software-reset preflight; no hardware/network/subprocess');return
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    binary=(root/a.package).resolve();proof_path=(root/a.ota_proof).resolve()
    assert binary.is_relative_to(root) and proof_path.is_relative_to(root)
    meta=json.loads((binary.parent/'build.json').read_text(encoding='utf-8'));proof=json.loads(proof_path.read_text(encoding='utf-8'))
    assert meta['version']==a.version and hashlib.sha256(binary.read_bytes()).hexdigest()==meta['hashes'][binary.name]['sha256'].lower()
    assert proof['passed'] and proof['targetRunning'] and proof['targetVersion']==a.version
    def load(n,p):
        s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text());assert a.owner_thread==owner['thread']
    lease=load('rebootlease',root/'hil_tests/n6_hardware_lease.py');i=lease.windows_process_identity(owner['pid']);assert i['state']=='alive' and i['created_utc']==owner['process_created_utc']
    usb=load('rebootusb',root/'hil_tests/run_xip_usb_update.py')
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports)
    assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
    assert re.fullmatch('[a-z0-9-]+',a.label)
    out=root/('.local-dependencies/xip/software-reboot-'+a.label);out.mkdir(exist_ok=False)
    result={'passed':False,'reset_commands_sent':0,'physical_power_cycle':False,'image_program_requested':False}
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1);uart.dtr=False;uart.rts=False;uart.port='COM6'
    stop=threading.Event();reader=None
    try:
        uart.open()
        with (out/'uart.log').open('xb') as log:
            def collect():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:log.write(data);log.flush()
                except BaseException as e:result['uart_error']=repr(e)
            reader=threading.Thread(target=collect);reader.start()
            try:
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.3)
                    result['before']={s:usb.command(port,s) for s in ['version','tof status','cloud disable','cloud status','dataset stream status']}
                    assert f'Firmware version: {a.version}\r\n' in result['before']['version']
                    assert 'ToF: sent 0' in result['before']['cloud status'] and 'Dataset stream: off' in result['before']['dataset stream status']
                    assert 'requested NONE, active NONE' in result['before']['tof status']
                    port.write(b'reboot yes\r');port.flush();result['reset_commands_sent']=1
                    print('ONE software reboot command submitted; no retry, not a cold boot.',flush=True)
                usb.wait_usb_disconnect(list_ports.comports,seconds=10);result['USB_disconnect_seen']=True
                deadline=time.monotonic()+40
                while not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports()):
                    if time.monotonic()>deadline:raise TimeoutError('USB did not return; no new reset or debugger attempted')
                    time.sleep(.1)
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.3)
                    result['after']={s:usb.command(port,s) for s in ['version','debug ping 3901','tof status','rps status','cloud disable','cloud status','dataset stream status','radio status']}
                    assert f'Firmware version: {a.version}\r\n' in result['after']['version'] and 'PONG 3901 ' in result['after']['debug ping 3901']
                while time.monotonic()<deadline:
                    text=(out/'uart.log').read_text(errors='replace')
                    if '[UPDATE] boot confirmed; rollback window closed' in text:break
                    time.sleep(.1)
                text=(out/'uart.log').read_text(errors='replace')
                assert '[FSBL] entered from BootROM' in text
                m=re.search(r'update metadata: seq=(\d+) state=1 confirmed=(\d+)/v'+str(a.version),text)
                assert m,'Current confirmed version not observed at persistent boot'
                pc=re.findall(r'CPU PC=([0-9A-Fa-f]{8}) VTOR=([0-9A-Fa-f]{8})',text);assert pc
                result['PC'],result['VTOR']=pc[-1];assert 0x70000000<=int(result['PC'],16)<0x70400000
                assert '[UPDATE] boot confirmed; rollback window closed' in text
                result['metadata_sequence_at_boot']=int(m[1]);result['slot']=int(m[2])
                assert 'SPI fault: count=0' in result['after']['radio status'] and 'ToF: sent 0' in result['after']['cloud status']
                result['passed']=True;print('PASS actual software reboot/current confirmed metadata/XIP PC/USB version, no physical power claim',flush=True)
            finally:stop.set();reader.join(timeout=2)
    except BaseException as e:result['error']=repr(e);raise
    finally:
        stop.set()
        if reader is not None:reader.join(timeout=2)
        uart.close();result['owned_handles_closed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
