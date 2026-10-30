"""Mock UART only: deadline, failure, disconnect and final cleanup behavior."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capture',ROOT/'Tools/capture_xip_boot_uart.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)


class Clock:
    def __init__(self):self.value=0
    def __call__(self):self.value+=.25;return self.value


class Port:
    def __init__(self,items=(),close_error=False):
        self.items=list(items);self.is_open=True;self.closed=0;self.close_error=close_error
    def read(self,n):
        item=self.items.pop(0) if self.items else b''
        if isinstance(item,BaseException):raise item
        return item
    def close(self):
        self.closed+=1
        if self.close_error:raise OSError('close failed')
        self.is_open=False


class Tests(unittest.TestCase):
    def run_capture(self,port,**kw):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);evidence={};messages=[]
            clock=Clock()
            try:
                capture.receive_bounded(port,folder,evidence,kw.pop('seconds',30),now=clock,
                    emit=lambda s,**k:messages.append(s),sleep=lambda s:None,**kw)
            except (OSError,RuntimeError):pass
            result=json.loads((folder/'result.json').read_text())
            return result,(folder/'uart.log').read_bytes(),messages
    def test_bounded_300_seconds_and_stdout_heartbeat(self):
        result,data,messages=self.run_capture(Port([b'abc']),seconds=300)
        self.assertEqual(result['status'],'BOUNDED_CAPTURE_COMPLETE');self.assertEqual(data,b'abc')
        self.assertTrue(result['owned_port_close_returned']);self.assertFalse(result['port_free_verified'])
        self.assertGreater(len(messages),40);self.assertLess(result['elapsed_seconds'],302)
    def test_read_exception_keeps_partial_evidence_and_closes(self):
        port=Port([b'kept',OSError('read failed')]);result,data,_=self.run_capture(port)
        self.assertEqual(data,b'kept');self.assertEqual(result['status'],'ABORTED');self.assertEqual(port.closed,1)
    def test_access_denial_is_never_retried(self):
        calls=[]
        result,_,_=self.run_capture(Port([PermissionError('denied')]),
            reconnect=lambda:calls.append(1),disconnected=lambda e:True)
        self.assertEqual(result['status'],'ABORTED');self.assertEqual(calls,[])
    def test_confirmed_disconnect_can_reconnect_within_deadline(self):
        old=Port([b'before',OSError('device gone')]);new=Port([b'after'])
        result,data,_=self.run_capture(old,reconnect=lambda:new,disconnected=lambda e:True)
        self.assertEqual(data,b'beforeafter');self.assertEqual(result['reconnections'],1)
        self.assertEqual(old.closed,1);self.assertEqual(new.closed,1)
    def test_absent_device_does_not_restart_deadline(self):
        result,data,_=self.run_capture(Port([OSError('gone')]),reconnect=lambda:None,disconnected=lambda e:True)
        self.assertLess(result['elapsed_seconds'],32);self.assertEqual(data,b'')
    def test_close_failure_is_not_clean_success(self):
        result,_,_=self.run_capture(Port(close_error=True))
        self.assertEqual(result['status'],'ABORTED');self.assertFalse(result['owned_port_close_returned'])
    def test_stop_request_closes_without_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'stop.request').write_text('stop');port=Port();evidence={}
            capture.receive_bounded(port,folder,evidence,30,now=Clock())
            self.assertEqual(evidence['status'],'STOP_REQUESTED');self.assertEqual(port.closed,1)
    def test_signal_flag_stops_without_reset_or_io(self):
        result,data,_=self.run_capture(Port(),stopping=lambda:True)
        self.assertEqual(result['status'],'STOP_REQUESTED');self.assertEqual(data,b'')
    def test_overlong_capture_rejected_before_file_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):capture.receive_bounded(Port(),Path(temporary),{},1200)
            self.assertEqual(list(Path(temporary).iterdir()),[])
    def main_failure(self,close_error=False,branch='main'):
        import types
        import serial
        from serial.tools import list_ports
        with tempfile.TemporaryDirectory(prefix='capture-host-',dir=ROOT/'.local-dependencies') as temporary:
            folder=Path(temporary);diag=folder/'.local-dependencies/diagnostics';diag.mkdir(parents=True)
            port=Port([OSError('fixture read failure')],close_error=close_error);port.open=lambda:None
            def command(args,**kw):return branch+'\n' if 'branch' in args else str(folder/'.git')+'\n'
            argv=['capture','--owner-thread','fixture','--output',str(folder/'capture'),'--seconds','30']
            with patch('sys.argv',argv),patch('subprocess.check_output',command),patch.object(serial,'Serial',lambda **kw:port),patch.object(list_ports,'comports',lambda:[types.SimpleNamespace(device='COM6',serial_number='000C00344142501620353451')]):
                with self.assertRaisesRegex(OSError,'fixture read failure'):capture.cli_main()
            result=json.loads((folder/'capture/result.json').read_text())
            self.assertEqual(result['status'],'ABORTED');self.assertEqual(result['lease_released'],not close_error)
            self.assertEqual((diag/'n6-hardware-owner.json').exists(),close_error)
            self.assertEqual((diag/'n6-hardware-owner.lock').exists(),close_error)
    def test_main_read_failure_releases_own_lease_without_hardware(self):self.main_failure()
    def test_main_close_failure_preserves_owner_for_explicit_recovery(self):self.main_failure(True)
    def test_legacy_branch_remains_compatible(self):self.main_failure(branch='feature/n6-xip-ota-usb')
    def test_unapproved_or_detached_branch_rejected_before_device_access(self):
        import serial
        from serial.tools import list_ports
        for branch in ('topic/unapproved',''):
            with self.subTest(branch=branch),patch('sys.argv',['capture']),patch('subprocess.check_output',return_value=branch+'\n'),patch.object(serial,'Serial') as open_port,patch.object(list_ports,'comports') as ports:
                with self.assertRaisesRegex(RuntimeError,'Wrong branch'):capture.cli_main()
                open_port.assert_not_called();ports.assert_not_called()
    def test_active_dtr_rejected_before_any_device_access(self):
        import contextlib,io
        with patch('sys.argv',['capture','--dtr','1']),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:capture.cli_main()
        self.assertEqual(error.exception.code,2)


if __name__=='__main__':unittest.main()
