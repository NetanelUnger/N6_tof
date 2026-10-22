"""Exercise the actual Tk capture window with a fixture source; no hardware."""


def cli_main():
    global FixtureSource, FrameReader, Path, Sample, SourceStats, VERSION_V4, argparse, args, build_test_record, buttons, close, counts, errors, importlib, io, json, np, record, result, root, root_path, rows, source, spec, start, sys, tempfile, temporary, time, tk, training, ui
    import argparse
    import importlib.util
    import io
    import json
    from pathlib import Path
    import sys
    import tempfile
    import time
    import tkinter as tk
    import numpy as np

    training = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(training / 'scripts'))
    from sample_sources import Sample, SourceStats
    from protocol import FrameReader, build_test_record, VERSION_V4
    spec = importlib.util.spec_from_file_location('capture_ui', training / 'scripts/01_capture.py')
    ui = importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)


    class FixtureSource:
        def __init__(self):
            self.stats = SourceStats(); self.counter = 0; self.port = 'fixture'; self.closed = False
        def open(self): self.stats.state = 'streaming'
        def read(self, timeout=1):
            time.sleep(.06); self.counter += 1
            wire = build_test_record(np.full((42,54), 350 + self.counter, dtype=np.uint16),
                                    frame_id=self.counter, timestamp_ms=self.counter * 60, protocol_version=VERSION_V4)
            self.stats.received += 1
            return Sample(FrameReader(io.BytesIO(wire)).read_frame(), 'fixture-device', 'ab'*16,
                          'fixture-connection', 'fixture', '2026-10-21T00:00:00Z', time.monotonic_ns())
        def stop(self): self.closed = True; self.stats.state = 'closed'
        def status(self): return {'restore_error': None, 'state': self.stats.state}


    with tempfile.TemporaryDirectory(prefix='n6-capture-ui-') as temporary:
        root_path = Path(temporary)
        ui.TRAINING_ROOT = root_path; ui.RAW_ROOT = root_path / 'data/raw'
        ui.mark_stage = lambda *a, **kw: None
        source = FixtureSource()
        ui.create_source = lambda *a, **kw: source
        args = argparse.Namespace(transport='usb', port=None, expected_device=None, device=None, session='ui-fixture',
                                  unlabeled=True, label=None, target_per_class=50, samples_per_burst=3,
                                  save_fps=20, disable_content_filter=True)
        root = tk.Tk(); errors = []; counts = []
        root.report_callback_exception = lambda *e: errors.append(str(e[1]))
        ui.launch_capture(root, args)
        def buttons(widget):
            found = []
            for child in widget.winfo_children():
                if child.winfo_class() in ('TButton', 'Button'): found.append(child)
                found.extend(buttons(child))
            return found
        def start():
            next(b for b in buttons(root) if b.cget('text') == 'Start capture').invoke()
            app = root.capture_app; app.warmup_seconds = 0
        def record(): root.capture_app.toggle_capture()
        def close():
            app = root.capture_app
            counts.append(len(app.store.records()))
            app.close()
        root.after(50, start); root.after(350, record); root.after(1100, close)
        root.after(4000, root.destroy)
        root.mainloop()
        assert not errors, errors
        assert counts == [3], counts
        assert source.closed
        rows = [json.loads(line) for line in (ui.RAW_ROOT / 'ui-fixture/metadata.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows) == 3 and all(r['label'] is None for r in rows)
        result = {'status':'PASS', 'fixture_only':True, 'verification':'Actual Tk Start/SPACE-equivalent/close widget workflow; no native mouse or pixel assertions',
                  'unlabeled_samples':3, 'source_stopped':source.closed, 'serial_in_ui':False}
        (training / 'reports/platform_upgrade_20261021/m3-ui.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))


if __name__ == "__main__":
    cli_main()
