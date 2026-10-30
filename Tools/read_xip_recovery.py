"""Read NOR through a RAM FSBL, stopping before boot selection or application entry.

Default is host-only preflight. --execute requires a separately held shared lease
and DEV ROM. Uses interactive GDB/MI so a command error cannot silently exit a
batch file and resume the installed legacy application. Never sends reset, erase,
OTP, debug-unlock or application-continue commands.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time


def scalar_value(text):
    # GDB decorates PC values with symbols, e.g. 0x34181234 <Error_Handler>.
    match = re.match(r'^[+-]?(?:0x[0-9a-fA-F]+|[0-9]+)(?=$|\s|<)', text)
    if not match:
        raise ValueError('Non-scalar GDB value: ' + text)
    return int(match[0], 0)


class GdbMI:
    def __init__(self, executable, log):
        self.process = subprocess.Popen(
            [str(executable), '-nx', '-q', '--interpreter=mi2'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.lines = queue.Queue()
        self.log = log
        self.token = 0
        self.running = False
        def read():
            for line in self.process.stdout:
                if line.startswith('*running'):
                    self.running = True
                elif line.startswith('*stopped'):
                    self.running = False
                self.log.write(line)
                self.log.flush()
                self.lines.put(line.rstrip())
            self.lines.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def until(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('GDB response timeout; target outcome uncertain')
            line = self.lines.get(timeout=remaining)
            if line is None:
                raise RuntimeError('GDB exited unexpectedly')
            if predicate(line):
                return line

    def command(self, command, timeout=15):
        self.token += 1
        token = str(self.token)
        self.log.write('>> ' + token + command + '\n')
        self.log.flush()
        self.process.stdin.write(token + command + '\n')
        self.process.stdin.flush()
        result = self.until(lambda line: line.startswith(token + '^'), timeout)
        if result.startswith(token + '^error'):
            raise RuntimeError(result)
        return result

    def console(self, command, timeout=15):
        return self.command('-interpreter-exec console ' + json.dumps(command), timeout)

    def value(self, expression):
        result = self.command('-data-evaluate-expression ' + json.dumps(expression))
        match = re.search(r'value=("(?:[^"\\]|\\.)*")', result)
        if not match:
            raise RuntimeError('No scalar GDB result: ' + result)
        return scalar_value(json.loads(match[1]))

    def close(self):
        if self.process.poll() is None:
            # In particular after failed parking, do not let GDB's normal
            # exit detach/resume a target implicitly. Disconnect requests no
            # resume; a dead debug link still makes actual board state unknown.
            try:
                self.command('-target-disconnect', timeout=3)
            except Exception:
                pass
            try:
                self.command('-gdb-exit', timeout=3)
            except Exception:
                self.process.terminate()
        self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


def read_at_prepare(mi, fsbl, output, symbols):
    """Requires halted DEV ROM; finally parks loaded FSBL even on command error."""
    loaded = False
    evidence = {'nor_written': False, 'application_entered': False}
    try:
        mi.command('-gdb-set mi-async on')
        mi.console('set mem inaccessible-by-default off')
        mi.console('file ' + fsbl.as_posix())
        mi.command('-target-select extended-remote localhost:61444')
        pc = mi.value('$pc')
        evidence['initial_pc'] = hex(pc)
        if not 0x18000000 <= pc < 0x18040000:
            # In NS runtime even a diagnostic Secure-alias read can fail the
            # debug transport. Reject from the PC alone before reading BOOTSR.
            raise RuntimeError('Requires verified DEV Boot ROM; refusing RAM load')
        bootsr = mi.value('*(unsigned int*)0x56008100')
        evidence['bootsr'] = bootsr
        if bootsr & 3 != 2:
            raise RuntimeError('Requires verified DEV Boot ROM; refusing RAM load')
        mi.console('load', timeout=30)
        loaded = True
        mi.console('thbreak *0x%x' % symbols['Firmware_Boot_Prepare'])
        mi.console('set $sp = *(unsigned int*)0x34180400')
        mi.console('set $pc = *(unsigned int*)0x34180404')
        mi.command('-exec-continue')
        mi.until(lambda line: line.startswith('*stopped'), timeout=30)
        if mi.value('$pc') != symbols['Firmware_Boot_Prepare']:
            raise RuntimeError('Unexpected FSBL stop; boot selection not allowed')
        # Park BEFORE any inferior calls/dumps. A failed read then returns to a
        # Secure loop, not to boot selection / JumpToApplication.
        mi.console('set $pc = 0x%x' % symbols['Error_Handler'])
        if mi.value('(int)MapMemory()') != 0:
            raise RuntimeError('MapMemory failed')
        for name in ('nor-first.bin', 'nor-second.bin'):
            mi.console('dump binary memory ' + (output / name).as_posix() +
                       ' 0x70000000 0x70400000', timeout=30)
        if mi.value('(int)EXTMEM_MemoryMappedMode(0,EXTMEM_DISABLE)') != 0:
            raise RuntimeError('Unmap failed; FSBL remains parked')
        first = (output / 'nor-first.bin').read_bytes()
        second = (output / 'nor-second.bin').read_bytes()
        if len(first) != 4194304 or first != second:
            raise RuntimeError('NOR double-read mismatch')
        evidence.update(bytes=len(first), double_read_identical=True,
                        sha256=hashlib.sha256(first).hexdigest())
        return evidence
    finally:
        if loaded:
            # Interactive MI remains alive after a missing symbol or failed
            # memory read. Never detach unless parking was read back.
            if getattr(mi, 'running', False):
                try:
                    mi.command('-exec-interrupt --all', timeout=3)
                    mi.until(lambda line: line.startswith('*stopped'), timeout=3)
                except Exception:
                    pass
            mi.console('set $pc = 0x%x' % symbols['Error_Handler'])
            if mi.value('$pc') != symbols['Error_Handler']:
                raise RuntimeError('Cannot verify Secure parking; no detach sent')
            evidence['park_verified'] = True
        mi.command('-target-detach' if loaded else '-target-disconnect')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fsbl', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--owner-thread')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    git = ['git', '-c', 'safe.directory=' + str(root), '-C', str(root)]
    if subprocess.check_output(git + ['branch', '--show-current'], text=True).strip() not in ('main', 'feature/n6-xip-ota-usb'):
        raise RuntimeError('Wrong branch; no hardware access')
    fsbl = args.fsbl.resolve()
    if hashlib.sha256(fsbl.read_bytes()).hexdigest().lower() != args.sha256.lower():
        raise RuntimeError('FSBL hash mismatch; no hardware access')
    if ' ' in str(fsbl) or ' ' in str(args.output.resolve()):
        raise RuntimeError('GDB restore/dump paths must not contain spaces')
    plugins = Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
    gdb = next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gdb.exe'))
    raw = subprocess.check_output([str(gdb.with_name('arm-none-eabi-nm.exe')),
                                   '--defined-only', str(fsbl)], text=True)
    symbols = {}
    for name in ('Firmware_Boot_Prepare', 'Error_Handler', 'MapMemory', 'EXTMEM_MemoryMappedMode'):
        match = re.search(r'(?m)^([0-9a-fA-F]+)\s+[TtWw]\s+' + name + '$', raw)
        if not match:
            raise RuntimeError('Missing FSBL symbol: ' + name)
        symbols[name] = int(match[1], 16)
    print('HOST PREFLIGHT PASS: branch/hash/four FSBL symbols; no hardware opened', flush=True)
    if not args.execute:
        return
    common = Path(subprocess.check_output(git + ['rev-parse', '--path-format=absolute', '--git-common-dir'], text=True).strip())
    status = common.parent / '.local-dependencies/diagnostics/n6-hardware-owner.json'
    owner = json.loads(status.read_text())
    if not args.owner_thread or owner['thread'] != args.owner_thread or 'XIP' not in owner['scope']:
        raise RuntimeError('Required shared XIP lease not held by specified owner')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    server = next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_*/tools/bin/ST-LINK_gdbserver.exe'))
    cp = next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*/tools/bin/STM32_Programmer_CLI.exe')).parent
    with (output / 'server.log').open('w') as log:
        process = subprocess.Popen([str(server), '-p', '61444', '-d', '-m', '1', '-g', '-i',
                                    '000C00344142501620353451', '-cp', str(cp)],
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
        mi = None
        try:
            deadline = time.monotonic() + 15
            while 'Waiting for debugger connection' not in (output / 'server.log').read_text(errors='replace'):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('AP1 server unavailable; no RAM load executed')
                time.sleep(.1)
            with (output / 'gdb-mi.log').open('w') as milog:
                mi = GdbMI(gdb, milog)
                try:
                    evidence = read_at_prepare(mi, fsbl, output, symbols)
                    (output / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n')
                    print(json.dumps(evidence))
                finally:
                    mi.close()
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
