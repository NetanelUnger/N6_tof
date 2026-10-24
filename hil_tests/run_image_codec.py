"""Bounded real BLE codec test. Requires the matching held hardware lease.
Never pairs, resets, installs firmware or changes persistent settings. Captures
wire notifications for replay through the website's actual decoder.
"""
from cli_text_protocol import reply_finished, reply_succeeded, reply_results

import argparse, asyncio, json, time
from pathlib import Path
from bleak import BleakClient, BleakScanner
from ble_inspector import TofFrameAssembler
ROOT=Path(__file__).resolve().parents[1]
RX='7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
TX='7a1e0003-b5a3-f393-e0a9-e50e24dcca9e'
IMAGE='7a1e0004-b5a3-f393-e0a9-e50e24dcca9e'
async def run(args):
    owner=json.loads((ROOT/'.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert owner['thread']==args.owner_thread,'matching exclusive lease required'
    assert not args.report.exists(),'choose a fresh report path'
    report={'passed':False,'notifications':[],'frames':[],'commands':[],'modes':[],'pair_requested':False}
    assembler=TofFrameAssembler();cli=bytearray();client=None
    def receive(_,data):
        report['notifications'].append(bytes(data).hex())
        frame=assembler.push(data)
        if frame:report['frames'].append({**frame,'host_s':time.monotonic()})
    async def command(text):
        begin=len(cli);start=time.monotonic()
        await client.write_gatt_char(RX,(text+'\r').encode(),response=True)
        while time.monotonic()-start<8:
            reply=cli[begin:].decode('utf-8','replace')
            if reply_succeeded(reply):
                report['commands'].append({'command':text,'ms':round((time.monotonic()-start)*1000,2),'reply':reply});return reply
            await asyncio.sleep(.01)
        raise TimeoutError('No completed reply: '+text)
    try:
        devices=await BleakScanner.discover(timeout=8)
        matches=[d for d in devices if (d.name or '').startswith('N6-MAINT-')]
        assert len(matches)==1,f'expected one N6 advertiser, found {len(matches)}'
        client=BleakClient(matches[0],pair=False,timeout=20)
        await client.connect();report['mtu']=client.mtu_size
        await client.start_notify(TX,lambda _,data:cli.extend(data))
        original=await command('MAP ENCODING')
        original_mode=next((m for m in ('RAW','UINT16','UINT8','JPEG') if 'Wireless encoding: '+m in original),None)
        assert original_mode,'firmware does not implement codec selection'
        await client.start_notify(IMAGE,receive);await command('MAP ON')
        try:
            for mode,code in [('RAW',1),('UINT16',2),('UINT8',3),('JPEG',4),('RAW',1)]:
                await command('MAP ENCODING '+mode);begin=len(report['frames']);deadline=time.monotonic()+25
                while True:
                    frames=[f for f in report['frames'][begin:] if f['pixel_format']==code]
                    if len(frames)>=6:break
                    assert time.monotonic()<deadline,'missing complete frames in '+mode
                    reply=await command('debug ping codec-'+mode);assert 'PONG codec-'+mode in reply
                    await asyncio.sleep(.2)
                assert all((code == 4 and 0 < f['total'] <= 9072) or (code != 4 and f['total']==f['width']*f['height']*{1:4,2:2,3:1}[code]) for f in frames)
                assert all(f['version']==3 for f in frames)
                report['modes'].append({'mode':mode,'frames':len(frames),'payload':frames[-1]['total']})
                print('PASS',mode,len(frames),'frames',frames[-1]['total'],'bytes',flush=True)
            assert assembler.crc_errors==0 and assembler.dropped==0
            report['passed']=True
        finally:
            if client.is_connected:
                await command('MAP ENCODING '+original_mode)
                await client.stop_notify(IMAGE)
    except Exception as exc:
        report['failure']=type(exc).__name__+': '+str(exc);raise
    finally:
        if client and client.is_connected:await client.disconnect()
        report['crc_errors']=assembler.crc_errors;report['dropped']=assembler.dropped
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--owner-thread',required=True);p.add_argument('--report',type=Path,required=True)
    asyncio.run(run(p.parse_args()))
