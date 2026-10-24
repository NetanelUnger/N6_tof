"""Bounded protected Cloud/BLE recovery profiles; no image CCCD writes or replay."""
from cli_text_protocol import reply_finished, reply_succeeded, reply_results



def cli_main():
    global ADDRESS, BASE, BleakClient, BleakScanner, HERE, Path, ROOT, RX, TOF, TX, UsbCli, aggregate, argparse, args, asyncio, atomic_json, campaign_events, client, collect, connect, datetime, find_cn8, index, json, lease, main, os, owner, parser, ping, re, received, report, safe_receive, save, serial, snapshot, stop, sys, threading, time, timezone, uart, usb, worker
    import argparse, asyncio, json, re, sys, threading, time, os
    from pathlib import Path
    from datetime import datetime, timezone
    import serial
    from bleak import BleakClient, BleakScanner
    sys.path.insert(0, 'hil_tests')
    from run_milestone4_gate import UsbCli, find_cn8, atomic_json

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--owner-thread',required=True)
    parser.add_argument('--elf-sha256',default='05FD9EFDAA0C825C81F30751C8DE3A1245F074007B96110EFE77E21BE25F7E12')
    parser.add_argument('--profiles',type=int,choices=(1,2,3),default=1)
    args=parser.parse_args()
    ROOT=Path(__file__).resolve().parents[1]
    os.chdir(ROOT)
    HERE=args.output.resolve()
    HERE.mkdir(exist_ok=False,parents=True)
    lease=ROOT/'.local-dependencies/diagnostics/n6-hardware-owner.lock'
    assert lease.exists(), 'exclusive hardware lease absent'
    owner=json.loads(lease.with_suffix('.json').read_text())
    assert owner['thread']==args.owner_thread, 'exclusive hardware ownership not established'
    RX = '7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
    TX = '7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
    TOF = '7a1e0004-b5a3-f393-e0a9-e50e24dcca9e'
    ADDRESS = '40:82:7B:03:B8:FB'
    report = {'passed': False, 'phase': 'setup', 'started_utc': datetime.now(timezone.utc).isoformat(),
              'pair_requested': False, 'fault_submissions': 0, 'automatic_command_replay': False,
              'firmware_reset_load_flash_or_credential_write': False,
              'dma_in_flight_abort_proven': False, 'ble_commands': [], 'connections': [],
              'events': [], 'usb_pings': [], 'samples': []}
    stop = threading.Event()
    usb = uart = worker = client = None
    received = bytearray()
    campaign_events = []

    def save():
        atomic_json(HERE / 'report.json', report)

    def collect():
        pending = bytearray()
        while not stop.is_set():
            try:
                pending.extend(uart.read(4096))
            except Exception as exc:
                report['uart_error']=type(exc).__name__+': '+str(exc)
                stop.set()
                return
            while b'\n' in pending:
                raw, _, tail = pending.partition(b'\n'); pending[:] = tail
                line = raw.decode('utf-8', 'replace')
                for tag in ('RADIO-RECOVERY', 'CLI-RECOVERY', 'SPI-FAULT', 'NCP-CONFIG', 'WIFI_RESTORE'):
                    if '['+tag+']' not in line: continue
                    tick = re.search(r'^\[(\d+)\]', line)
                    row = {'tag': tag, 'tick_ms': int(tick[1]) if tick else None,
                           'numbers': dict(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)=([+-]?(?:0x)?[0-9A-Fa-f]+)\b', line)),
                           'words': dict(re.findall(r'\b(reason|result|outcome)=([A-Za-z_]+)', line)),
                           'start': 'START' in line, 'end': 'END' in line}
                    report['events'].append(row)
                    campaign_events.append(row)
                    break
            if len(pending) > 8192: pending.clear()

    def snapshot():
        r = usb.command('radio status', 2)
        t = usb.command('tof status', 2)
        c = usb.command('cloud status', 2)
        s = usb.command('status', 2)
        b = usb.command('ble status', 2)
        recovery = re.search(r'NCP recovery: state=(\d+) stage=(\d+) attempts=(\d+) ready=(\d+) failed=(\d+) elapsed=(\d+) ms', r)
        counts = re.search(r'ToF: sent (\d+), dropped (\d+); request errors (\d+)', c)
        notice = re.search(r'BLE recovery notice: sequence=(\d+) pending=(\d+) old_generation=(\d+) rx_slots=(\d+) tx_slots=(\d+) active_reply=(\d+)', r)
        frame = re.search(r'Frame: (\d+)', t)
        route = re.search(r'Image destination: requested (\w+), active (\w+)', t)
        assert recovery and counts and frame and notice, 'public status incomplete'
        return {'recovery': dict(zip(('state','stage','attempts','ready','failed','elapsed_ms'), map(int,recovery.groups()))),
                'notice': dict(zip(('sequence','pending','old_generation','rx_slots','tx_slots','active_reply'),map(int,notice.groups()))),
                'wifi_ip': 'Wi-Fi IP ready' in s, 'radio_ready': 'state=available reason=READY' in r,
                'tof_ready': 'ToF state: ready' in t, 'tof_frame': int(frame[1]),
                'cloud_paired': bool(re.search(r'Cloud Relay: [^,]+, paired,',c)),
                'cloud_state': re.search(r'Cloud Relay: ([^,]+)',c)[1],
                'cloud_frames': int(counts[1]), 'cloud_drops': int(counts[2]), 'cloud_errors': int(counts[3]),
                'http': next((x for x in c.splitlines() if x.startswith('HTTP:')),'missing'),
                'route': list(route.groups()) if route else None,
                'map': next((x for x in t.splitlines() if x.startswith('Map:')),'missing'),
                'spi_fault': next((x.strip() for x in r.splitlines() if 'SPI fault:' in x),'missing'),
                'allocations': next((x.strip() for x in r.splitlines() if 'Radio allocations:' in x),'missing'),
                'subscriptions': next((x.strip() for x in b.splitlines() if x.startswith('CLI TX notifications:')),'missing')}

    def safe_receive(start=0):
        text = received[start:].decode('utf-8','replace')
        return {'bytes': len(received)-start,
                'help_banners': text.count('CLI HELP ('),
                'results': reply_results(text),
                'pongs': re.findall(r'PONG (CA-[A-Za-z0-9-]+) (\d+)',text),
                'notices': re.findall(r'\[CLI-EVENT\] event=RADIO_RECOVERY[^\r\n]*',text)}

    async def connect():
        global client, received
        seen = await BleakScanner.discover(timeout=6,return_adv=True)
        matches = [d for d,a in seen.values() if d.address.upper()==ADDRESS]
        assert len(matches)==1, 'exact target advertisement absent'
        for kind in ('automatic','public','random'):
            options = {'use_cached_services':False}
            if kind!='automatic': options['address_type']=kind
            candidate=BleakClient(matches[0], timeout=18,pair=False,winrt=options)
            row={'kind':kind,'pair_requested':False};report['connections'].append(row)
            try:
                await candidate.connect()
                assert candidate.is_connected, 'BLE backend disconnected'
                chars={c.uuid for service in candidate.services for c in service.characteristics}
                assert RX in chars and TX in chars, 'CLI UUID contract absent'
                client=candidate;row.update(connected=True,mtu=client.mtu_size)
                received=bytearray()
                await client.start_notify(TX,lambda _,data:received.extend(data))
                image_char=client.services.get_characteristic(TOF)
                assert image_char is not None, 'ToF characteristic absent'
                image_cccd=next(d for d in image_char.descriptors if d.uuid.lower().startswith('00002902-'))
                row['image_cccd_before']=bytes(await client.read_gatt_descriptor(image_cccd.handle)).hex()
                row['image_subscription_written']=False
                row['cli_characteristic_handle']=client.services.get_characteristic(TX).handle
                row['image_characteristic_handle']=image_char.handle
                row['after_cli_subscribe_status']=await asyncio.to_thread(snapshot)
                await asyncio.sleep(2)
                return
            except Exception as exc:
                row['failure']=type(exc).__name__+': '+str(exc)
                if candidate.is_connected: await candidate.disconnect()
        raise RuntimeError('All bounded transient BLE connection attempts failed')

    async def ping(token):
        start=len(received);tick=time.monotonic()
        await client.write_gatt_char(RX,('debug ping '+token+'\r').encode(),response=True)
        end=tick+10
        while time.monotonic()<end:
            text=received[start:].decode('utf-8','replace')
            if 'PONG '+token+' ' in text and reply_succeeded(text):
                row={'token':token,'ms':round((time.monotonic()-tick)*1000,2),'complete':True}
                report['ble_commands'].append(row);return
            await asyncio.sleep(.01)
        raise TimeoutError('BLE final/PONG missing: '+token)

    async def main():
        global usb,uart,worker,client,received
        try:
            proof=json.loads((args.inspection).read_text())
            assert proof['candidate_elf_sha256']==args.elf_sha256.upper()
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(proof['finished_utc'])).total_seconds()
            assert 0 <= age <= 900, 'fresh protected SRAM inspection required'
            assert all(x['match'] for x in proof['immutable_sram_proof']) and proof['pairing_persistence_verified']
            m=proof['metadata']
            assert m['settings_writes']==m['settings_busy']==m['settings_io']==m['recovery']==m['fence']==0
            assert m['record_generation']==1 and m['record_crc']==0x72B6B9AF and m['record_length']==705
            if uart is None:
                uart=serial.Serial('COM6',115200,timeout=.1)
                worker=threading.Thread(target=collect);worker.start()
            if usb is None: usb=UsbCli(find_cn8(None,10))
            await connect()
            for n in range(6): await ping('CA-BEFORE-'+str(n))
            report['ready_snapshot']=await asyncio.to_thread(snapshot)
            report['phase']='baseline';save()
            print('READY BLE/Cloud baseline; no ToF subscription writes.',flush=True)
            before=await asyncio.to_thread(snapshot);report['before']=before;save()
            if aggregate['profiles']:
                assert before['recovery']['attempts']==aggregate['profiles'][-1]['final_attempts'], 'additional recovery between profiles'
            assert before['wifi_ip'] and before['radio_ready'] and before['tof_ready'] and before['cloud_paired']
            assert before['route']==['CLOUD','CLOUD'] and before['recovery']['state']==0
            assert 'ToF image notifications: off' in before['subscriptions'], 'unexpected BLE image subscription at baseline'
            assert before['cloud_frames']>report['ready_snapshot']['cloud_frames'], 'no newly accepted Cloud frames'
            assert worker.is_alive() and not stop.is_set(), 'causal UART collector unavailable; no fault submitted'
            old_notice=before['notice']['sequence']
            start=len(received)
            await client.write_gatt_char(RX,b'help\r',response=True)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                state=safe_receive(start)
                if 'complete' in state['results']: raise RuntimeError('HELP completed before fault; no in-flight fault submitted')
                if 'accepted' in state['results']: break
                await asyncio.sleep(.001)
            else: raise TimeoutError('HELP acceptance absent; no fault submitted')
            report['inflight_before_fault']=state
            report['fault_submissions']=1
            usb.serial.write(b'radio fault-test\r')
            report['phase']='fault_submitted';save()
            print('FAULT submitted once during accepted unfinished BLE HELP; Cloud route active.',flush=True)
            answer=await asyncio.to_thread(usb._read,2,True)
            report['fault_admitted']='Radio recovery requested' in answer
            assert report['fault_admitted'], 'fault request not admitted'
            report['old_link_receive_at_retirement']=safe_receive(start)
            try:
                await client.stop_notify(TX)
                report['old_cli_notification_stopped']=True
            except Exception as exc:
                report['old_cli_notification_stop_error']=type(exc).__name__
            await client.disconnect()
            report['old_host_link_retired_before_ncp_return']=not client.is_connected
            assert report['old_host_link_retired_before_ncp_return'], 'old Windows link not retired'
            print('OLD HOST LINK RETIRED: no old GATT session survives NCP reinitialization.',flush=True)
            deadline=time.monotonic()+80
            while time.monotonic()<deadline:
                token='CA-USB-'+str(len(report['usb_pings']));tick=time.monotonic()
                reply=await asyncio.to_thread(usb.command,'debug ping '+token,2)
                row={'token':token,'ms':round((time.monotonic()-tick)*1000,2),'ok':'PONG '+token+' ' in reply}
                report['usb_pings'].append(row);assert row['ok'],'USB ping absent'
                current=await asyncio.to_thread(snapshot);report['samples'].append(current);save()
                assert current['tof_ready'] and ((current['tof_frame']-before['tof_frame'])&0xffff)>0, 'ToF stopped'
                assert current['recovery']['state']!=3,'recovery failed closed'
                if current['recovery']['ready']==before['recovery']['ready']+1 and current['recovery']['state']==0:
                    if current['wifi_ip'] and current['cloud_frames']>=before['cloud_frames']+5: break
                await asyncio.sleep(.2)
            else: raise TimeoutError('Radio/Wi-Fi/Cloud return deadline exceeded')
            after=report['samples'][-1];report['after']=after
            report['old_link_receive']=safe_receive(start)
            assert after['recovery']['attempts']==before['recovery']['attempts']+1
            assert after['recovery']['failed']==before['recovery']['failed']
            assert after['cloud_paired'] and after['radio_ready'] and after['route']==before['route']
            assert any(e['numbers'].get('genuine_fence')=='1' for e in report['events']), 'genuine fence missing'
            assert any(e['start'] and e['words'].get('reason')=='TEST_MISSING_RESPONSE' for e in report['events'])
            report['phase']='reconnect';save()
            print('RECOVERED saved Wi-Fi/pairing/Cloud frames; reconnecting BLE to inspect UNKNOWN notice.',flush=True)
            if client and client.is_connected: await client.disconnect()
            await connect()
            report['proactive_notice_receive']=safe_receive()
            # Model an application attaching its receiver after Windows restored
            # the CCCD. The next command is new, never a replay of interrupted HELP.
            if report['profile_index'] > 1:
                received=bytearray()
                report['late_application_observer']=True
            await ping('CA-READY-'+str(report['profile_index']))
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                notices=safe_receive()['notices']
                if any('sequence='+str(old_notice+1)+' ' in x and 'outcome=unknown' in x for x in notices): break
                await asyncio.sleep(.05)
            else: raise TimeoutError('New-generation UNKNOWN notice missing')
            report['new_link_receive']=safe_receive()
            for n in range(6): await ping('CA-AFTER-'+str(n))
            report['new_link_final_receive']=safe_receive()
            assert report['new_link_final_receive']['help_banners']==0, 'old HELP reply leaked into fresh generation'
            assert report['new_link_final_receive']['results'].count('complete')==7, 'unexpected final in fresh generation'
            observed=received.decode('utf-8','replace')
            event_at=observed.find('[CLI-EVENT] event=RADIO_RECOVERY sequence='+str(old_notice+1)+' ')
            pong_at=observed.find('PONG CA-READY-'+str(report['profile_index'])+' ')
            report['unknown_before_new_pong']=0<=event_at<pong_at
            assert report['unknown_before_new_pong'], 'new command completed before its recovery warning'
            report['final']=await asyncio.to_thread(snapshot);save()
            report['new_recovery_starts']=[e for e in report['events'] if e['start'] and e['words'].get('reason') in ('AT_FENCED','DNS_EXPIRED','TEST_MISSING_RESPONSE','EXPLICIT_REQUEST')]
            assert len(report['new_recovery_starts'])==1, 'missing or unexpected causal recovery record'
            assert report['final']['recovery']['attempts']==before['recovery']['attempts']+1, 'extra recovery detected'
            assert report['final']['route']==['CLOUD','CLOUD'], 'fresh BLE CLI link stole Cloud route'
            assert 'ToF image notifications: off' in report['final']['subscriptions'], 'fresh CLI-only link enabled image CCCD'
            assert report['final']['cloud_frames']>after['cloud_frames'], 'Cloud images did not advance with fresh BLE CLI'
            notice=report['final']['notice']
            report['reply_active_at_recovery']=notice['active_reply']>0
            report['reply_transfer_in_flight_at_recovery']=notice['tx_slots']>0
            assert report['reply_transfer_in_flight_at_recovery'], 'queued BLE reply transmission at recovery unproven'
            report['executing_cli_body_at_fault_proven']=False
            report['acceptance_scope']='Queued BLE reply interrupted; UNKNOWN delivered; no replay. Formatting-active and physical DMA abort not proven.'
            report['passed']=True;report['phase']='done'
        except Exception as exc:
            report['failure']=type(exc).__name__+': '+str(exc)
            report['phase']='failed'
            print('STOP '+report['failure'],flush=True)
        finally:
            if client and client.is_connected:
                try: await client.stop_notify(TX)
                except Exception: pass
                try: await client.disconnect()
                except Exception as exc: report['ble_cleanup_error']=type(exc).__name__
            retain = report['passed'] and report['profile_index'] < args.profiles
            if not retain:
                if usb: usb.close()
                stop.set()
                if worker: worker.join(3)
                if uart: uart.close()
            report['handles_retained_for_next_campaign_profile']=retain
            report['handles_closed']={'usb':usb is None or not usb.serial.is_open,
                'uart':uart is None or not uart.is_open,'collector':worker is None or not worker.is_alive(),
                'ble':client is None or not client.is_connected}
            report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
            print(json.dumps({'passed':report['passed'],'fault_submissions':report['fault_submissions'],
                'failure':report.get('failure'),'ble_finals':len(report['ble_commands']),
                'usb_pings':len(report['usb_pings']),'reply_active_at_recovery':report.get('reply_active_at_recovery'),
                'dma_in_flight_abort_proven':False,'handles_closed':report['handles_closed']}),flush=True)
        if not report['passed']: raise SystemExit(1)

    aggregate={'profiles':[],'passed':False,'elf_sha256':args.elf_sha256,'automatic_replay':False,'image_subscription_writes':False}
    BASE=HERE
    for index in range(1,args.profiles+1):
        HERE=BASE/('profile-'+str(index));HERE.mkdir()
        report={'passed':False,'phase':'setup','profile_index':index,'started_utc':datetime.now(timezone.utc).isoformat(),
                'pair_requested':False,'fault_submissions':0,'automatic_command_replay':False,
                'firmware_reset_load_flash_or_credential_write':False,'dma_in_flight_abort_proven':False,
                'ble_commands':[],'connections':[],'events':[],'usb_pings':[],'samples':[]}
        client=None;received=bytearray()
        try:asyncio.run(main())
        except SystemExit:
            aggregate['profiles'].append({'index':index,'passed':False,'failure':report.get('failure')})
            aggregate['events']=campaign_events
            atomic_json(BASE/'summary.json',aggregate);raise
        aggregate['profiles'].append({'index':index,'passed':True,'recovery_ms':report['after']['recovery']['elapsed_ms'],
            'final_attempts':report['final']['recovery']['attempts'],
            'ble_finals':len(report['ble_commands']),'usb_pings':len(report['usb_pings']),
            'ble_max_ms':max(p['ms'] for p in report['ble_commands']),
            'usb_max_ms':max(p['ms'] for p in report['usb_pings']),
            'cloud_frames':[report['before']['cloud_frames'],report['after']['cloud_frames'],report['final']['cloud_frames']]})
        aggregate['events']=campaign_events
        atomic_json(BASE/'summary.json',aggregate)
    aggregate['passed']=True;aggregate['events']=campaign_events
    aggregate['handles_closed']=report['handles_closed'];atomic_json(BASE/'summary.json',aggregate)
    print(json.dumps(aggregate),flush=True)



if __name__ == "__main__":
    cli_main()
