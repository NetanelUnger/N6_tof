"""Audit helper names and imports; child workers deny hardware and subprocesses."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


def inventory(root):
    roots = ('Tools', 'hil_tests', 'training/scripts', '.local-dependencies')
    return sorted({p.resolve() for folder in roots for p in (root / folder).rglob('*.py')
                   if not any(part in p.parts for part in ('.venv', '__pycache__', 'node_modules'))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = inventory(root)
    known = set(sys.stdlib_module_names) | set(importlib.metadata.packages_distributions())
    collisions = [str(p.relative_to(root)) for p in paths if p.stem in known]
    child = root / 'Tools/check_import_child.py'
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')

    def check(target):
        try:
            process = subprocess.run([sys.executable, '-I', '-B', str(child),
                                      '--target', str(target), '--root', str(root)],
                                     capture_output=True, text=True, timeout=20,
                                     env=environment, encoding='utf-8', errors='replace')
            records = [line.split('=', 1)[1] for line in process.stdout.splitlines()
                       if line.startswith('N6_IMPORT_AUDIT_RESULT=')]
            if records:
                value = json.loads(records[-1])
                value['path'] = str(target.relative_to(root))
                return value
            return {'path': str(target.relative_to(root)), 'passed': False,
                    'error': 'Worker failed before result: ' + process.stderr[-1000:]}
        except subprocess.TimeoutExpired:
            return {'path': str(target.relative_to(root)), 'passed': False,
                    'error': 'Import exceeded20s; worker terminated'}

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
        results = list(executor.map(check, paths))
    report = {'python': sys.executable, 'scope': 'Host imports only, no hardware access',
              'count': len(paths), 'collisions': collisions, 'results': results,
              'passed': not collisions and all(value['passed'] for value in results)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('count', 'collisions', 'passed')}), flush=True)
    for value in results:
        if not value['passed']:
            print(json.dumps(value), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
