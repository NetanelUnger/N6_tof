"""RAM candidate build/load with read-only settings and an exclusive host lease."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import hashlib,json,re,shutil,subprocess,sys,time,uuid
from common import PROJECT_ROOT,GENERATED_ROOT,atomic_json,sha256_file,utc_now

@contextmanager
def hardware_lease(owner):
    process=subprocess.Popen([sys.executable,'-B',str(PROJECT_ROOT/'hil_tests/n6_hardware_lease.py'),
                              '--owner-thread',owner],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,text=True)
    try:
        line=process.stdout.readline()
        if '"ownership": "HELD"' not in line:
            process.wait(timeout=5)
            raise RuntimeError('BLOCKED: hardware lease unavailable: '+line.strip())
        yield
    finally:
        if process.poll() is None:
            output,_=process.communicate('release\n',timeout=10)
            if process.returncode or 'OWNERSHIP RELEASED' not in output:
                raise RuntimeError('Hardware lease release was not confirmed.')


def idle_board(expected_device=None,board_serial=None):
    import serial
    from serial.tools import list_ports
    from sample_sources import UsbSampleSource
    ports=list(list_ports.comports())
    uart=[p for p in ports if p.vid==0x0483 and p.serial_number and p.serial_number!='N6TOF001']
    cdc=[p for p in ports if p.vid==0x0483 and p.pid==0x5740 and p.serial_number=='N6TOF001']
    if len(uart)!=1 or len(cdc)!=1 or (board_serial and uart[0].serial_number!=board_serial):
        raise RuntimeError('BLOCKED: expected one matching ST-LINK and N6 CDC board.')
    source=UsbSampleSource();source._serial=serial.Serial(cdc[0].device,115200,timeout=.1,write_timeout=2)
    try:
        time.sleep(.15);source._serial.reset_input_buffer()
        state={command:source.command(command,marker) for command,marker in
               [('ble status',b'BLE GATT:'),('tof status',b'ToF state:'),
                ('dataset stream status',b'Dataset stream:'),('radio info',b'NCP MAC:')]}
        if (re.search(r'link:\s*connected\b',state['ble status']) or
            'Dataset stream: off' not in state['dataset stream status'] or 'Map: off' not in state['tof status']):
            raise RuntimeError('BLOCKED: another BLE client or image/dataset stream owns the board.')
        match=re.search(r'NCP MAC:\s*([0-9A-Fa-f:]{17})',state['radio info'])
        if not match:raise RuntimeError('BLOCKED: board canonical identity unavailable.')
        device='n6:'+match[1].lower()
        if expected_device and device!=expected_device:raise RuntimeError('BLOCKED: device identity differs from selected target.')
        return {'device':device,'board_serial':uart[0].serial_number,'uart':uart[0].device,'cdc':cdc[0].device,'runtime':state}
    finally:source._serial.close();source._serial=None


def build_candidate(version=None, *, keep_network=False):
    headers=[PROJECT_ROOT/'AppliNonSecure/Core/Inc/app_features.h',PROJECT_ROOT/'AppliNonSecure/Core/Inc/w61_driver_config.h',PROJECT_ROOT/'Common/Update/firmware_build_version.h']
    original={p:p.read_bytes() for p in headers}
    settings=(PROJECT_ROOT/'AppliNonSecure/Core/Inc/app_settings.h').read_text()
    if not all(x in settings for x in ('#define APP_SETTINGS_WRITES_ENABLED 0U','#define APP_SETTINGS_TRANSITION_ENABLED 0U')):
        raise RuntimeError('BLOCKED: RAM tests require persistent settings writes disabled.')
    folder=GENERATED_ROOT/'ram_candidates'/uuid.uuid4().hex;folder.mkdir(parents=True)
    debug=PROJECT_ROOT/'AppliNonSecure/Debug';backup=folder/'ordinary-debug';backup.mkdir()
    artifacts=[debug/('N6_AppliNonSecure.'+suffix) for suffix in ('elf','bin','map')]
    hashes={str(p):sha256_file(p) for p in artifacts}
    for p in artifacts:shutil.copy2(p,backup/p.name)
    info={'status':'BUILDING','created_utc':utc_now(),'folder':str(folder),'settings_writes':False,
          'ncp_preserve':True,'ble_only':not keep_network,'minimum_heap':369072,'ordinary_debug_hashes':hashes}
    started=time.monotonic()
    try:
        changes=[(headers[0],rb'(?m)^#define APP_DEMO_BLE_ONLY \([01]U\)$',
                  b'#define APP_DEMO_BLE_ONLY (0U)' if keep_network else b'#define APP_DEMO_BLE_ONLY (1U)'),
                 (headers[1],rb'(?m)^#define W61_CONFIG_PRESERVE       \([01]\)$',
                  b'#define W61_CONFIG_PRESERVE       (1)')]
        for p,pattern,new in changes:
            # Accept both the repository LF and Windows CRLF files.
            payload=original[p].replace(b'\r\n',b'\n')
            payload,count=re.subn(pattern,lambda match:new,payload)
            if count!=1:raise RuntimeError('Unexpected safe RAM build flags.')
            p.write_bytes(payload)
        current=int(re.search(rb'NATI_LAB_FIRMWARE_VERSION\s+\((\d+)UL\)',original[headers[2]])[1])
        version=current if version is None else version
        if version not in (current,current+1):raise RuntimeError('RAM candidate version must be current or current+1.')
        headers[2].write_bytes(re.sub(rb'(NATI_LAB_FIRMWARE_VERSION\s+\()\d+(UL\))',lambda m:m[1]+str(version).encode()+m[2],original[headers[2]]))
        info['firmware_version']=version
        with (folder/'build.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(PROJECT_ROOT/'Tools/Build-NonSecureIncremental.ps1')],cwd=PROJECT_ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        if result.returncode:raise RuntimeError('RAM candidate build failed; see '+str(folder/'build.log'))
        text=(folder/'build.log').read_text(encoding='utf-8-sig')
        heap=int(re.search(r'C heap capacity: (\d+)',text)[1]);info['heap']=heap
        for p in artifacts:shutil.copy2(p,folder/('candidate'+p.suffix))
        info['artifacts']={p.name:{'path':str(p),'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in folder.glob('candidate.*')}
        if heap<info['minimum_heap']:raise RuntimeError(f'BLOCKED: heap {heap} below preserved baseline369072; candidate was not loaded.')
        info['status']='BUILT'
    except Exception as exc:
        info.update(status='BLOCKED',error=str(exc));raise
    finally:
        for p,payload in original.items():p.write_bytes(payload)
        for p in artifacts:
            shutil.copy2(backup/p.name,p)
            if sha256_file(p)!=hashes[str(p)]:raise RuntimeError('Ordinary Debug restoration failed.')
        info['build_seconds']=round(time.monotonic()-started,3)
        info['source_defaults_restored']=info['ordinary_debug_restored']=True
        atomic_json(folder/'candidate.json',info)
    return info


def load_candidate(info, expected_device=None, board_serial=None):
    """Use the checked loader; the board must already be reset into DEV ROM."""
    folder = Path(info['folder'])
    if info['status'] != 'BUILT' or info['heap'] < 369072:
        raise RuntimeError('Candidate gate not passed.')
    if not board_serial:
        raise RuntimeError('BLOCKED: --board-serial is required for checked DEV RAM loading.')
    if (folder / 'load.json').exists():
        raise RuntimeError('BLOCKED: inspect previous loader outcome before retrying.')
    sys.path.insert(0, str(PROJECT_ROOT / 'Tools'))
    from load_checked_ram import execute, save_manifest
    result = {'status': 'LOADING', 'candidate': info}
    started = time.monotonic()
    try:
        manifest = save_manifest(PROJECT_ROOT, info, folder / 'load-inputs')
        result['manifest'] = str(manifest)
        loaded = execute(manifest, folder / 'checked-load', board_serial, expected_device)
        result.update(loaded)
    except Exception as exc:
        result.update(status='FAILED', error=str(exc))
        detail = folder / 'checked-load/result.json'
        if detail.exists():
            result['loader_result'] = json.loads(detail.read_text())
            result['status'] = result['loader_result']['status']
        raise
    finally:
        result['load_seconds'] = round(time.monotonic() - started, 3)
        # No replacement of ordinary Debug artifacts is needed by this loader.
        result['ordinary_debug_unchanged'] = True
        atomic_json(folder / 'load.json', result)
    return result
