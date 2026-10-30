"""Replay exact saved C inputs. No firmware build, board, or repository edits."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, subprocess, sys

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); here=Path(__file__).resolve().parent
    summary=json.loads((here/'summary.json').read_text())
    a.output.mkdir(parents=True,exist_ok=False)
    runner=a.repo/'hil_tests/test_wifi_scan_lifetime.py'
    child='''import importlib.util, pathlib, sys
s=importlib.util.spec_from_file_location("native_runner",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.run_native(pathlib.Path(sys.argv[2]).read_text())
'''
    failed=[]
    for case in summary['native_results']:
        source=here/case['generated_c']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==case['generated_c_sha256']
        result=subprocess.run([sys.executable,'-B','-c',child,str(runner),str(source)],capture_output=True,text=True)
        (a.output/(case['suite']+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode: failed.append(case['suite'])
        print(case['suite'],result.returncode)
    raise SystemExit(bool(failed))
