"""Isolated import worker: deny external effects before adding helper paths."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--preflight-entry', action='store_true')
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    # -I means none of the repository/helper directories can shadow these
    # trusted dependencies while the denial layer is being installed.
    import inspect
    import sysconfig
    assert Path(inspect.__file__).resolve() == (Path(sysconfig.get_path('stdlib')) / 'inspect.py').resolve()
    import subprocess
    import socket
    import threading
    import asyncio
    import ctypes
    import numpy
    import PIL.Image
    import serial
    import serial.tools.list_ports
    import bleak
    import tkinter
    if args.preflight_entry:
        # Trusted dependency preload under -I, before any helper directory is
        # searchable. The entrypoint itself still runs with all effects denied.
        import tensorflow
    effects = []

    class ImportEffectBlocked(BaseException):
        pass

    def denied(kind):
        def stop(*unused, **kwargs):
            effects.append(kind)
            raise ImportEffectBlocked(kind)
        return stop

    for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
        setattr(subprocess, name, denied('subprocess.' + name))
    os.system = denied('os.system')
    if hasattr(os, 'startfile'):
        os.startfile = denied('os.startfile')
    socket.create_connection = denied('socket.create_connection')
    socket.socket.connect = denied('socket.connect')
    socket.socket.connect_ex = denied('socket.connect_ex')
    serial.Serial.__init__ = denied('serial.Serial')
    serial.serial_for_url = denied('serial.serial_for_url')
    serial.SerialBase.open = denied('serial.open')
    if hasattr(serial, 'serialwin32'):
        serial.serialwin32.Serial.open = denied('serial.win32.open')
    serial.tools.list_ports.comports = denied('serial.enumerate')
    bleak.BleakClient.__init__ = denied('BLE client creation')
    bleak.BleakScanner.__init__ = denied('BLE scanner creation')
    for name in ('discover', 'find_device_by_address', 'find_device_by_filter', 'find_device_by_name'):
        if hasattr(bleak.BleakScanner, name):
            setattr(bleak.BleakScanner, name, staticmethod(denied('BLE.' + name)))
    asyncio.run = denied('asyncio.run')
    threading.Thread.start = denied('thread.start')
    tkinter.Tk = denied('Tk window')
    tkinter.Toplevel = denied('Tk window')
    ctypes.CDLL = denied('ctypes.CDLL')
    if hasattr(ctypes, 'WinDLL'):
        ctypes.WinDLL = denied('ctypes.WinDLL')

    def audit(event, values):
        if event in ('subprocess.Popen', 'os.system', 'socket.connect',
                     'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir',
                     'ctypes.dlopen'):
            denied(event)()
        if event == 'open':
            path, mode, flags = values
            device = str(path).upper()
            if device.startswith('\\\\.\\') or device.startswith('COM'):
                denied('device file open')()
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                    flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                denied('filesystem write')()

    sys.addaudithook(audit)
    root = args.root.resolve()
    target = args.target.resolve()
    sys.path[:0] = [str(target.parent), str(root / 'Tools'),
                    str(root / 'hil_tests'), str(root / 'training/scripts')]
    sys.argv = [str(target)] + (['--preflight-only'] if args.preflight_entry else [])
    result = {'path': str(target), 'effects': effects, 'passed': False}
    try:
        spec = importlib.util.spec_from_file_location('_n6_import_audit_target', target)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        if args.preflight_entry:
            try:
                module.cli_main()
            except SystemExit as status:
                if status.code not in (None, 0):
                    raise
        result['passed'] = not effects
    except BaseException as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    result['inspect_origin'] = str(Path(inspect.__file__).resolve())
    print('N6_IMPORT_AUDIT_RESULT=' + json.dumps(result), flush=True)
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
