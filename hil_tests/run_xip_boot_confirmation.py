"""Confirm existing B13 without reflashing: signed header replay, then one reboot.

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
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    build=root/'.local-dependencies/xip/v13-B-reset-safe3';info=json.loads((build/'build.json').read_text())
    data=(build/'N6-XIP-B-v13.n6fw').read_bytes()
    assert hashlib.sha256(data).hexdigest()==info['hashes']['N6-XIP-B-v13.n6fw']['sha256'].lower()
    spec=importlib.util.spec_from_file_location('protocol',root/'hil_tests/run_xip_usb_reject.py')
    protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
    packets=[protocol.packet(data[:128],sequence=1),protocol.packet(data[128:256],sequence=2)]
    assert len(packets)==2 and all(len(x)==133 for x in packets)
    if args.preflight_only or not args.execute:
        print('HOST PREFLIGHT PASS exact signedB13 header256bytes only; no image data, no EOT or flash write')
        return
    import re,subprocess,threading,serial
    from serial.tools import list_ports
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
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
                assert 'Firmware version: 13\r\n' in result['before']['version']
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
                result['confirmed_version13_read_by_Secure']='[SECURE-UPDATE] confirmed version = 0x0000000D' in text
                assert result['confirmed_version13_read_by_Secure'],'Replay did not prove confirmed13; inspect state, do not reboot'
                print('PASS existing Secure metadata is CONFIRMED version13; authenticated replay rejected before erase',flush=True)
                port.reset_input_buffer();port.write(b'reboot yes\r');port.flush()
                result['reboot_command_sent']=True
                response=bytearray();deadline=time.monotonic()+2
                try:
                    while time.monotonic()<deadline:response.extend(port.read(4096))
                except (OSError,serial.SerialException):pass
                result['reboot_response']=response.decode('utf-8','replace')
            if 'Reset blocked.' not in result['reboot_response']:
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
            result['passed']=result['confirmed_version13_read_by_Secure'] and result['boot_confirmation_seen'] and not result['reset_blocked']
            if not result['passed']:result['blocker']='Inspect recorded mux preconditions/reset outcome; current image not reflashed'
    except BaseException as error:result['error']=repr(error);raise
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=2)
        uart.close();(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CONFIRMATION RESULT',json.dumps({k:v for k,v in result.items()if not isinstance(v,(dict,list))}),flush=True)


if __name__=='__main__':cli_main()
