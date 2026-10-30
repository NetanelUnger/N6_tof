"""Bounded BLE CLI + USB controls, current Wi-Fi/Cloud intent preserved."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, asyncio, importlib.util, json, math, msvcrt, os, re, subprocess, sys, time, threading
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
    assert a.seconds==120;a.output.mkdir(parents=True,exist_ok=False)
    git=['git','-C',str(ROOT)]
    assert subprocess.check_output(git+['branch','--show-current'],text=True).strip()=='feature/n6-xip-ota-usb'
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    folder=common.parent/'.local-dependencies/diagnostics';marker=folder/'n6-hardware-owner.lock';status=folder/'n6-hardware-owner.json'
    assert not any(p.exists() for p in (marker,status,folder/'n6-hardware-recovery.lock')),'Existing hardware owner; no takeover'
    ident=windows_process_identity(os.getpid());assert ident['state']=='alive'
    owner={'thread':OWNER,'pid':os.getpid(),'started_utc':utc(),'process_created_utc':ident['created_utc'],
           'scope':'120-second images to existing NatiLab Cloud Relay; BLE/USB control probes; runtime image route off at finish; no reset, update, saved-settings or pairing writes'}
    r={'started_utc':utc(),'owner':owner,'result':'INCOMPLETE','profile':'BLE CLI + USB; existing Wi-Fi/Cloud enabled; existing Cloud images active',
       'requested_seconds':a.seconds,'source_revision':subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip(),
       'running_image_provenance':'B54 source5432d4a plus scoped working diff, packageSHA256 112299106456df407d5618096244c1095e8bbad7a8fded0e4a9a2ef62453c697, installed and Secure-confirmed; debug output OFF',
       'pair_requested':False,'firmware_bytes_sent':0,'settings_commands':False,'pings':[],'usb_pings':[],
       'events':[],'max_host_loop_lag_ms':0,'handles_closed':False,'lease_released':False}
    lock=usb=None;owned=False
    async def run():
        nonlocal usb
        client=None;subscribed=False;buf=bytearray();rx_times=[];monitor=None;measuring=False
        usb_lock=threading.Lock();stopper=None;images_controlled=False;images_started=None;images_stopped=False
        def command(c,timeout=3):
            with usb_lock:return usb.command(c,timeout)
        def note(_,data):buf.extend(data);rx_times.append(time.monotonic())
        def snapshot():
            return {c:command(c,3) for c in ('version','radio info','radio status','ble status','tof status','rps status','cloud status')}
        async def stop_images():
            nonlocal images_stopped
            if images_stopped:return
            r['image_stop_command']=await asyncio.to_thread(command,'dataset route none',3)
            r['image_stop_ack_utc']=utc()
            if images_started is not None:r['image_route_enabled_s']=time.monotonic()-images_started
            r['image_stop_status']=await asyncio.to_thread(command,'tof status',3)
            assert 'requested NONE, active NONE' in r['image_stop_status'],'Image stop not confirmed'
            images_stopped=True;r['image_transmission_stopped']=True
        async def bounded_stop():
            await asyncio.sleep(max(0,images_started+a.seconds-time.monotonic()))
            await stop_images()
        async def lag():
            before=time.monotonic()
            while measuring:
                await asyncio.sleep(.05);now=time.monotonic();r['max_host_loop_lag_ms']=max(r['max_host_loop_lag_ms'],(now-before-.05)*1000);before=now
        async def usb_watch():
            count=0
            while measuring:
                token=f'ST67U-{count:04d}';start=time.monotonic()
                response=await asyncio.to_thread(command,'debug ping '+token,3)
                assert response.count('PONG '+token+' ')==1 and response.endswith('n6> '),'USB PONG missing/duplicate'
                r['usb_pings'].append({'token':token,'elapsed_ms':(time.monotonic()-start)*1000,'response':response})
                assert r['usb_pings'][-1]['elapsed_ms']<1000
                count+=1;await asyncio.sleep(1)
        watch=None
        try:
            ports=[x for x in list_ports.comports() if x.vid==0x0483 and x.pid==0x5740 and x.serial_number=='N6TOF001'];assert len(ports)==1
            usb=UsbCli(ports[0].device);r['before']=snapshot()
            before=r['before'];assert 'Firmware version: 54\r\n' in before['version'],'Live version changed'
            assert 'link: disconnected' in before['ble status'] and 'CLI TX notifications: off' in before['ble status'],'Existing BLE user session'
            assert re.search(r'requested (?:CLOUD|NONE), active (?:CLOUD|NONE)',before['tof status']),'User image route changed'
            endpoint=re.search(r'endpoint (\S+)',before['cloud status'])
            assert endpoint and endpoint[1]=='http://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net','Cloud destination changed'
            assert 'Cloud Relay: polling, paired,' in before['cloud status']
            assert 'Device: N6-MAINT-B8FB, workspace: ws-13e32f198c2e42938860512d2f0ce47d,' in before['cloud status'],'Cloud identity changed'
            r['verified_endpoint']=endpoint[1]
            assert 'manager: ready' in before['radio status'] and 'W6X_Init: passed' in before['radio status'] and 'NCP recovery: state=0 stage=0' in before['radio status'],'Radio unavailable'
            assert 'ToF state: ready' in before['tof status'] and 'errors=0' in before['rps status'],'Sensor/NPU baseline unhealthy'
            images_controlled=True
            r['pause_for_setup']=await asyncio.to_thread(command,'dataset route none',3)
            assert 'requested NONE, active NONE' in await asyncio.to_thread(command,'tof status',3)
            r['image_encoding']=await asyncio.to_thread(command,'MAP ENCODING',3)
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
            r['cloud_measurement_before']=await asyncio.to_thread(command,'cloud status',3)
            images_started=time.monotonic();r['image_start_utc']=utc();stopper=asyncio.create_task(bounded_stop())
            r['image_start_command']=await asyncio.to_thread(command,'dataset route cloud',3)
            assert 'requested CLOUD, active CLOUD' in await asyncio.to_thread(command,'tof status',3)
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
                assert elapsed<1500,'Existing BLE maximum 1500 ms exceeded'
                count+=1
                if time.monotonic()-progress>=30:
                    print(json.dumps({'elapsed_s':time.monotonic()-begin,'ble':len(r['pings']),'usb':len(r['usb_pings']),'max_ble_ms':max(x['elapsed_ms'] for x in r['pings'])}),flush=True);progress=time.monotonic()
                await asyncio.sleep(max(0,begin+count-time.monotonic()))
            r['elapsed_s']=time.monotonic()-begin
            measuring=False;await monitor;await watch;watch=monitor=None
            await stopper;stopper=None
            await client.stop_notify(TX);subscribed=False;await client.disconnect();client=None
            r['after']=await asyncio.to_thread(snapshot)
            for pattern,key in [(r'SPI fault: count=(\d+)','radio status'),(r'NCP recovery: state=0 stage=0 attempts=(\d+)','radio status'),(r'Radio allocations: failed=(\d+)','radio status')]:
                b=re.search(pattern,before[key]);after=re.search(pattern,r['after'][key]);assert b and after and b[1]==after[1],f'New fault/recovery: {pattern}'
            assert 'requested NONE, active NONE' in r['after']['tof status']
            assert 'errors=0' in r['after']['rps status']
            assert int(re.search(r'processed (\d+)',r['after']['tof status'])[1])>int(re.search(r'processed (\d+)',before['tof status'])[1])
            sent_before=int(re.search(r'ToF: sent (\d+)',r['cloud_measurement_before'])[1])
            sent_after=int(re.search(r'ToF: sent (\d+)',r['after']['cloud status'])[1])
            assert sent_after>sent_before,'Cloud image sender stopped'
            r['cloud_images_http_accepted']=sent_after-sent_before
            r['cloud_images_http_accepted_per_second']=(sent_after-sent_before)/r['image_route_enabled_s']
            for label,pattern,key in [('cloud_image_drops',r'ToF: sent \d+, dropped (\d+)','cloud status'),('cloud_request_errors',r'request errors (\d+)','cloud status'),('spi_faults',r'SPI fault: count=(\d+)','radio status'),('ncp_recoveries',r'NCP recovery: state=0 stage=0 attempts=(\d+)','radio status')]:
                b=r['cloud_measurement_before'] if key=='cloud status' else before[key]
                r[label+'_delta']=int(re.search(pattern,r['after'][key])[1])-int(re.search(pattern,b)[1])
            r['cloud_receiver_validated']=False
            assert r['max_host_loop_lag_ms']<100
            r['result']='PASS'
        finally:
            measuring=False
            if stopper is not None:
                if not stopper.done():
                    stopper.cancel()
                    try:await stopper
                    except asyncio.CancelledError:pass
                else:
                    try:await stopper
                    except Exception as e:r['events'].append('image timer: '+repr(e))
            if images_controlled and not images_stopped:
                try:await stop_images()
                except Exception as e:r['events'].append('image stop: '+repr(e))
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
