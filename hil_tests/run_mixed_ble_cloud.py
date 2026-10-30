"""Three-minute BLE image/CLI + real Cloud CLI load; no firmware or pairing changes."""
import asyncio,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'training/scripts'))
from ble_console_core import BleSession
from ble_console_soak import run_soak,UartEvidence,usb_snapshot
from run_xip_usb_update import command as usb_command
import serial

async def main():
    replace_workspace='--replace-existing-workspace' in sys.argv
    folder=ROOT/'training/reports/ble_console'/('mixed-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
    s=BleSession();result={'passed':False,'phases':[]};worker=None;log=None;demo=False
    capture=UartEvidence('COM6',folder/'uart.jsonl')
    async def command(text):
        row=await s.command(text,disconnect_on_error=False)
        if not row['passed']:raise RuntimeError(row['response'])
        return row
    def preflight():
        with serial.Serial('COM8',115200,timeout=.1,write_timeout=2) as port:
            port.dtr=True;time.sleep(.3)
            return {name:usb_command(port,name) for name in ('version','cloud status','tof status')}
    try:
        await s.connect('40:82:7B:03:B8:FB');capture.start()
        proof=await asyncio.to_thread(preflight)
        assert 'last 409' in proof['cloud status'] or replace_workspace,'Workspace is active; explicit replacement authorization required'
        result['workspace_replacement_authorized']=replace_workspace
        assert 'requested NONE, active NONE' in proof['tof status']
        assert 'Firmware version: 58' in proof['version']
        (folder/'preflight.json').write_text(json.dumps(proof,indent=2))
        owner=json.loads((ROOT.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
        log=(folder/'cloud.log').open('w',encoding='utf-8')
        worker=subprocess.Popen(['node',str(ROOT/'hil_tests/run_mixed_cloud_worker.mjs'),'--folder',str(folder),'--owner-thread',owner['thread']]+(['--replace-existing-workspace'] if replace_workspace else []),stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
        deadline=time.monotonic()+100
        while not (folder/'cloud-ready.json').exists():
            if worker.poll() is not None:raise RuntimeError('Cloud startup failed; see cloud-result.json/log')
            if time.monotonic()>deadline:raise TimeoutError('Cloud startup exceeded100s')
            await asyncio.sleep(.2)
        await s.start_images('RAW')
        (folder/'start').write_text('start')
        for mode,interval in (('RAW',300),('UINT8',100),('JPEG',100)):
            await command(f'DEMO MAP ON {interval} BLE');demo=True
            def progress(row):
                print(json.dumps({'mode':mode,'interval_ms':interval,**row}),flush=True)
                if worker.poll() not in (None,0):raise RuntimeError('Cloud worker failed during BLE load')
            report,path=await run_soak(s,60,mode,report_dir=folder,progress=progress)
            row={k:report.get(k) for k in ('passed','frames_received','crc_errors','assembly_drops','max_image_gap_s','failure','disconnect_observed_before_cleanup')}
            row.update(mode=mode,interval_ms=interval,report=path)
            if s.connected and not s.tainted:row['demo_status']=await command('DEMO MAP STATUS')
            result['phases'].append(row)
            if not report['passed']:break
        (folder/'stop').write_text('stop')
        await asyncio.to_thread(worker.wait,55)
        result['cloud']=json.loads((folder/'cloud-result.json').read_text())
        result['passed']=len(result['phases'])==3 and all(x['passed'] for x in result['phases']) and result['cloud']['passed']
    except Exception as error:
        result['error']=repr(error);print('FAIL',repr(error),flush=True)
    finally:
        (folder/'stop').write_text('stop')
        if worker and worker.poll() is None:
            try:await asyncio.to_thread(worker.wait,55)
            except subprocess.TimeoutExpired:
                worker.terminate();await asyncio.to_thread(worker.wait,10);result['worker_forced_stop']=True;result['passed']=False
        if log:log.close()
        result['lifecycle_before_cleanup']=list(s.lifecycle)
        try:
            if s.lease.process is not None:result['usb_after']=await asyncio.to_thread(usb_snapshot,'COM8')
        except Exception as error:result['usb_error']=repr(error)
        try:
            if demo and s.connected and not s.tainted:await command('DEMO MAP OFF')
            await s.close()
        except Exception as error:
            result['cleanup_error']=repr(error);result['passed']=False
            try:await s.close(graceful=False)
            except Exception as close_error:result['close_error']=repr(close_error)
        capture.close();result['uart_error']=capture.error
        if capture.error:result['passed']=False
        if not result.get('close_error'):result['scan_after']=await s.scan()
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        print('RESULT',result['passed'],str(folder/'result.json'),flush=True)
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
