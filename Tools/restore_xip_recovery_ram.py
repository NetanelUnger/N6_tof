"""Explicit recovery from verified Secure FSBL park; default host-only preflight.

Loads matching guarded v27 RAM/Secure images, never A23. A four-byte RAM-only
N6_SystemReset return1 patch prevents the USB installer resetting into DEV or
the faulty confirmed image. NOR is not written by this loader. No reset command.
"""

def restore_parked(mi, output, fsbl, build, symbols):
    import struct
    park=symbols['park'];ns=False;handed=False;validated=False
    try:
        mi.command('-gdb-set mi-async on')
        mi.console('set mem inaccessible-by-default off')
        mi.console('file '+fsbl.as_posix())
        mi.command('-target-select extended-remote localhost:61444')
        pc=mi.value('$pc')
        if not park<=pc<park+32:raise RuntimeError('Not the verified Secure FSBL park; no RAM load')
        if mi.value('*(unsigned int*)0x56008100')&3!=2:raise RuntimeError('Not DEV; no RAM load')
        validated=True
        for name,address in [('AppliSecure.bin',0x34000400),('ram.bin',0x34100400)]:
            payload=(build/name).read_bytes()
            mi.console('restore '+(build/name).as_posix()+' binary 0x%x'%address)
            dest=output/(name+'.readback')
            mi.console('dump binary memory '+dest.as_posix()+' 0x%x 0x%x'%(address,address+len(payload)),timeout=30)
            if dest.read_bytes()!=payload:raise RuntimeError('RAM readback mismatch: '+name)
        reset=symbols['reset']+0x10000000
        mi.console('set {unsigned int}0x%x = 0x47702001'%reset)
        if mi.value('*(unsigned int*)0x%x'%reset)!=0x47702001:raise RuntimeError('Reset refusal RAM patch mismatch')
        mi.console('thbreak *0x%x'%symbols['secure_main'])
        mi.console('set $primask = 0')
        # This existing vendor handoff suspends tick and cleans/disables caches
        # before setting Secure VTOR/MSP. Boot selection is never executed.
        mi.console('set $pc = 0x%x'%symbols['jump'])
        mi.command('-exec-continue');mi.until(lambda s:s.startswith('*stopped'),timeout=30)
        if mi.value('$pc')!=symbols['secure_main']:raise RuntimeError('Secure main not reached')
        msp,entry=struct.unpack_from('<II',(build/'ram.bin').read_bytes())
        if mi.value('*(unsigned int*)0x34100400')!=msp or mi.value('*(unsigned int*)0x34100404')!=entry:
            raise RuntimeError('Guarded RAM vectors changed')
        mi.console('thbreak *0x%x'%symbols['main']);ns=True
        mi.command('-exec-continue');mi.until(lambda s:s.startswith('*stopped'),timeout=30)
        if mi.value('$pc')!=symbols['main']:raise RuntimeError('Guarded RAM NS main not reached')
        mi.console('thbreak *0x%x'%symbols['threadx'])
        mi.command('-exec-continue');mi.until(lambda s:s.startswith('*stopped'),timeout=30)
        if mi.value('$pc')!=symbols['threadx']:raise RuntimeError('ThreadX startup not reached')
        result={'RAM_main':hex(symbols['main']),'ThreadX':hex(symbols['threadx']),
                'reset_refusal_RAM_patch':hex(symbols['reset']),'nor_written':False,
                'A23_entered':False,'guarded_RAM_version':27,'resource_profile':False}
        mi.command('-target-detach');handed=True
        return result
    finally:
        if not handed and not validated:
            mi.command('-target-disconnect')
        if not handed and validated:
            if mi.running:
                mi.command('-exec-interrupt --all',timeout=3)
                mi.until(lambda s:s.startswith('*stopped'),timeout=3)
            if ns:
                # Keep the existing NS session; no Secure alias access here.
                mi.console('set {unsigned short}0x241ff000 = 0xe7fe')
                mi.console('set $pc = 0x241ff000');expected=0x241ff000
            else:
                mi.console('set $pc = 0x%x'%park);expected=park
            if mi.value('$pc')!=expected:raise RuntimeError('Failure park unverified; state uncertain')
            mi.command('-target-detach')


