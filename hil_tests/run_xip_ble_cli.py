"""Five bounded legacy BLE CLI pings; never pairs or selects an image stream."""
from cli_text_protocol import reply_finished, reply_succeeded, reply_results

def main():
    import argparse,asyncio,importlib.util,json,re,subprocess,time
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--owner-thread');parser.add_argument('--label')
    parser.add_argument('--pings',type=int,default=5,choices=range(1,101))
    parser.add_argument('--interval-ms',type=int,default=0,choices=range(0,1001))
    args=parser.parse_args()
    if not args.execute:print('PASS BLE preflight; no hardware access');return
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),'branch','--show-current'],text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    assert args.owner_thread and owner['thread']==args.owner_thread
    spec=importlib.util.spec_from_file_location('lease',root/'hil_tests/n6_hardware_lease.py');lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid']);assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    assert args.label and re.fullmatch('[a-z0-9-]+',args.label)
    output=root/('.local-dependencies/xip/ble-cli-'+args.label+'.json');assert not output.exists()
    result={'pair_requested':False,'image_subscription':False,'sensor_export_requested':False,'passed':False,'pings':[]}
    async def run():
        from bleak import BleakClient,BleakScanner
        device=await BleakScanner.find_device_by_address('40:82:7B:03:B8:FB',timeout=10)
        assert device is not None,'Exact N6 advertisement absent; no connection attempted'
        async with BleakClient(device,pair=False,timeout=20) as client:
            paired=client._backend._requester.device_information.pairing.is_paired
            result['OS_paired']=paired;assert not paired,'OS already paired; stop without changing pairing'
            data=bytearray();tx='7a1e0003-b5a3-f393-e0a9-e50e24dcca9e';rx='7a1e0002-b5a3-f393-e0a9-e50e24dcca9e'
            await client.start_notify(tx,lambda _,part:data.extend(part))
            try:
                for i in range(args.pings):
                    token='XIP17-'+str(i);begin=len(data);start=time.monotonic()
                    await client.write_gatt_char(rx,('debug ping '+token+'\r').encode(),response=True)
                    while time.monotonic()-start<10:
                        text=data[begin:].decode('utf8','replace')
                        if 'PONG '+token+' ' in text and reply_succeeded(text):break
                        await asyncio.sleep(.01)
                    else:raise TimeoutError('BLE PONG/final missing')
                    ms=(time.monotonic()-start)*1000;result['pings'].append({'token':token,'ms':ms})
                    print('BLE PONG/final',i+1,round(ms,2),'ms',flush=True)
                    if args.interval_ms:await asyncio.sleep(args.interval_ms/1000)
            finally:await client.stop_notify(tx)
        result['disconnected']=True
        result['passed']=len(result['pings'])==args.pings and max(x['ms'] for x in result['pings'])<=1500
    try:asyncio.run(run())
    except BaseException as error:result['error']=repr(error);raise
    finally:output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print('BLE RESULT',json.dumps(result),flush=True)
if __name__=='__main__':main()
