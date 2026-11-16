"""Guarded DEV RAM startup. Default: offline preflight; --execute opens hardware.

Promoted from the 2026-11-16 demo controller. No reset/erase/program command is
sent. FSBL boot selection is allowed only behind a metadata-writer breakpoint.
See docs/ram-demo-loader_HE.md for the scope of this software guard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from read_xip_recovery import GdbMI

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDE = Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE')
WINDOWS = {'fsbl': (0x34180400, 0x34200000),
           'secure': (0x34000400, 0x34100000),
           'nonsecure': (0x24100400, 0x24200000)}
REQUIRED_SYMBOLS = {
    'fsbl': ('boot_metadata_commit', 'JumpToApplication', 'Error_Handler',
             'Firmware_Boot_Prepare'),
    'secure': ('main',),
    'nonsecure': ('main', 'NPU_SharedMemory_Clear', 'Debug_UART_Init',
                  'MX_ThreadX_Init'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_manifest(root, candidate, destination):
    """Freeze the build's exact inputs; does not inspect or open a device."""
    if (candidate['status'] != 'BUILT' or candidate['heap'] < 369072 or
            candidate['settings_writes'] is not False or
            candidate['ncp_preserve'] is not True):
        raise RuntimeError('Candidate safety gates did not pass')
    settings = (root / 'AppliNonSecure/Core/Inc/app_settings.h').read_text()
    for flag in ('APP_SETTINGS_WRITES_ENABLED', 'APP_SETTINGS_TRANSITION_ENABLED'):
        if not re.search(r'^#define\s+' + flag + r'\s+0U\s*$', settings, re.M):
            raise RuntimeError('RAM demo requires ' + flag + '=0U')
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': 1, 'settings_writes': False,
                'settings_transition': False, 'ncp_preserve': True,
                'ble_only': candidate['ble_only'], 'heap': candidate['heap'],
                'firmware_version': candidate['firmware_version'], 'artifacts': {}}
    for role, stem in (('fsbl', root / 'FSBL/Debug/N6_FSBL'),
                       ('secure', root / 'AppliSecure/Debug/N6_AppliSecure'),
                       ('nonsecure', Path(candidate['folder']) / 'candidate')):
        for suffix in ('elf', 'bin'):
            source = stem.with_suffix('.' + suffix)
            if role == 'nonsecure':
                expected = candidate['artifacts']['candidate.' + suffix]['sha256']
                if digest(source) != expected:
                    raise RuntimeError('Candidate changed: ' + str(source))
            name = role + '.' + suffix
            shutil.copy2(source, destination / name)
            manifest['artifacts'][name] = {'sha256': digest(destination / name)}
    path = destination / 'ram-load.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return path


def find_tools(ide):
    def one(pattern):
        matches = list((ide / 'plugins').glob(pattern))
        if len(matches) != 1:
            raise RuntimeError('Expected one tool matching ' + pattern)
        return matches[0]
    gdb = one('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gdb.exe')
    return {'gdb': gdb, 'nm': gdb.with_name('arm-none-eabi-nm.exe'),
            'objcopy': gdb.with_name('arm-none-eabi-objcopy.exe'),
            'server': one('com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_*/tools/bin/ST-LINK_gdbserver.exe'),
            'programmer': one('com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*/tools/bin/STM32_Programmer_CLI.exe').parent}


