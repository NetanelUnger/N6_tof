"""Bounded existing USB CLI status; no reset, update or sensor stream commands."""
def main():
    import argparse,importlib.util,json,re,subprocess,time
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread');parser.add_argument('--label')
    parser.add_argument('--expected-version',type=int)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if not args.execute:print('PASS USB status preflight; no external action');return
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid'])
    assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/status-'+args.label+'.json');assert not output.exists()
    import serial
    from serial.tools import list_ports
    ports=list(list_ports.comports())
    assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports)
    result={}
    try:
        with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
            port.dtr=True;time.sleep(.3)
            for line in ['version','debug ping 1417','tof status','rps status','debug uart','radio status','ble status','wifi status','cloud status','dataset stream status']:
                port.reset_input_buffer();port.write((line+'\r').encode());port.flush()
                data=bytearray();deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    data.extend(port.read(8192))
                    if data.endswith(b'n6> '):break
                result[line]=data.decode('utf8','replace')
                assert data.endswith(b'n6> '),'Incomplete CLI response: '+line
                print(line,ascii(result[line][:210]),flush=True)
        assert f'Firmware version: {args.expected_version}\r\n' in result['version']
        assert 'requested NONE, active NONE' in result['tof status']
        assert 'ToF: sent 0' in result['cloud status'] and 'Dataset stream: off' in result['dataset stream status']
        result['passed']=True
    finally:output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('PASS current USB version/health/no sensor exports; COM closed',flush=True)
if __name__=='__main__':main()
