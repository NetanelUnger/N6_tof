"""Explicit safe USB negative tests: no complete authenticated manifest is sent.

Bad CRC, sender cancellation after128 manifest bytes, and a bad signature in
an otherwise valid B13 header. Never sends a valid256-byte manifest, EOT or
reboot command. Requires the separately held shared lease and healthy A12.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct
import time


def packet(payload, corrupt_crc=False):
    if len(payload) not in (128,1024):raise ValueError('XMODEM packet size')
    crc=binascii.crc_hqx(payload,0) ^ int(corrupt_crc)
    return bytes([1 if len(payload)==128 else 2,1,254])+payload+crc.to_bytes(2,'big')


def until(port,predicate,seconds=8):
    data=bytearray();deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        data.extend(port.read(1))
        if predicate(bytes(data)):return bytes(data)
        if len(data)>65536:raise RuntimeError('Bounded response overflow')
    raise TimeoutError('Expected response missing: '+repr(bytes(data)[-700:]))


def status(port,command):
    port.reset_input_buffer();port.write((command+'\r').encode());port.flush()
    return until(port,lambda b:b.endswith(b'n6> '),5).decode('utf-8','replace')


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--label')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    build=root/'.local-dependencies/xip/v13-B-abi-compat4'
    info=json.loads((build/'build.json').read_text())
    name='N6-XIP-B-v13.n6fw';data=(build/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==info['hashes'][name]['sha256'].lower()
    assert len(data)==498336 and struct.unpack_from('<I',data,20)[0]==13 and struct.unpack_from('<I',data,24)[0]==2
    assert binascii.crc_hqx(b'123456789',0)==0x31c3
    bad=bytearray(data[:1024]);bad[60]^=1
    cases=[('bad-crc',packet(data[:128],True),b'\x15'),
           ('cancel-partial-manifest',packet(data[:128]),b'\x06'),
           ('bad-signature',packet(bytes(bad)),b'\x18\x18')]
    if args.preflight_only or not args.execute:
        print('HOST PREFLIGHT PASS original package hash/slot/version and CRC fixture; no valid manifest will be sent')
        return
    import re,subprocess,threading,serial
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/usb-reject-'+args.label);output.mkdir(exist_ok=False)
    result={'scope':'Actual USB XMODEM negative tests from A12 XIP; no valid complete manifest/EOT/reset',
            'package_sha256':hashlib.sha256(data).hexdigest(),'cases':[],'passed':False,'NOR_independent_read':'Not performed during NS runtime'}
    uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
    uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    stop=threading.Event();thread=None
    try:
        with (output/'uart.log').open('xb') as log:
            def collect():
                while not stop.is_set():
                    part=uart.read(8192)
                    if part:log.write(part);log.flush()
            thread=threading.Thread(target=collect);thread.start()
            with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
                port.dtr=True;time.sleep(.3)
                result['before']={command:status(port,command) for command in ['version','debug ping 1959','rps status','tof status','cloud status','dataset stream status']}
                assert 'Firmware version: 12\r\n' in result['before']['version']
                assert 'requested NONE, active NONE' in result['before']['tof status'] and 'ToF: sent 0' in result['before']['cloud status']
                assert 'Dataset stream: off' in result['before']['dataset stream status']
                for name,frame,expected in cases:
                    record={'name':name,'bytes_sent':len(frame),'passed':False};result['cases'].append(record)
                    port.reset_input_buffer();port.write(b'update\r');port.flush()
                    start=until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
                    record['start']=start.decode('ascii','replace');time.sleep(.5)
                    port.write(frame);port.flush()
                    reply=until(port,lambda b:expected in b)
                    record['control_reply_hex']=reply.hex()
                    if name!='bad-signature':port.write(b'\x18\x18');port.flush()
                    terminal=until(port,lambda b:b.endswith(b'n6> '))
                    record['terminal']=terminal.decode('utf-8','replace')
                    assert b'transfer cancelled or rejected' in terminal
                    record['version_after']=status(port,'version')
                    record['ping_after']=status(port,'debug ping 1959')
                    assert 'Firmware version: 12\r\n' in record['version_after'] and 'PONG 1959 ' in record['ping_after']
                    record['passed']=True;print('PASS actual USB negative case',name,flush=True)
                time.sleep(.5)
                result['after']={command:status(port,command) for command in ['rps status','tof status','cloud status','dataset stream status']}
                assert 'errors=0' in result['after']['rps status'] and 'ToF state: ready' in result['after']['tof status']
                assert 'ToF: sent 0' in result['after']['cloud status'] and 'requested NONE, active NONE' in result['after']['tof status']
                assert 'Dataset stream: off' in result['after']['dataset stream status']
            stop.set();thread.join(timeout=2)
            log.flush()
            trace=(output/'uart.log').read_text(errors='replace')
            assert '[SECURE-UPDATE] signature authentication failed' in trace,'Signature test did not reach authentication reject; inspect trace'
            result['passed']=True
    except BaseException as error:
        result['error']=repr(error);raise
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=2)
        uart.close()
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS three hardware USB negative cases; application remains alive, no sensor Cloud exports',flush=True)


if __name__=='__main__':cli_main()