def preflight(path, tools):
    """Check hashes, ELF/BIN identity, load sections, vectors and guard symbols."""
    path = path.resolve()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if (manifest.get('schema_version') != 1 or
            manifest.get('settings_writes') is not False or
            manifest.get('settings_transition') is not False or
            manifest.get('ncp_preserve') is not True or
            manifest.get('heap', 0) < 369072):
        raise RuntimeError('Missing RAM safety contract in manifest')
    symbols = {}
    for role, (low, high) in WINDOWS.items():
        elf, binary = (path.parent / (role + suffix) for suffix in ('.elf', '.bin'))
        for artifact in (elf, binary):
            if digest(artifact) != manifest['artifacts'][artifact.name]['sha256']:
                raise RuntimeError('Artifact hash mismatch: ' + artifact.name)
        payload = binary.read_bytes()
        if len(payload) < 8 or low + len(payload) > high:
            raise RuntimeError('Image exceeds SRAM window: ' + role)
        sp, pc = struct.unpack_from('<II', payload)
        if not (low <= sp <= high and sp % 8 == 0 and low <= pc < high and pc & 1):
            raise RuntimeError('Invalid SRAM vectors: ' + role)
        # Validate every loadable ELF segment before GDB "load" can see it.
        data = elf.read_bytes()
        if data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
            raise RuntimeError('Expected little-endian ARM ELF32')
        phoff = struct.unpack_from('<I', data, 28)[0]
        phsize, count = struct.unpack_from('<HH', data, 42)
        if phsize < 32 or not count:
            raise RuntimeError('Missing ELF load segments')
        loaded = False
        for index in range(count):
            kind, _, _, address, size, _, _, _ = struct.unpack_from('<8I', data, phoff + index * phsize)
            if kind == 1 and size:
                loaded = True
                # GNU ELF segments include the 0x400-byte aligned header
                # prefix; loadable sections and the raw BIN start at low.
                if not low - 0x400 <= address < address + size <= high:
                    raise RuntimeError('ELF load segment outside SRAM: ' + role)
        if not loaded:
            raise RuntimeError('No ELF load bytes')
        with tempfile.TemporaryDirectory(prefix='n6-ram-preflight-') as tmp:
            extracted = Path(tmp) / 'image.bin'
            subprocess.run([str(tools['objcopy']), '-O', 'binary', str(elf), str(extracted)],
                           check=True, capture_output=True, timeout=30)
            if extracted.read_bytes() != payload:
                raise RuntimeError('ELF/BIN mismatch: ' + role)
        output = subprocess.check_output([str(tools['nm']), '--defined-only', str(elf)],
                                         text=True, timeout=30)
        syms = {m[2]: int(m[1], 16) for m in re.finditer(r'(?m)^([\da-fA-F]+)\s+\w\s+(\S+)$', output)}
        for name in REQUIRED_SYMBOLS[role]:
            if name not in syms or not low <= syms[name] < high:
                raise RuntimeError('Missing or out-of-range safety symbol: ' + name)
        symbols[role] = syms
    return manifest, symbols


def start_in_dev(mi, folder, output, symbols, result, port):
    """Run one guarded session. On failure, park; never resume a write path."""
    fsbl, secure, ns = (symbols[role] for role in ('fsbl', 'secure', 'nonsecure'))
    loaded = entered_ns = False
    try:
        mi.command('-gdb-set mi-async on')
        mi.console('set mem inaccessible-by-default off')
        mi.command('-file-exec-and-symbols ' + json.dumps((folder / 'fsbl.elf').as_posix()))
        mi.command('-target-select extended-remote localhost:' + str(port))
        pc = mi.value('$pc')
        result['initial_pc'] = hex(pc)
        if not 0x18000000 <= pc < 0x18040000:
            raise RuntimeError('Not in DEV ROM; no RAM download allowed')
        bootsr = mi.value('*(unsigned int*)0x56008100')
        result['bootsr'] = bootsr
        if bootsr & 3 != 2:
            raise RuntimeError('DEV boot not confirmed')
        # A partially failed download must also take the failure parking path.
        loaded = True
        mi.console('load', timeout=30)
        guard = mi.command('-break-insert -h *0x%x' % fsbl['boot_metadata_commit'])
        guard_id = re.search(r'number="(\d+)"', guard)[1]
        mi.console('thbreak *0x%x' % fsbl['JumpToApplication'])
        mi.console('set $sp = *(unsigned int*)0x34180400')
        mi.console('set $pc = *(unsigned int*)0x34180404')
        mi.command('-exec-continue')
        mi.until(lambda line: line.startswith('*stopped'), timeout=35)
        if mi.value('$pc') != fsbl['JumpToApplication']:
            raise RuntimeError('FSBL stopped before handoff; metadata write forbidden')
        if mi.value('boot_work_record.state') != 1:
            raise RuntimeError('Installed metadata not confirmed')
        result.update(metadata_state=1,
                      installed_version=mi.value('boot_work_record.confirmed_version'),
                      installed_slot=mi.value('boot_work_record.confirmed_slot'))
        mi.command('-break-delete ' + guard_id)

        def restore(role, address):
            payload = (folder / (role + '.bin')).read_bytes()
            # GDB restore/dump on Windows consumes an unquoted filename. Use
            # a relative simple name in a private working directory.
            mi.console('restore ' + role + '.bin binary 0x%x' % address, timeout=30)
            mi.console('dump binary memory ' + role + '.readback 0x%x 0x%x' %
                       (address, address + len(payload)), timeout=30)
            if (output / (role + '.readback')).read_bytes() != payload:
                raise RuntimeError('Full RAM readback mismatch: ' + role)
            result[role + '_readback'] = 'PASS'

        def reach(address, label):
            mi.console('thbreak *0x%x' % address)
            mi.command('-exec-continue')
            mi.until(lambda line: line.startswith('*stopped'), timeout=30)
            if mi.value('$pc') != address:
                raise RuntimeError('Unexpected stop before ' + label)
            result['phase'] = label

        # cd affects GDB's file commands only, not the Python process.
        mi.command('-environment-cd ' + json.dumps(output.as_posix()))
        restore('secure', 0x34000400)
        reach(secure['main'], 'secure-main')
        restore('nonsecure', 0x34100400)
        entered_ns = True
        for name in REQUIRED_SYMBOLS['nonsecure']:
            reach(ns[name], name)
        mi.command('-target-detach')
        result['status'] = 'RAM_STARTED'
    except Exception:
        result['status'] = 'FAILED'
        try:
            if loaded:
                if mi.running:
                    mi.command('-exec-interrupt --all', timeout=3)
                    mi.until(lambda line: line.startswith('*stopped'), timeout=3)
                # Never depend on possibly partially overwritten FSBL code.
                park = 0x241ff000 if entered_ns else 0x341ff000
                mi.console('set {unsigned short}0x%x = 0xe7fe' % park)
                if mi.value('*(unsigned short*)0x%x' % park) != 0xe7fe:
                    raise RuntimeError('Failure loop readback failed')
                mi.console('set $pc = 0x%x' % park)
                if mi.value('$pc') != park:
                    raise RuntimeError('Failure park readback failed')
                mi.command('-target-detach')
                result['failure_park_verified'] = hex(park)
            else:
                mi.command('-target-disconnect')
        except Exception as exc:
            result.update(status='UNCERTAIN', park_error=str(exc))
            # GdbMI.close disconnects without an implicit resume.
        raise


