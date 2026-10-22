"""Bounded passive ST-LINK UART capture; never writes serial or resets/debugs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time


def save_status(output, name, value):
    temporary=output/(name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    temporary.replace(output/name)


def receive_bounded(port, output, evidence, seconds, now=time.monotonic,
                    emit=print, sleep=time.sleep, reconnect=None,
                    disconnected=lambda error:False, stopping=lambda:False):
    """Injected serial source/clock allow complete host-only failure tests.

    A normal finally cannot survive TerminateProcess or a machine shutdown.
    Missing result/stale heartbeat must therefore remain an unknown outcome.
    """
    if not 0<seconds<=300:raise ValueError('Capture window must be <=300seconds')
    started=now();last=started;count=0;connection=port;generation=0
    try:
        with (output/'uart.log').open('xb') as raw:
            while now()-started<seconds and not (output/'stop.request').exists() and not stopping():
                if connection is None:
                    connection=reconnect() if reconnect else None
                    if connection is None:sleep(.2)
                    else:
                        generation+=1;evidence['reconnections']=generation
                if connection is not None:
                    try:
                        data=connection.read(8192)
                    except (OSError,RuntimeError) as error:
                        if isinstance(error,PermissionError) or getattr(error,'winerror',None)==5 or 'denied' in str(error).lower():raise
                        if not reconnect or not disconnected(error):raise
                        # Do not open a replacement until the old handle closes.
                        closing=connection;connection=None
                        try:closing.close()
                        except BaseException as close_error:
                            evidence.update(owned_port_close_returned=False,close_error=repr(close_error)[:500])
                            raise
                        evidence.update(status='WAITING_FOR_RECONNECT',last_disconnect=str(error)[:300])
                        save_status(output,'status.json',evidence)
                    else:
                        if data:raw.write(data);raw.flush();count+=len(data)
                if now()-last>=5:
                    evidence.update(status='CAPTURING' if connection else 'WAITING_FOR_RECONNECT',
                                    bytes=count,elapsed_seconds=round(now()-started,3),
                                    last_heartbeat_utc=datetime.now(timezone.utc).isoformat())
                    save_status(output,'status.json',evidence)
                    try:emit('CAPTURE_HEARTBEAT '+json.dumps(evidence),flush=True)
                    except BrokenPipeError:pass
                    last=now()
        evidence.update(status='STOP_REQUESTED' if (output/'stop.request').exists() or stopping() else 'BOUNDED_CAPTURE_COMPLETE')
        return evidence
    except BaseException as error:
        evidence.update(status='ABORTED',error_type=type(error).__name__,error=str(error)[:500])
        raise
    finally:
        evidence.update(bytes=count,elapsed_seconds=round(now()-started,3),port_free_verified=False)
        try:
            if connection is not None:
                connection.close()
            if 'close_error' not in evidence:evidence['owned_port_close_returned']=True
        except BaseException as error:
            evidence.update(owned_port_close_returned=False,close_error=repr(error)[:500],status='ABORTED')
        save_status(output,'result.json',evidence)


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--seconds',type=int,default=300)
    # Active DTR was denied; retain only the previously approved passive mode.
    parser.add_argument('--dtr',type=int,choices=(0,),default=0)
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
    if not args.owner_thread or not args.output or not 30<=args.seconds<=300:
        raise RuntimeError('Owner, fresh output and bounded30..300seconds required')
    output=args.output.resolve()
    if not output.is_relative_to(root):raise RuntimeError('Output outside feature worktree')
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics'
    marker=folder/'n6-hardware-owner.lock';status=folder/'n6-hardware-owner.json'
    if marker.exists() or status.exists() or (folder/'n6-hardware-recovery.lock').exists():
        raise RuntimeError('Existing hardware owner/recovery; no port opened')
    output.mkdir(parents=True,exist_ok=False)
    owner={'thread':args.owner_thread,'pid':os.getpid(),'started_utc':datetime.now(timezone.utc).isoformat(),
           'scope':'XIP passive COM6 UART capture only; no serial writes, debugger, resets or flash activity'}
    import importlib.util
    spec=importlib.util.spec_from_file_location('capture_lease',root/'hil_tests/n6_hardware_lease.py')
    lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(os.getpid())
    if identity.get('state')!='alive':raise RuntimeError('Cannot verify own process creation identity')
    owner['process_created_utc']=identity['created_utc']
    lock=marker.open('x+b');published=False;port=None;evidence={**owner,'status':'STARTING','serial_writes':0}
    import signal
    signals=[];old_signals={}
    def stopped(number,frame):signals.append(number)
    try:
        for number in (signal.SIGINT,signal.SIGTERM):
            old_signals[number]=signal.signal(number,stopped)
        lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with status.open('x',encoding='utf-8') as f:json.dump(owner,f)
        published=True
        def open_exact(initial=False):
            matches=[p for p in list_ports.comports() if p.device=='COM6' and p.serial_number=='000C00344142501620353451']
            if len(matches)!=1:
                if initial:raise RuntimeError('Exact ST-LINK COM6 identity absent; no port opened')
                return None
            candidate=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1)
            candidate.dtr=False;candidate.rts=False;candidate.port='COM6'
            # Any open error, including access denied, aborts; never retry it.
            candidate.open()
            return candidate
        def disconnected(error):
            if isinstance(error,PermissionError) or getattr(error,'winerror',None)==5 or 'denied' in str(error).lower():return False
            return not any(p.serial_number=='000C00344142501620353451' for p in list_ports.comports())
        port=open_exact(initial=True)
        evidence={**owner,'status':'READY','port':'COM6','baud':115200,'serial_number':'000C00344142501620353451',
                  'dtr':bool(args.dtr),'rts':False,'maximum_seconds':args.seconds,'serial_writes':0,
                  'bytes':0,'waiting_for_physical_change':True}
        (output/'ready.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print('CAPTURE_READY '+json.dumps(evidence),flush=True)
        receive_bounded(port,output,evidence,args.seconds,reconnect=open_exact,disconnected=disconnected,stopping=lambda:bool(signals))
        print('CAPTURE_COMPLETE '+json.dumps(evidence),flush=True)
    except BaseException as error:
        evidence.update(status='ABORTED',error_type=type(error).__name__,error=str(error)[:500])
        raise
    finally:
        try:
            if port is not None and port.is_open and 'owned_port_close_returned' not in evidence:port.close()
        except BaseException as error:
            evidence.update(status='ABORTED',close_error=repr(error)[:500])
        finally:
            lock.close()
            # Refuse to remove another owner's coordination files.
            if (published and status.exists() and json.loads(status.read_text())==owner and
                    evidence.get('owned_port_close_returned') is not False and 'close_error' not in evidence):
                marker.unlink();status.unlink();evidence['lease_released']=True
            else:evidence['lease_released']=False
            for number,handler in old_signals.items():signal.signal(number,handler)
            evidence.update(port_free_verified=False,host_signals=signals)
            save_status(output,'result.json',evidence)
            print('CAPTURE_FINAL '+json.dumps(evidence),flush=True)


if __name__=='__main__':cli_main()
