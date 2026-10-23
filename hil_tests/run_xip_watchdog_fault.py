"""One armed UART fault and actual hardware-reset observation, no reset retry.

Requires a confirmed matching watchdog USB install and existing exclusive lease.
No flash programmer, physical power operation, pairing or sensor route requested.
"""
def main():
    import argparse,hashlib,importlib.util,json,re,subprocess,threading,time
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--owner-thread')
    p.add_argument('--kind',choices=('uart','supervisor'),required=True)
    p.add_argument('--version',type=int,required=True);p.add_argument('--package',required=True)
    p.add_argument('--install-proof',required=True);p.add_argument('--label',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()=='feature/n6-xip-ota-usb'
    binary=(root/a.package).resolve();proof_path=(root/a.install_proof).resolve()
    assert binary.is_relative_to(root) and proof_path.is_relative_to(root)
    build=json.loads((binary.parent/'build.json').read_text(encoding='utf8'))
    proof=json.loads(proof_path.read_text(encoding='utf8'))
    assert build['watchdog'] and build['version']==a.version
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==build['hashes'][binary.name]['sha256'].lower()
    assert proof['passed'] and proof['target_version']==a.version and proof['boot_confirmation_seen']
    if not a.execute:print('PASS host admission; no hardware opened');return
    def load(n,path):
        s=importlib.util.spec_from_file_location(n,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert owner['thread']==a.owner_thread
    lease=load('wdtlease',root/'hil_tests/n6_hardware_lease.py');identity=lease.windows_process_identity(owner['pid'])
    assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    usb=load('wdtusb',root/'hil_tests/run_xip_usb_update.py')
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
    assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports)
    assert re.fullmatch('[a-z0-9-]+',a.label)
    out=root/('.local-dependencies/xip/watchdog-'+a.label);out.mkdir(exist_ok=False)
    result={'passed':False,'kind':a.kind,'software_reset_commands':0,'flash_writes_requested':False,
      'arm_bytes_sent':0,'fault_bytes_sent':0,'physical_power_cycle':False}
    uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
    uart.dtr=False;uart.rts=False;uart.port='COM6';stop=threading.Event();reader=None
    try:
        uart.open()
        with (out/'uart.log').open('xb') as log:
            def capture():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:log.write(data);log.flush()
                except BaseException as e:result['uart_error']=repr(e)
            reader=threading.Thread(target=capture);reader.start()
            def wait_text(key,seconds):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    text=(out/'uart.log').read_text(encoding='utf8',errors='replace')
                    if key in text:return text
                    time.sleep(.05)
                raise TimeoutError('No '+key+'; no automatic re-arm/fault/reset retry')
            with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                port.dtr=True;time.sleep(.3)
                result['before']={s:usb.command(port,s) for s in ['version','cloud disable','cloud status','dataset stream status','tof status','radio status']}
                assert f'Firmware version: {a.version}\r\n' in result['before']['version']
                assert 'Cloud Relay: disabled' in result['before']['cloud status']
                assert 'ToF: sent 0' in result['before']['cloud status'] and 'Dataset stream: off' in result['before']['dataset stream status']
                assert 'requested NONE, active NONE' in result['before']['tof status']
            target='UART-control-task' if a.kind=='uart' else 'supervisor-task'
            print('CAPTURE READY before fault; UART exclusive, USB closed, no flash write',flush=True)
            uart.write(b'w' if a.kind=='uart' else b's');uart.flush();result['arm_bytes_sent']=1
            wait_text('ARM target='+target,3)
            fault_at=time.monotonic();uart.write(b'W');uart.flush();result['fault_bytes_sent']=1
            wait_text('FAULT target='+target,3)
            usb.wait_usb_disconnect(list_ports.comports,seconds=40)
            result['USB_disconnect_seconds_after_W']=time.monotonic()-fault_at
            print('WATCHDOG USB disconnect observed',result['USB_disconnect_seconds_after_W'],flush=True)
            deadline=time.monotonic()+65
            while not any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports()):
                if time.monotonic()>deadline:raise TimeoutError('USB absent after watchdog; no reset/debugger attempted')
                time.sleep(.1)
            text=wait_text('[WDT] HEALTHY required=',55)
            assert '[FSBL] entered from BootROM' in text
            assert '[UPDATE] boot confirmed; rollback window closed' in text
            assert re.search(r'\[WDT\] reset RSR=[0-9A-F]+ IWDG=1;',text),'No actual IWDG reset flag'
            if a.kind=='uart':assert '[WDT] TASK STALE mask=002;' in text
            result['IWDG_reset_cause']=True;result['boot_confirmation_seen']=True
            with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                port.dtr=True;time.sleep(.3)
                result['after']={s:usb.command(port,s) for s in ['version','debug ping 4141','tof status','rps status','cloud disable','cloud status','dataset stream status','radio status','debug resources']}
            assert f'Firmware version: {a.version}\r\n' in result['after']['version'] and 'PONG 4141 ' in result['after']['debug ping 4141']
            assert 'ToF state: ready' in result['after']['tof status'] and 'errors=0' in result['after']['rps status']
            assert 'SPI fault: count=0' in result['after']['radio status'] and 'ToF: sent 0' in result['after']['cloud status']
            assert 'Dataset stream: off' in result['after']['dataset stream status']
            # Retain the bounded resource snapshot stream after USB is closed.
            time.sleep(12)
            result['passed']=True
            print('PASS hardware IWDG cause, boot/confirmation/USB/ToF/NPU/radio; no whole-board power-cycle claim',flush=True)
    except BaseException as e:result['error']=repr(e);raise
    finally:
        stop.set()
        if reader is not None:reader.join(timeout=2)
        uart.close();result['owned_handles_closed']=True
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
