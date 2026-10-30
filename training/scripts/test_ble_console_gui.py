"""Exercise actual Tk widgets/async dispatch with a simulated GATT peer."""
import asyncio
import json
from pathlib import Path
import queue
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace as NS

import ble_console as gui
from ble_console_core import BleSession, save_report
from test_ble_console import Client, Lease, Scanner


class GuiScanner(Scanner):
    @staticmethod
    async def discover(timeout, return_adv):
        return {'test': (NS(address='test',name='N6-MAINT-TEST'),NS(local_name='N6-MAINT-TEST',service_uuids=[]))}


def main():
    with tempfile.TemporaryDirectory() as folder:
        root=tk.Tk()
        window=gui.ConsoleWindow(root)
        window.session=BleSession(lambda kind,data:window.events.put((kind,data)),
                                  scanner=GuiScanner,client_factory=Client,lease=Lease())
        gui.save_report=lambda report:save_report(report,folder)
        def until(predicate,timeout=10):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                root.update()
                if predicate(): return
                time.sleep(.02)
            raise AssertionError('UI operation did not complete: '+window.status.get())
        try:
            root.update()
            assert root.winfo_width()>=850 and root.winfo_height()>=620
            window.buttons[0].invoke();until(lambda:not window.busy)
            assert window.device_box.current()==0
            window.buttons[1].invoke();until(lambda:not window.busy)
            assert window.session.connected
            window.count.set(3);window.buttons[3].invoke();until(lambda:not window.busy)
            assert window.summary.get().startswith('PASS')
            assert len(window.table.get_children())==9
            report=Path(window.report_path.get())
            assert json.loads(report.read_text())['passed']
            window.command_box.set('version');window.buttons[7].invoke();until(lambda:not window.busy)
            assert 'Firmware version: 57' in window.output.get('1.0','end')
            window.buttons[4].invoke();until(lambda:not window.busy)
            assert window.session.image_subscribed
            from test_ble_console_images import packets
            wire=list(packets(bytes([1,2,3,4,5,6,7,8]),code=3))
            for packet in wire:window.session._image_notify(window.session.generation,packet)
            root.update();window.render_image()
            assert window.photo is not None and 'UINT8' in window.image_status.get()
            window.buttons[5].invoke();until(lambda:not window.busy)
            assert not window.session.image_subscribed
            window.count.set(500);window.buttons[3].invoke()
            window.stop_button.invoke();until(lambda:not window.busy)
            assert window.summary.get().startswith('STOPPED')
            window.buttons[2].invoke();until(lambda:not window.busy)
            assert not window.session.connected and not window.session.lease.held
            window.close();until(lambda:window.close_sent)
            deadline=time.monotonic()+10
            while window.worker.is_alive() and time.monotonic()<deadline:
                try:root.update()
                except tk.TclError:pass
                time.sleep(.02)
            assert not window.worker.is_alive()
            print('PASS actual Tk scan/select/connect/send/checks/report/stop/disconnect/close; simulated GATT only')
        finally:
            if window.worker.is_alive():
                asyncio.run_coroutine_threadsafe(window.session.close(),window.loop).result(10)
                window.loop.call_soon_threadsafe(window.loop.stop)
            try:root.destroy()
            except tk.TclError:pass


if __name__=='__main__':main()
