"""Read-only USB PONG clock comparison against host monotonic time."""
def main():
    import argparse,importlib.util,json,re,subprocess,time
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread');parser.add_argument('--label');args=parser.parse_args()
    if not args.execute:print('PASS clock preflight; no hardware');return
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text());assert args.owner_thread==owner['thread']
    spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py');lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    ident=lease.windows_process_identity(owner['pid']);assert ident['state']=='alive' and ident['created_utc']==owner['process_created_utc']
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/clock-'+args.label+'.json');assert not output.exists()
    import serial
    from serial.tools import list_ports
    assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in list_ports.comports())
    result={'samples':[],'NOR_write':False,'reset':False}
    try:
        with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
            port.dtr=True;time.sleep(.3)
            for i in range(6):
                token='CLOCK-'+str(i);port.reset_input_buffer();start=time.monotonic_ns();port.write(('debug ping '+token+'\r').encode());port.flush()
                data=bytearray();deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    data.extend(port.read(4096))
                    if data.endswith(b'n6> '):break
                end=time.monotonic_ns();match=re.search(rb'PONG CLOCK-\d+ (\d+)',data);assert match
                result['samples'].append({'device_ms':int(match[1]),'host_midpoint_ns':(start+end)//2,'RTT_ms':(end-start)/1e6})
                print('CLOCK',result['samples'][-1],flush=True)
                if i<5:time.sleep(2)
        first,last=result['samples'][0],result['samples'][-1]
        result['host_elapsed_ms']=(last['host_midpoint_ns']-first['host_midpoint_ns'])/1e6
        result['device_elapsed_ms']=(last['device_ms']-first['device_ms'])&0xffffffff
        result['device_host_ratio']=result['device_elapsed_ms']/result['host_elapsed_ms']
    finally:output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print('CLOCK ratio',result['device_host_ratio'],flush=True)
if __name__=='__main__':main()
