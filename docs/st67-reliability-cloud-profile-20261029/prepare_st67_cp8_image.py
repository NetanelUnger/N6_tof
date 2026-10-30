from pathlib import Path
import ast, hashlib, json
here=Path(__file__).parent
root=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
source=root/'hil_tests/run_ble_npu_soak.py'
# Reuse the reviewed CP4 adapter map, never execute its old output writes.
module=ast.parse((here/'prepare_st67_image52.py').read_text())
changes=ast.literal_eval(next(n.value for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='changes' for t in n.targets)))
text=source.read_text()
for old,new in changes.items():
    assert old in text,old
    text=text.replace(old,new)
text=text.replace("device=next(d for d in seen if d.address.upper()=='40:82:7B:03:B8:FB')", "address=re.search(r'Address:\\s*([0-9A-F:]{17})',link)[1];device=next(d for d in seen if d.address.upper()==address.upper())")
assert 'require_receive_window_counts(report' in text
ast.parse(text)
target=here/'st67_cp8_image52.py';assert not target.exists();target.write_text(text)
wrapper=(here/'st67_image52_owned_v2.py').read_text()
wrapper=wrapper.replace('st67-cp4-20261028','st67-cp8-cloud-profiles').replace('image120-v2','image120-connected-cloud').replace('st67-baseline52-images-v2','st67-cp8-images-cloud204').replace("'st67_image52.py'","'st67_cp8_image52.py'")
wrapper=wrapper.replace('import serial','import serial\nfrom serial.tools import list_ports')
wrapper=wrapper.replace("p=serial.Serial(port=None", "ports=[p for p in list_ports.comports() if p.vid==0x0483 and p.pid==0x5740 and p.serial_number=='N6TOF001'];assert len(ports)==1;\n        p=serial.Serial(port=None")
wrapper=wrapper.replace("p.port='COM8'","p.port=ports[0].device")
wrapper=wrapper.replace("('version','tof status','dataset stream status','rps status','cloud status')", "('version','status','ble status','radio status','tof status','dataset stream status','rps status','cloud status')")
wrapper=wrapper.replace("('version','tof status','dataset stream status','rps status','radio status','cloud status')", "('version','status','ble status','tof status','dataset stream status','rps status','radio status','cloud status')")
wrapper=wrapper.replace("port.close();port=None", "assert 'last 204' in r['before']['cloud status'],'Cloud baseline changed';assert 'link: disconnected' in r['before']['ble status'];\n        port.close();port=None")
ast.parse(wrapper)
target=here/'st67_cp8_image52_owned.py';assert not target.exists();target.write_text(wrapper)
out=here/'evidence/st67-cp8-cloud-profiles'
(out/'image-harness-adaptations.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'adaptations':changes,'additional_changes':['USB identity exact VID/PID/serial','BLE address read from current status','fresh immutable CP8 output','assert Cloud204 before profile','frozen receive window preserved'],'purpose':'New baseline after Cloud409->204 activation; BLE images+NPU+CLI with active Cloud polling, not actual Cloud CLI workload or BLE-only acceptance'},indent=2)+'\n')
print('Prepared corrected CP8 image collector and lease/cleanup wrapper; syntax PASS.')
