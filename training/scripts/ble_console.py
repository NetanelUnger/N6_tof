"""N6 BLE desktop diagnostic console, also usable as an automated CLI."""
from __future__ import annotations
import argparse
import asyncio
import json
import queue
import threading
import time

from ble_console_core import BleSession, READ_COMMANDS, run_checks, save_report, utc_now
from ble_console_soak import run_soak
from ble_console_images import decode_pixels, colorize, MODES, CHANNELS


async def cli(args):
    session = BleSession()
    reports = []
    try:
        if args.scan:
            print(json.dumps(await session.scan(), indent=2))
            return 0
        if args.soak:
            await session.connect(args.address)
            report,path=await run_soak(session,args.soak,args.encoding,uart=args.uart,usb=args.usb,
                report_dir=args.report_dir,progress=lambda state:print(json.dumps(state),flush=True))
            print(json.dumps({'passed':report['passed'],'report':path,'finding':report['finding'],
                              'failure':report.get('failure')}),flush=True)
            return 0 if report['passed'] else 1
        for cycle in range(args.cycles):
            report = {'passed': False, 'started_utc': utc_now(), 'address': args.address}
            try:
                await session.connect(args.address)
                report = await run_checks(session, args.pings, args.interval)
            except Exception as error:
                report = {'passed': False, 'started_utc': utc_now(),
                          'address': args.address, 'error': type(error).__name__+': '+str(error)}
            finally:
                try:
                    await session.close()
                except Exception as error:
                    report['passed'] = False
                    report['cleanup_error'] = str(error)
            report['cycle'] = cycle+1
            path = save_report(report, args.report_dir)
            reports.append(report)
            print(json.dumps({'cycle': cycle+1, 'passed': report['passed'],
                              'pings': report.get('pings_completed', 0),
                              'max_ms': report.get('ping_max_ms'), 'report': str(path),
                              'error': report.get('error')}), flush=True)
            if not report['passed']:
                return 1
        return 0
    finally:
        await session.close()