def main():
    import argparse,hashlib,importlib.util,json,re,struct,subprocess,threading,time,zlib
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--owner-thread');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    git=['git','-c','safe.directory='+str(root),'-C',str(root)]
    if subprocess.check_output(git+['branch','--show-current'],text=True).strip() not in ('main', 'feature/n6-xip-ota-usb'):raise RuntimeError('Wrong branch')
    build=root/'.local-dependencies/xip/v27-B-resource-margin';info=json.loads((build/'build.json').read_text())
    for name in ['ram.bin','ram.elf','AppliSecure.bin','AppliSecure.elf','FSBL.elf']:
        if hashlib.sha256((build/name).read_bytes()).hexdigest()!=info['hashes'][name]['sha256'].lower():raise RuntimeError('Artifact hash mismatch: '+name)
    backup=root/'.local-dependencies/xip/recovery-read-20261023-1157'
    b=(backup/'nor-first.bin').read_bytes();read=json.loads((backup/'result.json').read_text())
    if not read['double_read_identical'] or hashlib.sha256(b).hexdigest()!=read['sha256']:raise RuntimeError('Backup mismatch')
    if b!=(backup/'nor-second.bin').read_bytes():raise RuntimeError('Second backup mismatch')
    record=b[0x3e0000:0x3e0400]
    if struct.unpack_from('<8I',record)!=(0x5242364e,1,66,1,0,23,1,22) or zlib.crc32(record[:1020])!=struct.unpack_from('<I',record,1020)[0]:raise RuntimeError('Unexpected metadata; no RAM load')
    if hashlib.sha256(b[0x180000:0x180000+499840]).hexdigest()!='1922aeae6e2aefe1da6e119c31f3e52bc4ff632c8a9c368db45fd491afa8bca0':raise RuntimeError('A23 backup mismatch')
    plugins=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
    gdb=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gdb.exe'))
    def sym(elf,name):
        raw=subprocess.check_output([str(gdb.with_name('arm-none-eabi-nm.exe')),'--defined-only',str(elf)],text=True)
        m=re.search(r'(?m)^([0-9a-fA-F]+)\s+[TtWw]\s+'+name+'$',raw)
        if not m:raise RuntimeError('Missing symbol: '+name)
        return int(m[1],16)
    symbols={key:sym(build/elf,name) for key,elf,name in [
        ('park','FSBL.elf','Error_Handler'),('jump','FSBL.elf','JumpToApplication'),
        ('secure_main','AppliSecure.elf','main'),('main','ram.elf','main'),
        ('reset','ram.elf','N6_SystemReset'),('threadx','ram.elf','MX_ThreadX_Init')]}
    if not 0x24100400<=symbols['reset']<0x24180000:raise RuntimeError('Reset symbol outside RAM')
    print('HOST PREFLIGHT PASS exact artifacts, seq66/A23, double backup and symbols; no hardware opened',flush=True)
    if not a.execute:return
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    owner=json.loads((common.parent/'.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if not a.owner_thread or owner['thread']!=a.owner_thread:raise RuntimeError('Wrong owner')
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    lease=module('recovery_lease',root/'hil_tests/n6_hardware_lease.py')
    identity=lease.windows_process_identity(owner['pid'])
    if identity.get('state')!='alive' or identity.get('created_utc')!=owner['process_created_utc']:raise RuntimeError('Owner identity mismatch')
    out=a.output.resolve()
    if not out.is_relative_to(root) or ' ' in str(out):raise RuntimeError('Invalid output')
    out.mkdir(parents=True,exist_ok=False)
    reader=module('recovery_mi',root/'Tools/read_xip_recovery.py')
    import serial
    from serial.tools import list_ports
    if not any(x.device=='COM6' and x.serial_number=='000C00344142501620353451' for x in list_ports.comports()):raise RuntimeError('Exact UART absent')
    uart=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1)
    uart.dtr=False;uart.rts=False;uart.port='COM6';uart.open()
    stop=threading.Event();errors=[];result={};mi=None;process=None
    try:
        with (out/'uart.log').open('xb') as trace:
            def collect():
                try:
                    while not stop.is_set():
                        data=uart.read(8192)
                        if data:trace.write(data);trace.flush()
                except BaseException as error:errors.append(repr(error))
            thread=threading.Thread(target=collect);thread.start()
            try:
                server=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_*/tools/bin/ST-LINK_gdbserver.exe'))
                cp=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*/tools/bin/STM32_Programmer_CLI.exe')).parent
                with (out/'server.log').open('w') as log:
                    process=subprocess.Popen([str(server),'-p','61444','-d','-m','1','-g','-i','000C00344142501620353451','-cp',str(cp)],stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
                    deadline=time.monotonic()+15
                    while 'Waiting for debugger connection' not in (out/'server.log').read_text(errors='replace'):
                        if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('AP1 unavailable; no RAM load')
                        time.sleep(.1)
                    with (out/'gdb-mi.log').open('w') as milog:
                        mi=reader.GdbMI(gdb,milog)
                        result=restore_parked(mi,out,build/'FSBL.elf',build,symbols)
                        mi.close();mi=None
                    process.terminate();process.wait(timeout=5);process=None
                # No debugger during NS runtime. Bounded UART startup only.
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:time.sleep(.2)
            finally:
                if mi is not None:mi.close()
                if process is not None:
                    if process.poll() is None:process.terminate()
                    process.wait(timeout=5)
                stop.set();thread.join(timeout=2)
    finally:
        uart.close();result.update(uart_errors=errors,owned_uart_closed=True)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
