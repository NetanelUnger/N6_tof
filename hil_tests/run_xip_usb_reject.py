"""Explicit safe USB negative tests: no complete authenticated manifest is sent.

Bad CRC, cancellation after128 manifest bytes, a truncated17byte packet, and
a bad signature in an otherwise valid B13 header. No valid256byte manifest,
EOT or reboot. Requires a shared lease and an explicit expected live version.
Extended timeout observation never relaxes the12second acceptance bound.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct
import time


def packet(payload, corrupt_crc=False, sequence=1):
    if len(payload) not in (128,1024):raise ValueError('XMODEM packet size')
    crc=binascii.crc_hqx(payload,0) ^ int(corrupt_crc)
    sequence&=255
    return bytes([1 if len(payload)==128 else 2,sequence,255-sequence])+payload+crc.to_bytes(2,'big')


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
    parser.add_argument('--expected-version',type=int,default=12)
    parser.add_argument('--case',choices=('all','bad-crc','cancel-partial-manifest','truncated-packet-timeout','bad-signature'),default='all')
    parser.add_argument('--timeout-observe-seconds',type=int,choices=range(12,26),default=12,
                        help='Diagnostic observation only; timeout case still must respond within12s to pass')
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
           ('truncated-packet-timeout',packet(data[:128])[:17],b'\x15'),
           ('bad-signature',packet(bytes(bad)),b'\x18\x18')]
    if args.case!='all':cases=[c for c in cases if c[0]==args.case]
    if args.preflight_only or not args.execute:
        print('HOST PREFLIGHT PASS original package hash/slot/version and CRC fixture; no valid manifest will be sent')
        return
    import re,subprocess,threading,serial
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/usb-reject-'+args.label);output.mkdir(exist_ok=False)
    result={'scope':f'Actual USB XMODEM negative tests from v{args.expected_version} XIP; no valid complete manifest/EOT/reset',
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
                assert f'Firmware version: {args.expected_version}\r\n' in result['before']['version']
                assert 'requested NONE, active NONE' in result['before']['tof status'] and 'ToF: sent 0' in result['before']['cloud status']
                assert 'Dataset stream: off' in result['before']['dataset stream status']
                for name,frame,expected in cases:
                    record={'name':name,'bytes_sent':len(frame),'passed':False};result['cases'].append(record)
                    port.reset_input_buffer();port.write(b'update\r');port.flush()
                    start=until(port,lambda b:b'Waiting: ' in b and b.endswith(b'C'))
                    record['start']=start.decode('ascii','replace');time.sleep(.5)
                    port.write(frame);port.flush()
                    observed_at=time.monotonic()
                    reply=until(port,lambda b:expected in b,args.timeout_observe_seconds if name=='truncated-packet-timeout' else 8)
                    record['response_seconds']=time.monotonic()-observed_at
                    record['control_reply_hex']=reply.hex()
                    if name!='bad-signature':port.write(b'\x18\x18');port.flush()
                    terminal=until(port,lambda b:b.endswith(b'n6> '))
                    record['terminal']=terminal.decode('utf-8','replace')
                    assert b'transfer cancelled or rejected' in terminal
                    record['version_after']=status(port,'version')
                    record['ping_after']=status(port,'debug ping 1959')
                    assert f'Firmware version: {args.expected_version}\r\n' in record['version_after'] and 'PONG 1959 ' in record['ping_after']
                    record['passed']=name!='truncated-packet-timeout' or record['response_seconds']<=12
                    if not record['passed']:raise RuntimeError('Diagnostic response arrived beyond unchanged12s acceptance bound; receiver cancelled and version checked')
                    print('PASS actual USB negative case',name,flush=True)
                time.sleep(.5)
                result['after']={command:status(port,command) for command in ['rps status','tof status','cloud status','dataset stream status']}
                assert 'errors=0' in result['after']['rps status'] and 'ToF state: ready' in result['after']['tof status']
                assert 'ToF: sent 0' in result['after']['cloud status'] and 'requested NONE, active NONE' in result['after']['tof status']
                assert 'Dataset stream: off' in result['after']['dataset stream status']
            stop.set();thread.join(timeout=2)
            log.flush()
            trace=(output/'uart.log').read_text(errors='replace')
            if any(c[0]=='bad-signature' for c in cases):
                assert '[SECURE-UPDATE] signature authentication failed' in trace,'Signature test did not reach authentication reject; inspect trace'
            if any(c[0]=='truncated-packet-timeout' for c in cases):
                assert 'packet timeout: collected=16 of 132 tail bytes' in trace,'Truncated packet did not reach the actual timeout path'
            result['passed']=True
    except BaseException as error:
        result['error']=repr(error);raise
    finally:
        stop.set()
        if thread is not None:thread.join(timeout=2)
        uart.close()
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',len(cases),'hardware USB negative cases; application remains alive, no sensor Cloud exports',flush=True)


if __name__=='__main__':cli_main()
