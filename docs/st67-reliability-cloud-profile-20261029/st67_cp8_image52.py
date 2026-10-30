"""Exclusive BLE-only actual NPU/image/CLI soak with nonblocking status I/O.

An existing user/BLE connection is a blocker. Always pair=False. This never loads
firmware, resets hardware or changes Wi-Fi/Cloud/settings. Run only after the
protected SRAM identity/settings baseline is verified and the lease is held.
Full data is written once after cleanup; periodic small status writes occur on
a dedicated host thread. Direct receive-gap and loop-lag metrics expose backlog.
"""
from cli_text_protocol import reply_finished, reply_succeeded, reply_results



def require_receive_window_counts(start, end, duration):
    """Check the existing delivery floors using the frozen measurement window.

    Notifications arriving during end-state queries or cleanup cannot rescue
    a window that missed its throughput requirement.
    """
    measured = {name: end[name] - start[name] for name in ('images', 'results')}
    minimum = {'images': duration * 3000 // 3600,
               'results': duration * 6000 // 3600}
    for name in ('images', 'results'):
        assert measured[name] >= minimum[name], (
            f'{name} in measurement window: {measured[name]} < {minimum[name]}'
        )
    return {'measured': measured, 'minimum': minimum}


def cli_main():
    global BleakClient, BleakScanner, Path, RPS, RX, TOF, TX, TofFrameAssembler, UsbCli, argparse, args, assembler, asyncio, atomic_json, cli, client, collect, datetime, duration, find_cn8, here, image, json, label, last_image_receipt, last_result_receipt, main, math, measuring, monitor, owner, parser, pending, ping, probe_writer_delay, queue, re, report, result, root, save, serial, snapshot, state, status_jobs, stop, sys, threading, time, timezone, uart, usb, watch_loop, worker, write_status, writer, writer_stop
    import argparse,asyncio,json,re,time,sys,threading,math,queue
    from datetime import datetime,timezone
    from pathlib import Path
    import serial
    from bleak import BleakScanner,BleakClient
    sys.path.insert(0,'hil_tests')
    from run_milestone4_gate import UsbCli,find_cn8,atomic_json
    from ble_inspector import TofFrameAssembler
    parser=argparse.ArgumentParser(description='Exclusive BLE-only actual NPU/image/CLI soak. No pairing, reset, load, Wi-Fi or persistent setters. Run from project root with the matching held hardware lease.')
    parser.add_argument('--duration',type=int,default=3600)
    parser.add_argument('--label',required=True,help='Fresh unique diagnostics folder label')
    parser.add_argument('--owner-thread',required=True,help='Exact thread identity owning the held N6 lease')
    parser.add_argument('--probe-writer-delay',action='store_true',help='Focused host-only4.5s writer-delay verification')
    args=parser.parse_args();duration=args.duration;label=args.label;assert 120<=duration<=3600 and re.fullmatch('[a-z0-9-]+',label)
    probe_writer_delay=args.probe_writer_delay
    root=Path.cwd();here=root/'.local-dependencies/diagnostics'/label;here.mkdir(exist_ok=False)
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text(encoding='utf-8-sig'));assert owner['thread']==args.owner_thread and (root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.lock').exists(),'BLOCKED no matching exclusive lease'
    RPS='7a1e0005-b5a3-f393-e0a9-e50e24dcca9e';TOF='7a1e0004-b5a3-f393-e0a9-e50e24dcca9e';RX='7a1e0002-b5a3-f393-e0a9-e50e24dcca9e';TX='7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
    report={'started_utc':datetime.now(timezone.utc).isoformat(),'passed':False,'scope':'B52_BLE_IMAGES_NPU_CLI_WITH_EXISTING_WIFI_CLOUD_POLLING_NOT_ACTIVE_CLOUD_CONTROL','pair_requested':False,'settings_commands':False,'duration_target_s':duration,'io_timings':[],'io_errors':[],'max_event_loop_lag_s':0,'max_result_receive_gap_s':0,'max_image_receive_gap_s':0,'snapshots':[],'stale_probe':{},'results':[],'images':[],'pings':[],'connections':[],'errors':[],'events':[],'rps_packets':[]}
    usb=uart=client=worker=None;stop=threading.Event();cli=bytearray();pending=bytearray();assembler=TofFrameAssembler()
    measuring=False;status_jobs=queue.Queue(maxsize=1);writer_stop=threading.Event();writer=None;monitor=None;last_result_receipt=last_image_receipt=0

    def snapshot():
        start=report.get('soak_start_counts',{});v=sorted(report['pings'][start.get('pings',0):]);stats={k:v[min(len(v)-1,math.ceil(p*len(v))-1)] for k,p in (('p50',.5),('p95',.95),('p99',.99),('max',1))} if v else {}
        return {'status':'RUNNING' if measuring else 'PASS' if report['passed'] else 'FAILED' if report.get('failure') else 'SETUP','elapsed_s':report.get('elapsed_s'),'duration_target_s':duration,'results':len(report['results']),'images':len(report['images']),'cli_finals':len(report['pings']),'latency_ms':stats,'parser_errors':len(report['errors']),'image_crc_errors':assembler.crc_errors,'image_drops_during_soak':report.get('image_drops_during_soak',0),'max_age_ms':report.get('max_result_age_ms'),'hardware_events':len(report['events']),'snapshots':len(report['snapshots']),'last_snapshot':report['snapshots'][-1] if report['snapshots'] else None,'failure':report.get('failure'),'max_event_loop_lag_s':report['max_event_loop_lag_s'],'max_result_receive_gap_s':report['max_result_receive_gap_s'],'max_image_receive_gap_s':report['max_image_receive_gap_s'],'io_write_max_s':max((x['elapsed_s'] for x in report['io_timings']),default=0),'io_errors':len(report['io_errors']),'stale_probe':report['stale_probe']}

    def save():
        item=snapshot()
        try:status_jobs.put_nowait(item)
        except queue.Full:
            try:status_jobs.get_nowait()
            except queue.Empty:pass
            status_jobs.put_nowait(item)

    def write_status():
        while not writer_stop.is_set() or not status_jobs.empty():
            try:item=status_jobs.get(timeout=.2)
            except queue.Empty:continue
            begin=time.monotonic()
            if probe_writer_delay and measuring and not report['io_timings']:
                report['injected_host_writer_delay_s']=4.5;time.sleep(4.5)
            try:atomic_json(here/'status.json',item)
            except Exception as exc:report['io_errors'].append(type(exc).__name__+': '+str(exc))
            report['io_timings'].append({'begin_monotonic':begin,'end_monotonic':time.monotonic(),'elapsed_s':time.monotonic()-begin})

    async def watch_loop():
        prior=time.monotonic()
        while measuring:
            await asyncio.sleep(.05);now=time.monotonic();report['max_event_loop_lag_s']=max(report['max_event_loop_lag_s'],now-prior-.05);prior=now

    def collect():
        buf=bytearray()
        while not stop.is_set():
            buf.extend(uart.read(4096))
            while b'\n' in buf:
                line,_,tail=buf.partition(b'\n');buf[:]=tail;s=line.decode('utf8','replace')
                if any('['+t+']' in s for t in ('RADIO-RECOVERY','SPI-FAULT','TOF-RECOVERY')):report['events'].append(s)
            if len(buf)>8192:buf.clear()
    def state():
        system=usb.command('status',3);radio=usb.command('radio status',3);tof=usb.command('tof status',3);cloud=usb.command('cloud status',3)
        r=re.search(r'NCP recovery: state=(\d+) stage=(\d+) attempts=(\d+) ready=(\d+) failed=(\d+)',radio)
        ctrl=re.search(r'BLE control: state=(\d+) op=(\d+) submitted=(\d+) completed=(\d+) deferred=(\d+) stale=(\d+) queue_max=(\d+) ms call_max=(\d+) ms last=(-?\d+)',radio)
        return {'ble_control':list(map(int,ctrl.groups())) if ctrl else None,'wifi_ip':'Wi-Fi IP ready' in system,'radio_ready':'manager: ready' in radio and 'W6X_Init: passed' in radio and 'NCP recovery: state=0 stage=0' in radio,'recovery':list(map(int,r.groups())),
                'tof_ready':'ToF state: ready' in tof,'tof_frame':int(re.search(r'Frame: (\d+)',tof)[1]),
                'route':re.search(r'requested (\w+), active (\w+)',tof).groups(),
                'cloud_paired':', paired,' in cloud,'http_active':int(re.search(r'HTTP: active (\d+)',cloud)[1]),
                'cloud_frames':int(re.search(r'ToF: sent (\d+)',cloud)[1]),'cloud_dropped':int(re.search(r'dropped (\d+)',cloud)[1]),'cloud_errors':int(re.search(r'request errors (\d+)',cloud)[1]),
                'spi_fault':int(re.search(r'SPI fault: count=(\d+)',radio)[1]) if re.search(r'SPI fault: count=(\d+)',radio) else None}
    def result(_,data):
        global last_result_receipt
        report['rps_packets'].append(bytes(data).hex());pending.extend(data)
        while b'\n' in pending:
            raw,_,tail=pending.partition(b'\n');pending[:]=tail
            try:
                x=json.loads(raw);assert x['v']==x['npu']==1 and len(x['q'])==4 and all(type(q) is int and -128<=q<=127 for q in x['q']) and all(type(x[k]) is int and x[k]>0 for k in ('g','f','r'))
                best=max(range(4),key=lambda i:x['q'][i]);p=((x['q'][best]+128)*1000+128)//256
                assert x['ok']==1 and x['c']==('none','rock','paper','scissors')[best] and x['p']==p and int(x['a'])<2000 and x['r']>0
                x['host_monotonic']=time.monotonic()
                if measuring:
                    gap=x['host_monotonic']-last_result_receipt;report['max_result_receive_gap_s']=max(report['max_result_receive_gap_s'],gap)
                    if gap>=3:report['errors'].append('NPU receive gap >3s: '+str(gap))
                    if report['results'] and (x['g']!=report['results'][-1]['g'] or x['f']<=report['results'][-1]['f'] or x['r']<=report['results'][-1]['r']):report['errors'].append('NPU generation/order regression')
                last_result_receipt=x['host_monotonic'];report['results'].append(x)
            except Exception as exc:report['errors'].append(type(exc).__name__+': '+str(exc))
        if len(pending)>192:report['errors'].append('oversize result');pending.clear()
    def image(_,data):
        global last_image_receipt
        x=assembler.push(data)
        if x:
            x['host_monotonic']=time.monotonic()
            if measuring:
                gap=x['host_monotonic']-last_image_receipt;report['max_image_receive_gap_s']=max(report['max_image_receive_gap_s'],gap)
                if gap>=5:report['errors'].append('image receive gap >5s: '+str(gap))
            last_image_receipt=x['host_monotonic'];report['images'].append(x)
    async def ping(i):
        token='RPS-'+str(i);begin=len(cli);t=time.monotonic();await client.write_gatt_char(RX,('debug ping '+token+'\r').encode(),response=True)
        while time.monotonic()-t<10:
            text=cli[begin:].decode('utf8','replace')
            if 'PONG '+token+' ' in text and reply_succeeded(text):break
            await asyncio.sleep(.01)
        else:raise TimeoutError('missing BLE final')
        elapsed=(time.monotonic()-t)*1000;report['pings'].append(round(elapsed,2));assert elapsed<1500,'BLE latency >1500ms'
    async def main():
        global usb,uart,worker,client,cli,pending,assembler,writer,monitor,measuring,last_result_receipt,last_image_receipt
        try:
            writer=threading.Thread(target=write_status,daemon=True);writer.start();usb=UsbCli(find_cn8(None,10));uart=serial.Serial('COM6',115200,timeout=.1);worker=threading.Thread(target=collect);worker.start()
            link=usb.command('ble status',3);assert 'link: disconnected' in link and 'queued 0/' in link,'BLOCKED active user/BLE client; no disconnect attempted'
            report['version']=usb.command('version',3);assert 'Firmware version: 52\r\n' in report['version'];report['image_encoding']=usb.command('MAP ENCODING',3);before=state();report['baseline']=before;assert before['wifi_ip'] and before['cloud_paired'] and before['radio_ready'] and before['tof_ready']
            for cycle in range(1):
                original_route=state()['route'];cli=bytearray();pending=bytearray();assembler=TofFrameAssembler();seen=await BleakScanner.discover(timeout=5)
                address=re.search(r'Address:\s*([0-9A-F:]{17})',link)[1];device=next(d for d in seen if d.address.upper()==address.upper())
                for kind in ('automatic',):
                    opts={'use_cached_services':False}
                    if kind!='automatic':opts['address_type']=kind
                    candidate=BleakClient(device,pair=False,timeout=18,winrt=opts)
                    try:
                        await candidate.connect();client=candidate;break
                    except Exception as exc:
                        report['connections'].append({'cycle':cycle+1,'kind':kind,'failure':type(exc).__name__+': '+str(exc)});save()
                        await candidate.disconnect()
                else:raise RuntimeError('all bounded non-pairing Windows connection variants failed')
                report['connections'].append({'cycle':cycle+1,'kind':kind,'mtu':client.mtu_size})
                assert RPS in {c.uuid for s in client.services for c in s.characteristics},'required actual RPS UUID absent'
                report['connections'][-1]['pair_requested']=False
                paired=client._backend._requester.device_information.pairing.is_paired
                report['connections'][-1]['os_is_paired']=paired
                assert not paired,'existing Windows paired state blocks direct nonbonded test; no unpair action taken'
                await client.start_notify(TX,lambda _,data:cli.extend(data));start=len(report['results']);await client.start_notify(RPS,result)
                await asyncio.sleep(4);assert len(report['results'])>=start+3,'NPU-only subscription delivered no fresh results'
                rps_only=state();report['connections'][-1]['rps_only']=rps_only;assert rps_only['route']==original_route,'RPS subscription stole image route'
                await client.stop_notify(RPS);await asyncio.sleep(.5);settled=len(report['results']);last=report['results'][-1];await asyncio.sleep(3.2)
                assert len(report['results'])==settled,'RPS callback continued after unsubscribed drain';expired=time.monotonic()-last['host_monotonic']>(2000-int(last['a']))/1000
                assert expired,'last model result did not age past expiry';pending.clear();await client.start_notify(RPS,result);resume=time.monotonic()+3
                while len(report['results'])==settled:
                    assert time.monotonic()<resume,'no fresh RPS after resubscribe';await asyncio.sleep(.05)
                assert report['results'][-1]['r']>last['r'],'old inference replay after resubscribe';report['stale_probe']={'unsubscribe_silence_s':3.2,'no_callbacks_after_drain':True,'host_model_expiry_elapsed':expired,'fresh_inference_after_resubscribe':True,'browser_rendering_observed':False};assert state()['route']==original_route
                await client.start_notify(TOF,image);await ping('map-'+str(cycle))
                at=len(cli);report['map_on_requested']=True;await client.write_gatt_char(RX,b'map on\r',response=True)
                deadline=time.monotonic()+5
                while not reply_succeeded(cli[at:]):
                    assert time.monotonic()<deadline,'MAP ON BLE completion absent';await asyncio.sleep(.01)
                first_image_deadline=time.monotonic()+5
                while not report['images']:
                    assert time.monotonic()<first_image_deadline,'initial image absent after5s';await asyncio.sleep(.05)
                start_images=len(report['images']);start_results=len(report['results']);soak_start=time.monotonic();checkpoint=soak_start+30;snapshot_due=soak_start+300;start_pings=len(report['pings']);start_drops=assembler.dropped;report['soak_start_counts']={'results':start_results,'images':start_images,'pings':start_pings,'drops':start_drops};report['soak_started_monotonic']=soak_start;measuring=True;monitor=asyncio.create_task(watch_loop());deadline=soak_start+duration
                while time.monotonic()<deadline:
                    await ping(str(cycle)+'-'+str(len(report['pings'])));await asyncio.sleep(.5)
                    assert client.is_connected,'unexpected BLE disconnect';assert assembler.crc_errors==0 and assembler.dropped==start_drops,'image CRC/drop';assert not report['events'],'unexpected hardware recovery/SPI event';assert not report['io_errors'],'host status I/O failed';assert not report['errors'],'NPU malformed/stale/gap/invalid';assert report['results'] and time.monotonic()-report['results'][-1]['host_monotonic']<3,'NPU stream stalled';assert report['images'] and time.monotonic()-report['images'][-1]['host_monotonic']<5,'image stream stalled';report['elapsed_s']=round(time.monotonic()-soak_start,3)
                    if time.monotonic()>=snapshot_due:
                        snap=await asyncio.to_thread(state);snap['elapsed_s']=report['elapsed_s'];report['snapshots'].append(snap);assert snap['radio_ready'] and snap['tof_ready'] and snap['tof_frame']>before['tof_frame'] and snap['route'][1]=='BLE';assert snap['wifi_ip'] and snap['cloud_paired'];assert snap['recovery']==before['recovery'] and snap['spi_fault']==before['spi_fault'] and snap['cloud_frames']==before['cloud_frames'] and snap['cloud_errors']==before['cloud_errors'] and snap['cloud_dropped']==before['cloud_dropped'];snapshot_due=time.monotonic()+300
                    if time.monotonic()>=checkpoint:
                        report['image_crc_errors']=assembler.crc_errors;report['image_drops_during_soak']=assembler.dropped-start_drops;report['max_result_age_ms']=max(int(x['a']) for x in report['results']);save()
                        print(json.dumps({'elapsed_s':report['elapsed_s'],'results':len(report['results']),'images':len(report['images']),'pings':len(report['pings']),'max_ms':max(report['pings'])}),flush=True);checkpoint=time.monotonic()+30
                report['soak_ended_monotonic']=time.monotonic();report['elapsed_s']=report['soak_ended_monotonic']-soak_start;assert report['elapsed_s']>=duration;report['soak_end_counts']={'results':len(report['results']),'images':len(report['images']),'pings':len(report['pings'])};measuring=False;await monitor
                current=await asyncio.to_thread(state);report['connections'][-1]['end']=current
                assert current['wifi_ip'] and current['cloud_frames']==before['cloud_frames']
                assert current['recovery']==before['recovery'] and current['spi_fault']==before['spi_fault']
                report['receive_count_gate']=require_receive_window_counts(report['soak_start_counts'],report['soak_end_counts'],duration)
                assert assembler.crc_errors==0
                report['connections'][-1]['image_crc_errors']=assembler.crc_errors
                await client.stop_notify(TOF);await client.stop_notify(RPS);await client.stop_notify(TX);await client.disconnect();client=None
                await asyncio.sleep(2);assert state()['route'][1]=='NONE';save();print('PASS B52 BLE-image/NPU background-Wi-Fi cycle '+str(cycle+1),flush=True)
            report['final']=await asyncio.to_thread(state);report['passed']=True;end=report['soak_end_counts'];values=sorted(report['pings'][start_pings:end['pings']]);report['latency_ms']={k:values[min(len(values)-1,math.ceil(pct*len(values))-1)] for k,pct in (('p50',.5),('p95',.95),('p99',.99),('max',1))};report['soak_counts']={'results':end['results']-start_results,'images':end['images']-start_images,'cli_finals':len(values)};report['finished_utc']=datetime.now(timezone.utc).isoformat()
        except Exception as exc:report['failure']=type(exc).__name__+': '+str(exc);raise
        finally:
            measuring=False
            if monitor and not monitor.done():await monitor
            if client and client.is_connected:
                for char in (TOF,RPS,TX):
                    try:await client.stop_notify(char)
                    except Exception:pass
                await client.disconnect()
            stop.set()
            if worker:worker.join(3)
            if uart:uart.close()
            if usb:usb.close()
            report['handles_closed']=True;save();writer_stop.set()
            if writer:writer.join(12)
            await asyncio.to_thread(atomic_json,here/'report.json',report);await asyncio.to_thread(atomic_json,here/'status.json',snapshot());print(json.dumps({k:report[k] for k in ('passed','scope','handles_closed')})+' results='+str(len(report['results']))+' images='+str(len(report['images'])),flush=True)
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
