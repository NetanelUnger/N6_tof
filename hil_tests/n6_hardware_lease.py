"""Hold a host-only exclusive N6 test lease. This never opens hardware.

Other testers must check the marker/status and active serial/debug processes.
An existing marker is a coordination blocker; this tool never steals a lease.
Use a terminal with stdin open, then enter 'release' after closing owned handles.
"""
import argparse
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
import sys
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--owner-thread', required=True)
parser.add_argument('--scope', choices=('ram','xip-update'), default='ram')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[1]
# Every linked worktree must coordinate with legacy tests in the primary
# checkout, rather than accidentally creating an independent hardware lease.
common = subprocess.check_output(['git','-c','safe.directory='+str(repository),
    '-C',str(repository),'rev-parse','--path-format=absolute','--git-common-dir'], text=True).strip()
folder = Path(common).parent / '.local-dependencies/diagnostics' 
folder.mkdir(exist_ok=True, parents=True)
marker = folder / 'n6-hardware-owner.lock'
status = folder / 'n6-hardware-owner.json'
if status.exists():
    raise SystemExit('BLOCKED: existing N6 owner status; coordinate before hardware access.')
try:
    handle = marker.open('x+b')
except FileExistsError:
    raise SystemExit('BLOCKED: existing N6 lease; coordinate before hardware access.')
owner = {'thread': args.owner_thread, 'pid': os.getpid(),
         'started_utc': datetime.now(timezone.utc).isoformat(),
         'scope': ('protected RAM-only tests; no persistent writes' if args.scope == 'ram' else
                   'authorized recoverable XIP/USB/OTA NOR validation; no OTP, settings, credential or pairing writes')}
try:
    handle.write(b'1'); handle.flush(); handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    # Windows locks the marker against reads too. Publish a separate status.
    with status.open('x', encoding='utf-8') as output:
        json.dump(owner, output, indent=2)
    print(json.dumps({'ownership': 'HELD', **owner}), flush=True)
    if sys.stdin.readline().strip() != 'release':
        raise RuntimeError('lease input closed; stop tests and re-establish ownership')
finally:
    handle.close()
    marker.unlink()
    if status.exists() and json.loads(status.read_text()) == owner:
        status.unlink()
    print('OWNERSHIP RELEASED', flush=True)