def execute(manifest_path, output, board_serial, expected_device=None,
            ide=DEFAULT_IDE, port=61444):
    if not 1 <= port <= 65533:
        raise ValueError('GDB port must be in 1..65533')
    tools = find_tools(ide)
    manifest, symbols = preflight(manifest_path, tools)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Private frozen input copies avoid loading ordinary Debug files or GDB
    # restore filenames containing spaces. Verify copies before any probe.
    for name in manifest['artifacts']:
        if name not in {role + ext for role in WINDOWS for ext in ('.elf', '.bin')}:
            raise RuntimeError('Unexpected manifest artifact name')
        shutil.copy2(manifest_path.parent / name, output / name)
    (output / 'ram-load.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest, symbols = preflight(output / 'ram-load.json', tools)
    sys.path.insert(0, str(ROOT / 'training/scripts'))
    from guarded_ram import hardware_lease, idle_board
    from serial.tools import list_ports
    result = {'status': 'STARTING', 'reset_sent': False,
              'metadata_write_guard': 'boot_metadata_commit',
              'manifest_sha256': digest(output / 'ram-load.json')}
    process = mi = None
    try:
        with hardware_lease('checked-ram-' + output.name):
            ports = [p for p in list_ports.comports()
                     if p.vid == 0x0483 and p.serial_number == board_serial]
            if len(ports) != 1:
                raise RuntimeError('Expected one matching ST-LINK identity')
            # Do not attach AP1 to a running application. The user resets into
            # DEV first; presence of the application CDC port refuses early.
            if any(p.serial_number == 'N6TOF001' for p in list_ports.comports()):
                raise RuntimeError('Application USB present; reset into DEV before loading')
            with (output / 'server.log').open('w') as serverlog, (output / 'gdb.log').open('w') as milog:
                try:
                    process = subprocess.Popen(
                        [str(tools['server']), '-p', str(port), '-d', '-m', '1', '-g',
                         '-i', board_serial, '-cp', str(tools['programmer'])],
                        stdout=serverlog, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    deadline = time.monotonic() + 15
                    while 'Waiting for debugger connection' not in (output / 'server.log').read_text(errors='replace'):
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError('Debugger unavailable before RAM load')
                        time.sleep(.1)
                    mi = GdbMI(tools['gdb'], milog)
                    start_in_dev(mi, output, output, symbols, result, port)
                finally:
                    try:
                        if mi is not None:
                            mi.close()
                    finally:
                        if process is not None:
                            if process.poll() is None:
                                process.terminate()
                            process.wait(timeout=5)
            time.sleep(25)
            result['target'] = idle_board(expected_device, board_serial)
            result['status'] = 'LOADED'
    except Exception as exc:
        if result['status'] != 'UNCERTAIN':
            result['status'] = 'FAILED'
        result['error'] = str(exc)
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--board-serial')
    parser.add_argument('--expected-device')
    parser.add_argument('--ide-root', type=Path, default=DEFAULT_IDE)
    parser.add_argument('--gdb-port', type=int, default=61444)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        if not args.output or not args.board_serial:
            parser.error('--execute requires --output (new directory) and --board-serial')
        execute(args.manifest.resolve(), args.output, args.board_serial,
                args.expected_device, args.ide_root, args.gdb_port)
        print('LOADED; inspect result.json and run Stage 11.')
    else:
        preflight(args.manifest, find_tools(args.ide_root))
        print('PREFLIGHT PASS; no hardware opened, reset or loaded.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
