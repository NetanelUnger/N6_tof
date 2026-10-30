"""Bounded boot-chain write through the already parked, verified RAM FSBL.

Default is a host-only artifact preflight. No reset or application entry. The
unmodified read controller must have just parked FSBL after a double NOR read.
Only two owned 128KiB boot-chain ranges may be changed; retained sector tails,
both application slots and metadata must compare exactly before returning.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time


def digest(data):
    return hashlib.sha256(data).hexdigest().lower()


def desired_nor(before, fsbl, secure):
    if len(before) != 4194304 or not 1024 < len(fsbl) <= 131072 or not 1024 < len(secure) <= 131072:
        raise ValueError('Boot-chain bounds rejected')
    result = bytearray(before)
    result[:len(fsbl)] = fsbl
    result[0x100000:0x100000 + len(secure)] = secure
    return bytes(result)


def program_parked(mi, output, fsbl, park, before, desired, text_address, text):
    # Never read Secure aliases if the CPU is unexpectedly executing NS code.
    if mi.value('$pc') not in (park, park+0x1a, park+0x1c):
        raise RuntimeError('Requires exact verified Secure FSBL park; no write')
    if mi.value('*(unsigned int*)0x56008100') & 3 != 2:
        raise RuntimeError('Requires DEV boot; no write')
    try:
        mi.console('dump binary memory ' + (output/'ram-text.bin').as_posix() +
                   ' 0x%x 0x%x' % (text_address, text_address+len(text)), timeout=30)
        if (output/'ram-text.bin').read_bytes() != text:
            raise RuntimeError('Parked RAM FSBL text mismatch; no write')
        # Error_Handler disabled IRQs. Inferior flash calls need the original
        # Secure SysTick for bounded HAL timeouts; no NS app has been entered.
        mi.console('set $primask = 0')
        if mi.value('(int)MapMemory()') != 0:
            raise RuntimeError('Map failed; no write')
        mi.console('dump binary memory '+(output/'before.bin').as_posix()+' 0x70000000 0x70400000', timeout=30)
        if (output/'before.bin').read_bytes() != before:
            raise RuntimeError('NOR changed since independent double backup; no write')
        if mi.value('(int)EXTMEM_MemoryMappedMode(0,EXTMEM_DISABLE)') != 0:
            raise RuntimeError('Unmap failed; no write')
        # Secure first: it supports the original RAM boot chain and B11 ABI.
        # All code, vectors, UART and flash-driver buffers are in SRAM here.
        for start in (0x100000, 0):
            for offset in range(start, start+131072, 65536):
                block=output/('sector-%06x.bin' % offset)
                block.write_bytes(desired[offset:offset+65536])
                mi.console('restore '+block.as_posix()+' binary 0x34010000')
                (output/'operation.json').write_text(json.dumps({'phase':'erase_requested','offset':hex(offset),'outcome':'uncertain until readback'})+'\n')
                if mi.value('(int)EXTMEM_EraseSector(0,%d,65536)' % offset) != 0:
                    raise RuntimeError('Erase failed at %x; inspect before any retry' % offset)
                if mi.value('(int)EXTMEM_Write(0,%d,(const unsigned char*)0x34010000,65536)' % offset) != 0:
                    raise RuntimeError('Write failed at %x; inspect before any retry' % offset)
                print('PROGRAMMED owned sector',hex(offset),flush=True)
        if mi.value('(int)MapMemory()') != 0:
            raise RuntimeError('Readback map failed')
        for name in ('after-first.bin','after-second.bin'):
            mi.console('dump binary memory '+(output/name).as_posix()+' 0x70000000 0x70400000', timeout=30)
            if (output/name).read_bytes() != desired:
                raise RuntimeError('Full NOR readback mismatch; inspect before any retry')
        if mi.value('(int)EXTMEM_MemoryMappedMode(0,EXTMEM_DISABLE)') != 0:
            raise RuntimeError('Readback unmap failed')
        result={'verified':True,'sha256':digest(desired),'application_slots_and_metadata_unchanged':True,
                'bootchain_ranges':['0x70000000..0x7001ffff','0x70100000..0x7011ffff'],
                'sector_tails_preserved':True,'otp_or_credentials_changed':False,'application_entered':False}
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)
    finally:
        if mi.running:
            mi.command('-exec-interrupt --all',timeout=3)
            mi.until(lambda x:x.startswith('*stopped'),timeout=3)
        mi.console('set $pc = 0x%x' % park)
        mi.console('set $primask = 1')
        if mi.value('$pc') != park:
            raise RuntimeError('Secure park unverifiable; no detach')
        mi.command('-target-detach')


def cli_main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--owner-thread')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    build=root/'.local-dependencies/xip/v13-B-abi-compat4'
    backup=root/'.local-dependencies/xip/inspection-after-loader-erase-fail'
    info=json.loads((build/'build.json').read_text())
    for name in ('FSBL.elf','FSBL-trusted.bin','AppliSecure-trusted.bin'):
        if digest((build/name).read_bytes()) != info['hashes'][name]['sha256'].lower():
            raise RuntimeError('Artifact hash changed: '+name)
    before=(backup/'nor-first.bin').read_bytes()
    if before != (backup/'nor-second.bin').read_bytes() or digest(before) != '0927f173a07437909a3585f7a9ba4ffa3b0819cf1aaf226ea541739c83d2543f':
        raise RuntimeError('Independent complete backup changed')
    desired=desired_nor(before,(build/'FSBL-trusted.bin').read_bytes(),(build/'AppliSecure-trusted.bin').read_bytes())
    print('HOST PREFLIGHT PASS fixed owned ranges, signed artifact hashes and exact double backup',flush=True)
    if not args.execute or args.preflight_only:
        return
    git=['git','-c','safe.directory='+str(root),'-C',str(root)]
    if subprocess.check_output(git+['branch','--show-current'],text=True).strip() not in ('main', 'feature/n6-xip-ota-usb'):
        raise RuntimeError('Wrong branch')
    common=Path(subprocess.check_output(git+['rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip())
    owner=json.loads((common.parent/'.local-dependencies/diagnostics/n6-hardware-owner.json').read_text())
    if not args.owner_thread or owner['thread'] != args.owner_thread or 'XIP' not in owner['scope']:
        raise RuntimeError('Missing shared XIP owner')
    if not args.output or ' ' in str(args.output.resolve()):
        raise RuntimeError('Explicit fresh output required, without GDB path spaces')
    output=args.output.resolve()
    if not output.is_relative_to(root):
        raise RuntimeError('Output outside worktree')
    output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('xip_reader',root/'Tools/read_xip_recovery.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    plugins=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
    gdb=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gdb.exe'))
    nm=subprocess.check_output([str(gdb.with_name('arm-none-eabi-nm.exe')),'--defined-only',str(build/'FSBL.elf')],text=True)
    park=int(re.search(r'(?m)^([0-9a-fA-F]+)\s+[Tt]\s+Error_Handler$',nm)[1],16)
    headers=subprocess.check_output([str(gdb.with_name('arm-none-eabi-objdump.exe')),'-h',str(build/'FSBL.elf')],text=True)
    section=re.search(r'(?m)^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',headers)
    address=int(section[2],16)
    subprocess.run([str(gdb.with_name('arm-none-eabi-objcopy.exe')),'-O','binary','--only-section=.text',str(build/'FSBL.elf'),str(output/'expected-text.bin')],check=True)
    text=(output/'expected-text.bin').read_bytes()
    assert len(text)==int(section[1],16)
    server=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_*/tools/bin/ST-LINK_gdbserver.exe'))
    cp=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*/tools/bin/STM32_Programmer_CLI.exe')).parent
    with (output/'server.log').open('w') as slog:
        process=subprocess.Popen([str(server),'-p','61444','-d','-m','1','-g','-i','000C00344142501620353451','-cp',str(cp)],stdout=slog,stderr=subprocess.STDOUT,creationflags=0x08000000)
        try:
            deadline=time.monotonic()+15
            while 'Waiting for debugger connection' not in (output/'server.log').read_text(errors='replace'):
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('AP1 unavailable; no write')
                time.sleep(.1)
            with (output/'gdb-mi.log').open('w') as log:
                mi=reader.GdbMI(gdb,log)
                try:
                    mi.console('set mem inaccessible-by-default off')
                    mi.console('file '+(build/'FSBL.elf').as_posix())
                    mi.command('-target-select extended-remote localhost:61444')
                    program_parked(mi,output,build/'FSBL.elf',park,before,desired,address,text)
                finally:mi.close()
        finally:
            if process.poll() is None:process.terminate()
            process.wait(timeout=5)


if __name__=='__main__':
    cli_main()
