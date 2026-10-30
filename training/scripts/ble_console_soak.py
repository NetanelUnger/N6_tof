"""Bounded images + CLI connection soak with independent timestamped evidence."""
import asyncio
import json
from pathlib import Path
import threading
import time
import uuid

from ble_console_core import ROOT, utc_now
from ble_console_images import decode_pixels


def append_json(path, item):
    with path.open('a',encoding='utf-8') as file:
        file.write(json.dumps(item)+'\n')


class UartEvidence:
    def __init__(self, port, path):
        self.port_name=port;self.path=path;self.stop=threading.Event();self.thread=None
        self.port=None;self.error=None;self.bytes=0;self.events=[]
    def start(self):
        if not self.port_name:return
        import serial
        self.port=serial.Serial(self.port_name,115200,timeout=.1)
        def collect():
            pending=bytearray()
            try:
                with self.path.open('x',encoding='utf-8') as file:
                    while not self.stop.is_set():
                        data=self.port.read(8192);self.bytes+=len(data);pending.extend(data)
                        while b'\n' in pending:
                            line,_,pending=pending.partition(b'\n')
                            text=line.decode('utf-8','replace').rstrip('\r')
                            item={'monotonic':time.monotonic(),'utc':utc_now(),'line':text}
                            file.write(json.dumps(item)+'\n')
                            if any(tag in text for tag in ('RADIO-RECOVERY','SPI-FAULT','TOF-RECOVERY','[WDT]','disconnect','DISCONNECT','BLEDISCONN','[RESET]','[FAULT]')):
                                if len(self.events)<500:self.events.append(item)
                        if len(pending)>16384:pending.clear()
                        if self.bytes>50_000_000:raise RuntimeError('UART capture exceeded 50 MB bound')
                        file.flush()
            except Exception as error:self.error=repr(error)
        self.thread=threading.Thread(target=collect,daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
        if self.port:self.port.close()


def usb_snapshot(port_name):
    if not port_name:return None
    import serial
    from run_xip_usb_update import command
    with serial.Serial(port_name,115200,timeout=.1,write_timeout=2) as port:
        port.dtr=True;time.sleep(.2)
        return {name:command(port,name) for name in ('version','ble status','radio status','tof status','rps status','debug uart')}


async def run_soak(session, duration=900, mode='UINT8', *, uart=None, usb=None,
                   stop=None, report_dir=None, progress=None):
    if not 10<=duration<=7200:raise ValueError('Soak duration must be 10..7200 seconds')
    folder=Path(report_dir or ROOT/'training/reports/ble_console')/('soak-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    report={'started_utc':utc_now(),'passed':False,'duration_target_s':duration,'encoding':mode,
            'address':session.address,'commands':[],'snapshots':[],'frames':[],
            'violations':[],'max_event_loop_lag_s':0,'pair_requested':False,
            'disconnect_observed_before_cleanup':False,'root_cause':'Not established'}
    capture=UartEvidence(uart,folder/'uart.jsonl')
    owned_images=not session.image_subscribed
    start=None;monitor=None;last_seen=None
    life_start=len(session.lifecycle)
    async def loop_monitor():
        prior=time.monotonic()
        while True:
            await asyncio.sleep(.05)
            now=time.monotonic();report['max_event_loop_lag_s']=max(report['max_event_loop_lag_s'],now-prior-.05);prior=now
    try:
        capture.start()
        if usb:report['usb_before']=await asyncio.to_thread(usb_snapshot,usb)
        report['baseline']={}
        for name in ('version','radio status','tof status','rps status','debug uart'):
            report['baseline'][name]=await session.command(name,disconnect_on_error=False)
        await session.start_images(mode)
        start=time.monotonic();report['start_monotonic']=start
        first_completed=session.images.completed;first_crc=session.images.crc_errors
        first_drops=session.images.dropped;first_errors=session.image_errors
        report['assembly_drops_at_start']=first_drops
        monitor=asyncio.create_task(loop_monitor())
        next_ping=start;next_status=start+30;next_progress=start
        index=0;last_gap_report=object()
        while time.monotonic()-start<duration:
            now=time.monotonic()
            if stop and stop.is_set():report['cancelled']=True;break
            if not session.connected:
                report['disconnect_observed_before_cleanup']=True
                report['failure']='BLE disconnected';break
            frame=session.latest_image
            if frame is not None and frame['host_monotonic']!=last_seen:
                decode_pixels(frame)  # Exercise the real decoder during headless runs too.
                last_seen=frame['host_monotonic']
            image_gap=now-(session.last_image_at or start)
            if image_gap>5 and last_gap_report!=session.last_image_at:
                report['violations'].append({'kind':'image_gap','at_s':now-start,'gap_s':image_gap})
                last_gap_report=session.last_image_at
            if image_gap>10:
                report['failure']='No complete image for more than 10 seconds';break
            if now>=next_ping:
                token='SOAK-'+str(index);index+=1
                try:row=await session.command('debug ping '+token,disconnect_on_error=False)
                except Exception as error:
                    report['failure']=type(error).__name__+': '+str(error)
                    if session.last_failure:report['commands'].append(session.last_failure)
                    break
                report['commands'].append(row)
                await asyncio.to_thread(append_json,folder/'commands.jsonl',{'at_s':time.monotonic()-start,**row})
                if not row['passed'] or 'PONG '+token+' ' not in row['response'] or row['ms']>1500:
                    report['violations'].append({'kind':'ping','at_s':time.monotonic()-start,'ms':row['ms'],'passed':row['passed']})
                next_ping=time.monotonic()+.5
            if now>=next_status:
                try:
                    state=await session.command('radio status',disconnect_on_error=False)
                    report['snapshots'].append({'at_s':time.monotonic()-start,**state})
                except Exception as error:
                    report['failure']='Status command: '+repr(error);break
                next_status=time.monotonic()+30
            if now>=next_progress:
                state={'elapsed_s':round(now-start,1),'connected':session.connected,
                       'frames':session.images.completed-first_completed,'pings':len(report['commands']),
                       'crc_errors':session.images.crc_errors-first_crc,'violations':len(report['violations'])}
                await asyncio.to_thread((folder/'progress.json').write_text,json.dumps(state,indent=2))
                if progress:progress(state)
                next_progress=now+10
            await asyncio.sleep(.02)
        report['measurement_elapsed_s']=time.monotonic()-start
        report['frames_received']=session.images.completed-first_completed
        report['crc_errors']=session.images.crc_errors-first_crc
        report['assembly_drops_total']=session.images.dropped
        report['assembly_drops']=session.images.dropped-first_drops
        report['image_callback_errors']=session.image_errors-first_errors
        report['max_image_gap_s']=session.max_image_gap
        report['last_image_notification_monotonic']=session.last_notification
        report['last_cli_notification_monotonic']=session.last_cli_notification
        report['frames']=[x for x in session.image_events if x['host_monotonic']>=start]
        if session.latest_image:
            from ble_console_images import colorize
            image,low,high=colorize(decode_pixels(session.latest_image))
            await asyncio.to_thread(image.resize((432,336)).save,folder/'last-sensor-frame.png')
            report['last_frame_display_range']=[low,high]
        if report.get('failure'):
            # Preserve a short passive tail BEFORE host-initiated disconnection.
            await asyncio.sleep(5)
        report['disconnect_observed_before_cleanup'] |= not session.connected
        if usb:
            try:report['usb_after']=await asyncio.to_thread(usb_snapshot,usb)
            except Exception as error:report['usb_after_error']=repr(error)
        report['passed']=(not report.get('failure') and not report.get('cancelled') and
                          not report['violations'] and report['crc_errors']==0 and
                          report['image_callback_errors']==0 and report['frames_received']>0 and
                          report['measurement_elapsed_s']>=duration)
    except asyncio.CancelledError:
        report['cancelled']=True
    except Exception as error:
        report['failure']=repr(error)
    finally:
        if monitor:
            monitor.cancel()
            try:await monitor
            except asyncio.CancelledError:pass
        report['lifecycle_before_cleanup']=list(session.lifecycle)[life_start:]
        report['cleanup_started_monotonic']=time.monotonic()
        if owned_images:
            try:await session.stop_images()
            except Exception as error:
                report['cleanup_error']=repr(error);report['passed']=False
        capture.close()
        report['uart']={'bytes':capture.bytes,'error':capture.error,'events':capture.events}
        if capture.error:report['passed']=False
        if report['disconnect_observed_before_cleanup']:
            report['finding']='Disconnect observed before cleanup; Bleak supplies no definitive remote reason. Correlate UART and USB state.'
        elif report.get('failure'):
            report['finding']='Failure observed without proof of a remote BLE disconnect. Host cleanup is recorded separately.'
        else:
            report['finding']='No unexpected BLE disconnect observed during this bounded measurement.'
        report['finished_utc']=utc_now()
        await asyncio.to_thread((folder/'result.json').write_text,json.dumps(report,indent=2),encoding='utf-8')
    return report,str(folder/'result.json')
