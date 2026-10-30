"""Bounded BLE CLI + USB controls, current Wi-Fi/Cloud intent preserved."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, asyncio, importlib.util, json, math, msvcrt, os, re, subprocess, sys, time
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
from cli_text_protocol import reply_succeeded
from n6_hardware_lease import windows_process_identity
from run_milestone4_gate import UsbCli
from serial.tools import list_ports
from bleak import BleakClient,BleakScanner
OWNER='n6-xip-st67-reliability-20261028'
RX='7a1e0002-b5a3-f393-e0a9-e50e24dcca9e';TX='7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
def utc():return datetime.now(timezone.utc).isoformat()
def quantiles(values):
    v=sorted(values)
    return {k:v[math.ceil(q*len(v))-1] for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]} if v else {}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=120);a=p.parse_args()
    assert 30<=a.seconds<=600;a.output.mkdir(parents=True,exist_ok=False)
    git=['git','-C',str(ROOT)]
    assert subprocess.check_output(git+['branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';status=folder/'n6-hardware-owner.json'
    assert not any(p.exists() for p in (marker,status,folder/'n6-hardware-recovery.lock')),'Existing hardware owner; no takeover'
    ident=windows_process_identity(os.getpid());assert ident['state']=='alive'
    owner={'thread':OWNER,'pid':os.getpid(),'started_utc':utc(),'process_created_utc':ident['created_utc'],
           'scope':'bounded BLE CLI and USB read-only controls; no images, reset, update, settings or pairing writes'}
    r={'started_utc':utc(),'owner':owner,'result':'INCOMPLETE','profile':'BLE CLI + USB; existing Wi-Fi/Cloud enabled; images NONE',
       'requested_seconds':a.seconds,'source_revision':subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip(),
       'running_image_provenance':'UNRESOLVED v51; measurement only, no firmware changes',
       'pair_requested':False,'firmware_bytes_sent':0,'settings_commands':False,'pings':[],'usb_pings':[],
       'events':[],'max_host_loop_lag_ms':0,'handles_closed':False,'lease_released':False}
    lock=usb=None;owned=False
    async def run():
        nonlocal usb
        client=None;subscribed=False;buf=bytearray();rx_times=[];monitor=None;measuring=False
        def note(_,data):buf.extend(data);rx_times.append(time.monotonic())
        def snapshot():
            return {c:usb.command(c,3) for c in ('version','radio info','radio status','ble status','tof status','rps status','cloud status')}
        async def lag():
            before=time.monotonic()
            while measuring:
                await asyncio.sleep(.05);now=time.monotonic();r['max_host_loop_lag_ms']=max(r['max_host_loop_lag_ms'],(now-before-.05)*1000);before=now
        async def usb_watch():
            count=0
            while measuring:
                token=f'ST67U-{count:04d}';start=time.monotonic()
                response=await asyncio.to_thread(usb.command,'debug ping '+token,3)
                assert response.count('PONG '+token+' ')==1 and response.endswith('n6> '),'USB PONG missing/duplicate'
                r['usb_pings'].append({'token':token,'elapsed_ms':(time.monotonic()-start)*1000,'response':response})
                count+=1;await asyncio.sleep(2)
        watch=None
        try:
            ports=[x for x in list_ports.comports() if x.vid==0x0483 and x.pid==0x5740 and x.serial_number=='N6TOF001'];assert len(ports)==1
            usb=UsbCli(ports[0].device);r['before']=snapshot()
            before=r['before'];assert 'Firmware version: 51\r\n' in before['version'],'Live version changed'
            assert 'link: disconnected' in before['ble status'] and 'CLI TX notifications: off' in before['ble status'],'Existing BLE user session'
            assert 'requested NONE, active NONE' in before['tof status'],'Existing image stream; no interruption'
            assert 'state=available reason=READY' in before['radio status'],'Radio unavailable'
            assert 'ToF state: ready' in before['tof status'] and 'errors=0' in before['rps status'],'Sensor/NPU baseline unhealthy'
            address=re.search(r'Address:\s*([0-9A-F:]{17})',before['ble status'])[1]
            seen=await BleakScanner.discover(timeout=5)
            device=next((d for d in seen if d.address.upper()==address.upper()),None);assert device,'Expected BLE advertisement not found'
            r['ble_address']=address;r['ble_name']=device.name
            client=BleakClient(device,pair=False,timeout=18,winrt={'use_cached_services':False})
            await client.connect();r['mtu']=client.mtu_size
            r['os_is_paired']=client._backend._requester.device_information.pairing.is_paired
            assert not r['os_is_paired'],'Paired state blocks nonbonded test; no unpair attempted'
            uuids={c.uuid for s in client.services for c in s.characteristics};assert RX in uuids and TX in uuids,'CLI GATT contract missing'
            await client.start_notify(TX,note);subscribed=True;await asyncio.sleep(.2)
            begin=time.monotonic();measuring=True;monitor=asyncio.create_task(lag());watch=asyncio.create_task(usb_watch());count=0;progress=begin
            while time.monotonic()-begin<a.seconds:
                if watch.done():await watch
                assert client.is_connected,'Unexpected BLE disconnect'
                token=f'ST67B-{count:04d}';offset=len(buf);start=time.monotonic()
                await client.write_gatt_char(RX,('debug ping '+token+'\r').encode(),response=True)
                while time.monotonic()-start<5:
                    text=buf[offset:].decode('utf-8','replace')
                    if reply_succeeded(text) and 'PONG '+token+' ' in text:break
                    await asyncio.sleep(.005)
                else:raise TimeoutError('Missing BLE final: '+token)
                elapsed=(time.monotonic()-start)*1000
                item={'token':token,'elapsed_ms':elapsed,'response':text,'host_monotonic':time.monotonic()};r['pings'].append(item)
                assert text.count('PONG '+token+' ')==1,'Duplicate BLE outcome'
                assert elapsed<=1500,'Existing BLE maximum 1500 ms exceeded'
                count+=1
                if time.monotonic()-progress>=30:
                    print(json.dumps({'elapsed_s':time.monotonic()-begin,'ble':len(r['pings']),'usb':len(r['usb_pings']),'max_ble_ms':max(x['elapsed_ms'] for x in r['pings'])}),flush=True);progress=time.monotonic()
                await asyncio.sleep(max(0,begin+count-time.monotonic()))
            r['elapsed_s']=time.monotonic()-begin
            measuring=False;await monitor;await watch;watch=monitor=None
            await client.stop_notify(TX);subscribed=False;await client.disconnect();client=None
            r['after']=await asyncio.to_thread(snapshot)
            for pattern,key in [(r'SPI fault: count=(\d+)','radio status'),(r'NCP recovery: state=0 stage=0 attempts=(\d+)','radio status'),(r'Radio allocations: failed=(\d+)','radio status')]:
                b=re.search(pattern,before[key]);after=re.search(pattern,r['after'][key]);assert b and after and b[1]==after[1],f'New fault/recovery: {pattern}'
            assert 'requested NONE, active NONE' in r['after']['tof status']
            assert 'errors=0' in r['after']['rps status']
            assert int(re.search(r'processed (\d+)',r['after']['tof status'])[1])>int(re.search(r'processed (\d+)',before['tof status'])[1])
            r['result']='PASS'
        finally:
            measuring=False
            for task in (monitor,watch):
                if task is not None:
                    try:await task
                    except Exception as e:r['events'].append('worker: '+repr(e))
            if client is not None:
                try:
                    if subscribed and client.is_connected:await client.stop_notify(TX)
                    await client.disconnect()
                except Exception as e:r['events'].append('BLE cleanup: '+repr(e))
            if usb is not None:usb.close()
            r['handles_closed']=not r['events']
    try:
        lock=marker.open('x+b');lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with status.open('x') as f:json.dump(owner,f,indent=2)
        owned=True;(a.output/'owner-start.json').write_text(json.dumps(owner,indent=2)+'\n')
        asyncio.run(run())
    except BaseException as e:
        r['result']='FAIL';r['failure']=repr(e);raise
    finally:
        if lock is not None:
            lock.close()
            if owned and status.exists() and json.loads(status.read_text())==owner:
                marker.unlink();status.unlink();r['lease_released']=True
        r['finished_utc']=utc();r['ble_latency_ms']=quantiles([x['elapsed_ms'] for x in r['pings']]);r['usb_latency_ms']=quantiles([x['elapsed_ms'] for x in r['usb_pings']])
        (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in r.items() if k in ('result','failure','elapsed_s','ble_latency_ms','usb_latency_ms','max_host_loop_lag_ms','handles_closed','lease_released')}),flush=True)
if __name__=='__main__':main()