class ConsoleWindow:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root = root
        root.title('N6 BLE Console')
        root.geometry('1040x760')
        root.minsize(850, 620)
        self.events = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self.session = BleSession(lambda kind, data: self.events.put((kind, data)))
        self.worker = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.worker.start()
        self.busy = False
        self.closing = False
        self.close_sent = False
        self.stop = threading.Event()
        self.devices = []
        self.buttons = []
        self.status = tk.StringVar(value='Disconnected — scan for an N6 device to begin')
        self.count = tk.IntVar(value=20)
        self.summary = tk.StringVar(value='No test run yet')
        self.report_path = tk.StringVar(value='Reports are saved automatically after every test run.')
        self.encoding = tk.StringVar(value='UINT8')
        self.soak_minutes = tk.IntVar(value=15)
        self.image_status = tk.StringVar(value='Images stopped')
        self.displayed_image = None
        self.photo = None
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', padding=(12, 7))
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
        style.configure('Treeview', rowheight=27)
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='N6  /  BLE Console', style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel, text='Connect • inspect • run repeatable checks', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 16))
        connection = ttk.LabelFrame(panel, text='Device', padding=12)
        connection.pack(fill='x')
        self.device_box = ttk.Combobox(connection, state='readonly', width=47)
        self.device_box.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.button(connection, 'Scan', self.scan)
        self.button(connection, 'Connect', self.connect)
        self.button(connection, 'Disconnect', lambda: self.submit('disconnect', self.session.close()))
        ttk.Label(panel, textvariable=self.status, wraplength=950).pack(anchor='w', pady=(9, 12))
        actions = ttk.Frame(panel)
        actions.pack(fill='x')
        ttk.Label(actions, text='Ping count').pack(side='left')
        ttk.Spinbox(actions, from_=1, to=500, textvariable=self.count, width=6).pack(side='left', padx=8)
        self.button(actions, 'Run checks', self.run_tests)
        self.stop_button = ttk.Button(actions, text='Stop after current command', command=self.stop.set)
        self.stop_button.pack(side='left', padx=4)
        self.stop_button.state(['disabled'])
        stream_controls=ttk.Frame(panel)
        stream_controls.pack(fill='x',pady=(10,0))
        ttk.Label(stream_controls,text='Sensor images').pack(side='left')
        ttk.Combobox(stream_controls,textvariable=self.encoding,values=('RAW','UINT16','UINT8','JPEG'),
                     width=8,state='readonly').pack(side='left',padx=7)
        self.button(stream_controls,'Start / apply',lambda:self.submit('images',self.session.start_images(self.encoding.get())))
        self.button(stream_controls,'Stop images',lambda:self.submit('images',self.session.stop_images()))
        ttk.Spinbox(stream_controls,from_=1,to=120,textvariable=self.soak_minutes,width=4).pack(side='left',padx=6)
        self.button(stream_controls,'Min. connection test',self.run_soak)
        ttk.Label(panel, textvariable=self.summary, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=12)
        notebook = ttk.Notebook(panel)
        notebook.pack(fill='both', expand=True)
        results = ttk.Frame(notebook)
        terminal = ttk.Frame(notebook)
        viewer = ttk.Frame(notebook,padding=10)
        notebook.add(viewer,text='Sensor image')
        notebook.add(results, text='Test results')
        notebook.add(terminal, text='Responses')
        self.table = ttk.Treeview(results, columns=('command','result','ms'), show='headings')
        for key, title, width in [('command','Command',620),('result','Result',100),('ms','Time (ms)',100)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor='w' if key=='command' else 'center')
        self.table.tag_configure('pass', foreground='#187344')
        self.table.tag_configure('fail', foreground='#b42318')
        scroll = ttk.Scrollbar(results, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.table.pack(fill='both', expand=True)
        self.output = ScrolledText(terminal, wrap='word', font=('Consolas',10), state='disabled')
        self.output.pack(fill='both', expand=True)
        self.image_label=ttk.Label(viewer,text='Start sensor images to view validated frames',anchor='center')
        self.image_label.pack(fill='both',expand=True)
        ttk.Label(viewer,textvariable=self.image_status,wraplength=940).pack(fill='x')
        manual = ttk.Frame(panel)
        manual.pack(fill='x', pady=12)
        ttk.Label(manual, text='Diagnostic command').pack(side='left', padx=(0, 8))
        self.command_box = ttk.Combobox(manual, values=READ_COMMANDS, state='normal')
        self.command_box.set('version')
        self.command_box.pack(side='left', fill='x', expand=True)
        self.button(manual, 'Send', self.send_command)
        self.command_box.bind('<Return>',lambda _:self.send_command())
        ttk.Label(panel, textvariable=self.report_path, wraplength=950).pack(anchor='w')
        ttk.Label(panel, text='CLI + CRC-validated sensor frames • no Windows pairing • ping limit 1500 ms', foreground='#555555').pack(anchor='w', pady=(7,0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(50, self.poll)

    def button(self, parent, text, action):
        from tkinter import ttk
        button = ttk.Button(parent, text=text, command=action)
        button.pack(side='left', padx=4)
        self.buttons.append(button)
        return button

    def submit(self, name, coroutine):
        if self.busy:
            coroutine.close()
            return
        self.busy = True
        for button in self.buttons: button.state(['disabled'])
        self.status.set(name.capitalize()+'…')
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        def done(completed):
            try: self.events.put(('done', (name, completed.result(), None)))
            except BaseException as error: self.events.put(('done', (name, None, type(error).__name__+': '+str(error))))
        future.add_done_callback(done)

    def scan(self):
        self.submit('scan', self.session.scan())

    def connect(self):
        index = self.device_box.current()
        if index < 0:
            self.status.set('Scan and select an N6 device first')
            return
        self.submit('connect', self.session.connect(self.devices[index]['address']))

    def run_tests(self):
        try:
            count = self.count.get()
            if not 1 <= count <= 500: raise ValueError()
        except Exception:
            self.status.set('Ping count must be 1..500')
            return
        if not self.session.connected:
            self.status.set('Connect to N6 first')
            return
        self.table.delete(*self.table.get_children())
        self.stop.clear()
        self.summary.set('Running health checks and '+str(count)+' pings…')
        self.stop_button.state(['!disabled'])
        async def run():
            report = await run_checks(self.session, pings=count, stop=self.stop)
            path = await asyncio.to_thread(save_report, report)
            return report, str(path)
        self.submit('tests', run())

    def log(self, text):
        self.output.configure(state='normal')
        self.output.insert('end', text+'\n')
        if int(self.output.index('end-1c').split('.')[0]) > 2500:
            self.output.delete('1.0','500.0')
        self.output.see('end')
        self.output.configure(state='disabled')

    def send_command(self):
        text=self.command_box.get().strip()
        if text.upper()=='MAP ON':
            self.submit('images',self.session.start_images(self.encoding.get()))
        elif text.upper()=='MAP OFF':
            self.submit('images',self.session.stop_images())
        else:
            self.submit('command',self.session.command(text))

    def run_soak(self):
        try:
            seconds=self.soak_minutes.get()*60
            if not 60<=seconds<=7200:raise ValueError()
        except Exception:
            self.status.set('Connection test duration must be 1..120 minutes');return
        if not self.session.connected:
            self.status.set('Connect first');return
        self.stop.clear();self.stop_button.state(['!disabled'])
        self.summary.set('Testing continuous images and CLI…')
        self.submit('soak',run_soak(self.session,seconds,self.encoding.get(),stop=self.stop,
            progress=lambda data:self.events.put(('progress',data))))

    def render_image(self):
        from PIL import Image, ImageTk
        frame=self.session.latest_image
        if frame is None:
            self.displayed_image=None
            self.photo=None
            self.image_label.configure(image='',text='Waiting for a complete sensor frame' if self.session.image_subscribed else 'Images stopped')
            self.image_status.set('No current validated frame')
            return
        if self.displayed_image is not frame:
            self.displayed_image=frame
            try:
                image,low,high=colorize(decode_pixels(frame))
                scale=max(1,min(10,(self.image_label.winfo_width()-8)//frame['width'],
                                     (self.image_label.winfo_height()-8)//frame['height']))
                self.photo=ImageTk.PhotoImage(image.resize((frame['width']*scale,frame['height']*scale),Image.Resampling.NEAREST))
                self.image_label.configure(image=self.photo,text='')
                self.image_range=(low,high)
            except Exception as error:
                self.image_status.set('Image decode error: '+str(error));self.log(str(error));return
        age=time.monotonic()-frame['host_monotonic']
        low,high=getattr(self,'image_range',(None,None))
        scale_text='no valid pixels' if low is None else f'{low:.1f}..{high:.1f}'+(' mm' if frame['channel']==1 else '')
        npu=frame.get('npu') or {}
        ai=f"NPU {('none','rock','paper','scissors')[npu['class_id']]} score {npu['confidence']/10:.1f}%" if npu.get('state')==3 else 'NPU: no matching result'
        self.image_status.set(f"{'STALE' if age>3 or not self.session.image_subscribed or not self.session.connected else 'LIVE'} • "
            f"{CHANNELS.get(frame['channel'])} {frame['width']}×{frame['height']} {MODES.get(frame['pixel_format'])} • "
            f"source {frame['frame_id']} • received {self.session.images.completed} • age {age:.1f}s\n"
            f"Dynamic scale: {scale_text} • {ai} • CRC errors {self.session.images.crc_errors} • assembly drops {self.session.images.dropped}")

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'connection': self.status.set(data)
                elif kind == 'progress':
                    self.summary.set(f"{data['elapsed_s']}s • {data['frames']} images • {data['pings']} pings • {data['violations']} violations")
                elif kind == 'reply':
                    self.log('> '+data['command']+'  ('+str(data['ms'])+' ms)\n'+data['response'].replace('\r','\n').strip())
                elif kind == 'check':
                    passed = data['passed']
                    item = self.table.insert('', 'end', values=(data['command'],'PASS' if passed else 'FAIL',data['ms']), tags=('pass' if passed else 'fail',))
                    self.table.see(item)
                elif kind == 'done':
                    name, value, error = data
                    self.busy = False
                    for button in self.buttons: button.state(['!disabled'])
                    self.stop_button.state(['disabled'])
                    self.status.set(('Connected: '+str(self.session.address)) if self.session.connected else 'Disconnected')
                    if name == 'close':
                        if error:
                            self.closing = self.close_sent = False
                            self.status.set(error); self.log(error)
                        else:
                            self.loop.call_soon_threadsafe(self.loop.stop)
                            self.root.destroy()
                            return
                        continue
                    if error:
                        self.status.set(error); self.log(error)
                        if name == 'tests': self.summary.set('FAIL — '+error)
                    elif name == 'scan':
                        self.devices = value
                        self.device_box['values'] = [d['name']+'  |  '+d['address'] for d in value]
                        if value: self.device_box.current(0)
                        else: self.device_box.set(''); self.status.set('No N6 advertisement found')
                    elif name == 'tests':
                        report, path = value
                        outcome = 'PASS' if report['passed'] else 'STOPPED' if report['cancelled'] else 'FAIL'
                        self.summary.set(f"{outcome}  •  {report['pings_completed']} pings  •  max {report['ping_max_ms']} ms")
                        self.report_path.set(path)
                        if report.get('error'): self.log(report['error'])
                    elif name == 'soak':
                        report,path=value
                        self.summary.set(('PASS' if report['passed'] else 'STOPPED' if report.get('cancelled') else 'FAIL')+
                            f" • {report.get('measurement_elapsed_s',0):.1f}s • {report.get('frames_received',0)} images")
                        self.report_path.set(path)
                        self.log(report.get('failure',report['finding']))
        except queue.Empty:
            pass
        self.render_image()
        if self.closing and not self.busy and not self.close_sent:
            self.close_sent = True
            self.submit('close', self.session.close())
        self.root.after(50, self.poll)

    def close(self):
        self.closing = True
        self.stop.set()
        self.status.set('Finishing current command and disconnecting…')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--scan', action='store_true')
    mode.add_argument('--run', action='store_true', help='Run diagnostic checks without opening a window')
    mode.add_argument('--soak',type=int,metavar='SECONDS',help='Continuous sensor images and CLI, 10..7200 seconds')
    parser.add_argument('--address', help='Exact BLE address from --scan')
    parser.add_argument('--pings', type=int, default=20)
    parser.add_argument('--cycles', type=int, default=1, help='Explicit disconnect/reconnect cycles, 1..10')
    parser.add_argument('--interval', type=float, default=.2)
    parser.add_argument('--report-dir')
    parser.add_argument('--encoding',choices=('RAW','UINT16','UINT8','JPEG'),default='UINT8')
    parser.add_argument('--uart',help='Optional independent ST-LINK capture, e.g. COM6')
    parser.add_argument('--usb',help='Optional USB before/after health evidence, e.g. COM8')
    args = parser.parse_args()
    if not 1 <= args.pings <= 500 or not 1 <= args.cycles <= 10 or not 0 <= args.interval <= 10:
        parser.error('pings 1..500, cycles 1..10, interval 0..10')
    if args.soak is not None and not 10<=args.soak<=7200:parser.error('--soak must be 10..7200')
    if (args.run or args.soak) and not args.address:
        parser.error('--run/--soak requires --address from --scan')
    if args.run or args.scan or args.soak:
        return asyncio.run(cli(args))
    import tkinter as tk
    root = tk.Tk()
    ConsoleWindow(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
