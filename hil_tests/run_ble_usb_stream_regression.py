"""Real BLE images must survive repeated USB console open/close cycles.
Uses the shared hardware lease; never pairs, resets or installs firmware.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'training/scripts'))
from ble_console_core import BleSession,IMAGE
from ble_console_images import decode_pixels
from ble_console_soak import UartEvidence,usb_snapshot

async def run(args):
    folder=ROOT/'training/reports/ble_console'/('usb-isolation-'+time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(exist_ok=False)
    report={'passed':False,'cycles':[],'commands':[]}
    session=BleSession();capture=UartEvidence(args.uart,folder/'uart.jsonl')
    demo_owned=False
    async def command(text):
        row=await session.command(text,disconnect_on_error=False)
        report['commands'].append(row)
        if not row['passed']:raise RuntimeError(row['response'])
        return row['response']
    try:
        await session.connect(args.address);capture.start()
        version=await command('version')
        assert f'Firmware version: {args.version}' in version
        assert 'requested NONE, active NONE' in await command('tof status')
        assert 'Demo map: OFF' in await command('DEMO MAP STATUS')
        original=await command('MAP ENCODING')
        session.original_encoding=next(mode for mode in ('RAW','UINT16','UINT8','JPEG') if 'Wireless encoding: '+mode in original)
        await command('MAP ENCODING UINT8')
        session.image_subscribed=True;generation=session.generation
        await session.client.start_notify(IMAGE,lambda _,data:session._image_notify(generation,data))
        for mode in ('demo1000','demo300','sensor'):
            if mode=='sensor':
                await command('DEMO MAP OFF');demo_owned=False
                await command('MAP ON')
            else:
                await command('DEMO MAP ON '+mode[4:]+' BLE');demo_owned=True
            await asyncio.sleep(2)
            for index in range(3):
                before=session.images.completed
                snapshot=await asyncio.to_thread(usb_snapshot,args.usb)
                after_close=session.images.completed
                await asyncio.sleep(3)
                assert session.connected,'BLE disconnected'
                assert session.images.completed>after_close,'No new image after USB close'
                frame=session.latest_image;decode_pixels(frame)
                assert frame['npu']['state']==(3 if mode=='sensor' else 0)
                status=await command('DEMO MAP STATUS')
                assert ('Demo map: OFF' if mode=='sensor' else 'Demo map: ON') in status
                assert 'requested BLE, active BLE' in await command('tof status')
                reply=await command(f'debug ping USB-{mode}-{index}')
                assert f'PONG USB-{mode}-{index} ' in reply
                row={'mode':mode,'cycle':index+1,'before':before,'after_close':after_close,
                     'after_wait':session.images.completed,'source_id':frame['frame_id'],
                     'demo_status':status,'usb':snapshot}
                report['cycles'].append(row)
                print(json.dumps({k:v for k,v in row.items() if k not in ('usb','demo_status')}),flush=True)
        report['crc_errors']=session.images.crc_errors
        report['assembly_drops']=session.images.dropped
        assert session.images.crc_errors==0 and session.image_errors==0
        report['passed']=True
    except Exception as error:
        report['error']=repr(error);print('FAIL',repr(error),flush=True)
    finally:
        report['lifecycle_before_cleanup']=list(session.lifecycle)
        try:
            if demo_owned and session.connected and not session.tainted:await command('DEMO MAP OFF')
            await session.stop_images()
            report['final_tof']=await command('tof status')
            report['final_encoding']=await command('MAP ENCODING')
            await session.close()
        except Exception as error:
            report['cleanup_error']=repr(error);report['passed']=False
            try:await session.close(graceful=False)
            except Exception as close_error:report['close_error']=repr(close_error)
        capture.close();report['uart_error']=capture.error
        if capture.error:report['passed']=False
        if not report.get('close_error'):
            report['scan_after']=await session.scan()
        (folder/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('RESULT',report['passed'],str(folder/'result.json'),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True)
    parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--usb',default='COM8');parser.add_argument('--uart',default='COM6')
    raise SystemExit(asyncio.run(run(parser.parse_args())))
