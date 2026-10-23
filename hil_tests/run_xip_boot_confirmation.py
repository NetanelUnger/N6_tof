"""Confirm existing B13/A14 with header-only replay; optionally one explicit reboot.

Only256 manifest bytes are sent, in two128-byte packets. Even an unexpected
accept cannot erase/program an image because no image byte/EOT is submitted.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--label')
    parser.add_argument('--version',type=int,choices=(13,14),default=13)
    parser.add_argument('--reboot',action='store_true',help='Explicit single reboot after confirmed metadata proof')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    version=args.version
    directory,name=('v13-B-reset-safe3','N6-XIP-B-v13.n6fw') if version==13 else ('v14-A-reset-clkp','N6-XIP-A-v14.n6fw')
    build=root/('.local-dependencies/xip/'+directory);info=json.loads((build/'build.json').read_text())
    data=(build/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==info['hashes'][name]['sha256'].lower()
    spec=importlib.util.spec_from_file_location('protocol',root/'hil_tests/run_xip_usb_reject.py')
    protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
    packets=[protocol.packet(data[:128],sequence=1),protocol.packet(data[128:256],sequence=2)]
    assert len(packets)==2 and all(len(x)==133 for x in packets)
    if args.preflight_only or not args.execute:
        print(f'HOST PREFLIGHT PASS exact signedV{version} header256bytes only; no image data/EOT; reboot={args.reboot}, no hardware opened')
        return
    import re,subprocess,threading,serial
    from serial.tools import list_ports
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    lease_spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(lease_spec);lease_spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid'])
    assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    ports=list(list_ports.comports())
    assert any(p.device=='COM6' and p.serial_number=='000C00344142501620353451' for p in ports)
    assert any(p.device=='COM8' and p.serial_number=='N6TOF001' for p in ports)
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/confirmation-'+args.label);output.mkdir(exist_ok=False)
    result={'image_bytes_sent':0,'EOT_sent':False,'passed':False,'new_image_transfer':False}
    stop=threading.Event();thread=None
    uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
    uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    try:
        with (output/'uart.log').open('xb') as trace:
            def collect():
                while not stop.is_set():
                    part=uart.read(8192)
                    if part:trace.write(part);trace.flush()
            thread=threading.Thread(target=collect);thread.start()
            with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                port.dtr=True;time.sleep(.3)
                result['before']={cmd:protocol.status(port,cmd) for cmd in ['version','rps status','tof status','cloud status']}
                assert f'Firmware version: {version}\r\n' in result['before']['version']
                assert 'ToF: sent 0' in result['before']['cloud status'] and 'errors=0' in result['before']['rps status']
                port.write(b'update\r');port.flush()
                protocol.until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'));time.sleep(.5)
                port.write(packets[0]);port.flush();protocol.until(port,lambda b:b'\x06' in b)
                port.write(packets[1]);port.flush()
                reply=protocol.until(port,lambda b:b'\x18\x18' in b or b'\x06' in b)
                result['replay_control']=reply.hex()
                if b'\x06' in reply:
                    port.write(b'\x18\x18');port.flush()
                    raise RuntimeError('Unexpected replay accept; no image bytes sent, session cancelled')
                protocol.until(port,lambda b:b.endswith(b'n6> '));time.sleep(.5)
                trace.flush();text=(output/'uart.log').read_text(errors='replace')
                result['confirmed_version_read_by_Secure']=f'[SECURE-UPDATE] confirmed version = 0x{version:08X}' in text
                result['confirmed_version']=version
                assert result['confirmed_version_read_by_Secure'],'Replay did not prove expected confirmed version; do not reboot'
                print(f'PASS Secure metadata CONFIRMED version{version}; replay rejected before erase',flush=True)
                if args.reboot:
                    port.reset_input_buffer();port.write(b'reboot yes\r');port.flush()
                result['reboot_command_sent']=args.reboot
                response=bytearray();deadline=time.monotonic()+2
                try:
                    while args.reboot and time.monotonic()<deadline:response.extend(port.read(4096))
                except (OSError,serial.SerialException):pass
                result['reboot_response']=response.decode('utf-8','replace')
            if args.reboot and 'Reset blocked.' not in result['reboot_response']:
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    time.sleep(.25);trace.flush()
                    if 'boot confirmed; rollback window closed' in (output/'uart.log').read_text(errors='replace'):break
            result['after_ports']=[p.device for p in list_ports.comports()]
            if 'COM8' in result['after_ports']:
                with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                    port.dtr=True;time.sleep(.2)
                    result['after']={cmd:protocol.status(port,cmd) for cmd in ['version','rps status','tof status','cloud status']}
            stop.set();thread.join(timeout=2);trace.flush();text=(output/'uart.log').read_text(errors='replace')
            result['PC_VTOR_lines']=[line for line in text.splitlines() if '[RESET]' in line]
            result['boot_confirmation_seen']='boot confirmed; rollback window closed' in text
            result['reset_blocked']='Reset blocked.' in result['reboot_response']
            result['passed']=result['confirmed_version_read_by_Secure'] and (not args.reboot or result['boot_confirmation_seen']) and not result['reset_blocked']
            if not result['passed']:result['blocker']='Inspect recorded mux preconditions/reset outcome; current image not reflashed'
    except BaseException as error:result['error']=repr(error);raise
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=2)
        uart.close();(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CONFIRMATION RESULT',json.dumps({k:v for k,v in result.items()if not isinstance(v,(dict,list))}),flush=True)


if __name__=='__main__':cli_main()
