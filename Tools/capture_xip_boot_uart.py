"""Bounded passive ST-LINK UART capture; never writes serial or resets/debugs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--seconds',type=int,default=1200)
    parser.add_argument('--dtr',type=int,choices=(0,1),default=0,
                        help='ST-LINK host handshake only; USART1 has no flow-control wiring')
    args=parser.parse_args()
    if args.preflight_only:
        print('PASS passive recorder import/preflight; no external action')
        return
    import msvcrt
    import os
    import serial
    import subprocess
    from serial.tools import list_ports
    root=Path(__file__).resolve().parents[1]
    git=['git','-c','safe.directory='+str(root),'-C',str(root)]
    if subprocess.check_output(git+['branch','--show-current'],text=True).strip()!='feature/n6-xip-ota-usb':
        raise RuntimeError('Wrong branch')
    if not args.owner_thread or not args.output or not 30<=args.seconds<=1800:
        raise RuntimeError('Owner, fresh output and bounded30..1800seconds required')
    output=args.output.resolve()
    if not output.is_relative_to(root):raise RuntimeError('Output outside feature worktree')
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics'
    marker=folder/'n6-hardware-owner.lock';status=folder/'n6-hardware-owner.json'
    if marker.exists() or status.exists():raise RuntimeError('Existing hardware owner; no port opened')
    output.mkdir(parents=True,exist_ok=False)
    owner={'thread':args.owner_thread,'pid':os.getpid(),'started_utc':datetime.now(timezone.utc).isoformat(),
           'scope':'XIP passive COM6 UART capture only; no serial writes, debugger, resets or flash activity'}
    lock=marker.open('x+b');published=False;port=None
    try:
        lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with status.open('x',encoding='utf-8') as f:json.dump(owner,f)
        published=True
        ports=list(list_ports.comports())
        matches=[p for p in ports if p.device=='COM6' and p.serial_number=='000C00344142501620353451']
        if len(matches)!=1:raise RuntimeError('Exact ST-LINK COM6 identity not present; no port opened')
        port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1)
        port.dtr=bool(args.dtr);port.rts=False;port.port='COM6';port.open()
        started=time.monotonic();last=started;count=0
        evidence={**owner,'status':'READY','port':'COM6','baud':115200,'serial_number':matches[0].serial_number,
                  'dtr':bool(args.dtr),'rts':False,'maximum_seconds':args.seconds,'serial_writes':0,
                  'bytes':0,'waiting_for_physical_change':True}
        (output/'ready.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print('CAPTURE_READY '+json.dumps(evidence),flush=True)
        with (output/'uart.log').open('wb') as raw:
            # A later authorized owner can stop this exact recorder without
            # sending stdin to an unidentified terminal or killing a process.
            while time.monotonic()-started<args.seconds and not (output/'stop.request').exists():
                data=port.read(8192)
                if data:raw.write(data);raw.flush();count+=len(data)
                if time.monotonic()-last>=5:
                    evidence.update(status='CAPTURING',bytes=count,elapsed_seconds=round(time.monotonic()-started,3),
                                    last_heartbeat_utc=datetime.now(timezone.utc).isoformat())
                    (output/'status.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
                    last=time.monotonic()
        evidence.update(status='STOP_REQUESTED' if (output/'stop.request').exists() else 'BOUNDED_CAPTURE_COMPLETE',
                        bytes=count,elapsed_seconds=round(time.monotonic()-started,3))
        (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print('CAPTURE_COMPLETE '+json.dumps(evidence),flush=True)
    finally:
        if port is not None and port.is_open:port.close()
        lock.close();marker.unlink()
        if published and status.exists() and json.loads(status.read_text())==owner:status.unlink()
        print('OWNED_UART_AND_LEASE_RELEASED',flush=True)


if __name__=='__main__':cli_main()
