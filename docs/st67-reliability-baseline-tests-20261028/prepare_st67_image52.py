from pathlib import Path
import hashlib,json,ast
here=Path(__file__).parent
root=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
p=root/'hil_tests/run_ble_npu_soak.py';text=p.read_text()
changes={
    "here.parent/'n6-hardware-owner.json'":"root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json'",
    "here.parent/'n6-hardware-owner.lock'":"root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.lock'",
    "'scope':'BLE_ONLY'":"'scope':'B52_BLE_IMAGES_NPU_CLI_WITH_EXISTING_WIFI_CLOUD_POLLING_NOT_ACTIVE_CLOUD_CONTROL'",
    "'radio_ready':'state=available reason=READY' in radio":"'radio_ready':'manager: ready' in radio and 'W6X_Init: passed' in radio and 'NCP recovery: state=0 stage=0' in radio",
    "assert not before['wifi_ip'] and not before['http_active'] and before['cloud_paired']":"assert before['wifi_ip'] and before['cloud_paired']",
    "assert not snap['wifi_ip'] and not snap['http_active'] and snap['cloud_paired']":"assert snap['wifi_ip'] and snap['cloud_paired']",
    "assert not current['wifi_ip'] and not current['http_active'] and current['cloud_frames']==before['cloud_frames']":"assert current['wifi_ip'] and current['cloud_frames']==before['cloud_frames']",
    "for kind in ('public','random','automatic'):":"for kind in ('automatic',):",
    "opts={'use_cached_services':True}":"opts={'use_cached_services':False}",
    "at=len(cli);await client.write_gatt_char(RX,b'map on\\r',response=True)":"at=len(cli);report['map_on_requested']=True;await client.write_gatt_char(RX,b'map on\\r',response=True)",
    "before=state();report['baseline']=before;":"report['version']=usb.command('version',3);assert 'Firmware version: 52\\r\\n' in report['version'];report['image_encoding']=usb.command('MAP ENCODING',3);before=state();report['baseline']=before;",
    "PASS BLE-only image/NPU cycle ":"PASS B52 BLE-image/NPU background-Wi-Fi cycle ",
}
for old,new in changes.items():
    assert old in text,old
    text=text.replace(old,new)
text='''"""B52 bounded BLE image/NPU/CLI with existing Wi-Fi/Cloud polling.
Derived from the existing BLE-only receiver with identical latency/gap/CRC/NPU
gates. This is NOT BLE-only or active Cloud-control acceptance. No Wi-Fi,
Cloud pairing or persistent settings setters; one automatic nonbonded connect.
"""\n'''+text[text.index('from cli_text_protocol'):]
ast.parse(text)
(here/'st67_image52.py').write_text(text)
wrapper=(here/'st67_hil52.py').read_text().replace('hil100-wrapper.json','image120-wrapper.json').replace('hil100.log','image120.log')
wrapper=wrapper.replace("str(ROOT/'hil_tests/run_xip_model_regression.py'),\n             '--owner-thread',owner['thread'],'--label','st67-baseline52','--version','52'", "str(Path(__file__).parent/'st67_image52.py'),\n             '--owner-thread',owner['thread'],'--label','st67-baseline52-images','--duration','120'")
wrapper=wrapper.replace("ROOT/'.local-dependencies/xip/hil-XIP-v52-st67-baseline52.json'", "ROOT/'.local-dependencies/diagnostics/st67-baseline52-images/report.json'")
wrapper=wrapper.replace("r['hil']", "r['profile']").replace("if 'hil' in r:","if 'profile' in r:")
wrapper=wrapper.replace("'HIL100 existing USB same-frame tensor/NPU; temporary dataset USB only; restore dataset off; no firmware/reset/settings/Cloud stream'", "'B52 BLE image/NPU/CLI120s with existing Wi-Fi/Cloud; restore map off; no reset/firmware/pair/settings writes'")
wrapper=wrapper.replace("port=openusb();r['after']=", "port=openusb();\n        if r.get('profile',{}).get('map_on_requested'):r['map_off_cleanup']=cli(port,'MAP OFF')\n        r['after']=")
wrapper=wrapper.replace("('frames','exact_tensors','npu_frames','max_score_delta','crc_errors','sensor_fps','elapsed_s','passed')", "('soak_counts','latency_ms','image_crc_errors','image_drops_during_soak','max_result_receive_gap_s','max_image_receive_gap_s','max_event_loop_lag_s','elapsed_s','passed','failure')")
# The child runs outside hil_tests, so import its helpers through PYTHONPATH.
wrapper=wrapper.replace("r['command']=cmd", "r['command']=cmd;os.environ['PYTHONPATH']=str(ROOT/'hil_tests')")
ast.parse(wrapper)
(here/'st67_image52_owned.py').write_text(wrapper)
(here/'evidence/st67-cp4-20261028/image-harness-adaptations.json').write_text(json.dumps({'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'adaptations':changes,'profile':'120s bounded, preserves original receiver latency/gap/CRC/NPU gates; existing Wi-Fi stays enabled; not V01 or fullV04'},indent=2)+'\n')
print('Prepared bounded image profile, syntax PASS; no hardware opened.')
