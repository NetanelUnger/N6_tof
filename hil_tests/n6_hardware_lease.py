"""Hold a host-only exclusive N6 test lease. This never opens hardware.

Other testers must check the marker/status and active serial/debug processes.
An existing marker is a coordination blocker; this tool never steals a lease.
Use a terminal with stdin open, then enter 'release' after closing owned handles.
"""


def windows_process_identity(pid):
    """Host process query only. Access denied is UNKNOWN, never proof of death."""
    import ctypes
    from ctypes import wintypes
    from datetime import datetime, timedelta, timezone
    if not isinstance(pid, int) or pid <= 0:
        return {'state': 'unknown', 'reason': 'invalid PID'}
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        return {'state': 'absent' if error == 87 else 'unknown', 'winerror': error}
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return {'state': 'unknown', 'winerror': ctypes.get_last_error()}
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        return {'state': 'alive', 'created_utc': created.isoformat()}
    finally:
        kernel.CloseHandle(handle)


def recover_owned_stale(folder, ready_path, evidence, expected_thread, probe=windows_process_identity):
    """Explicit host-only recovery. Archive only an exact, dead, unlocked owner.

    No automatic takeover, port opening, process termination or force-delete.
    Any live PID (including reuse), failed process query or changed file blocks.
    """
    import hashlib
    import json
    import msvcrt
    import os
    from pathlib import Path
    import uuid
    folder, ready_path, evidence = map(Path, (folder, ready_path, evidence))
    status = folder / 'n6-hardware-owner.json'
    marker = folder / 'n6-hardware-owner.lock'
    guard = folder / 'n6-hardware-recovery.lock'
    ready_bytes = ready_path.read_bytes()
    ready = json.loads(ready_bytes)
    raw = status.read_bytes()
    owner = json.loads(raw)
    keys = ('thread', 'pid', 'started_utc', 'scope', 'process_created_utc')
    if owner.get('thread') != expected_thread or any(owner.get(k) != ready.get(k) for k in keys):
        raise RuntimeError('Owner/start identity mismatch; no recovery')
    if not owner['scope'].startswith('XIP passive COM6 UART capture only;'):
        raise RuntimeError('This recovery is restricted to our passive recorder')
    if probe(owner['pid']).get('state') != 'absent':
        raise RuntimeError('PID live/reused or unverified; no recovery')
    if evidence.exists():
        raise RuntimeError('Fresh evidence directory required')
    token = uuid.uuid4().hex.encode()
    guard_handle = guard.open('x+b')
    locked = None
    try:
        guard_handle.write(token); guard_handle.flush()
        if status.read_bytes() != raw:
            raise RuntimeError('Owner changed; no recovery')
        locked = marker.open('r+b')
        msvcrt.locking(locked.fileno(), msvcrt.LK_NBLCK, 1)
        locked.seek(0)
        if locked.read() != b'1':
            raise RuntimeError('Unexpected marker contents; no recovery')
        file_id = os.fstat(locked.fileno()).st_ino
        identity = probe(owner['pid'])
        if identity.get('state') != 'absent' or status.read_bytes() != raw:
            raise RuntimeError('PID/owner changed; no recovery')
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / 'ready.json').write_bytes(ready_bytes)
        result = {'owner': owner, 'process_check': identity,
                  'declared_start_identity_matched': True,
                  'original_process_creation_recorded': 'process_created_utc' in owner,
                  'owner_status_sha256': hashlib.sha256(raw).hexdigest(),
                  'marker_lock_acquired': True, 'port_free_verified': False,
                  'hardware_access': False, 'action': 'archive exact stale owner files'}
        (evidence / 'validated.json').write_text(json.dumps(result, indent=2) + '\n')
        # Windows cannot rename the CRT handle while it is open. The original
        # status still blocks new acquisition during this narrow interval, and
        # cooperative entrypoints also honor the recovery guard.
        locked.close(); locked = None
        if (marker.stat().st_ino != file_id or marker.read_bytes() != b'1' or
                status.read_bytes() != raw or probe(owner['pid']).get('state') != 'absent'):
            raise RuntimeError('Lease changed before archive; no recovery')
        marker.rename(evidence / marker.name)
        if status.read_bytes() != raw:
            raise RuntimeError('Status changed after marker archive; preserve evidence')
        status.rename(evidence / status.name)
        result['archived'] = True
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    finally:
        if locked is not None:
            locked.close()
        guard_handle.close()
        if guard.read_bytes() == token:
            guard.unlink()


def cli_main():
    global Path, argparse, args, common, datetime, folder, handle, json, marker, msvcrt, os, output, owner, parser, repository, status, subprocess, sys, timezone
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
    parser.add_argument('--recover-stale-from', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
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
    if args.recover_stale_from:
        branch = subprocess.check_output(['git','-c','safe.directory='+str(repository),'-C',str(repository),
                                          'branch','--show-current'], text=True).strip()
        if branch != 'feature/n6-xip-ota-usb' or not args.evidence_dir:
            raise SystemExit('Recovery requires the feature branch and explicit evidence directory')
        for path in (args.recover_stale_from.resolve(), args.evidence_dir.resolve()):
            if not path.is_relative_to(repository):
                raise SystemExit('Recovery evidence must stay within the feature worktree')
        print(json.dumps(recover_owned_stale(folder,args.recover_stale_from,args.evidence_dir,args.owner_thread)),flush=True)
        return
    if args.evidence_dir:
        raise SystemExit('Evidence directory is only for explicit stale recovery')
    if (folder / 'n6-hardware-recovery.lock').exists():
        raise SystemExit('BLOCKED: host-only lease recovery in progress')
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
    identity = windows_process_identity(os.getpid())
    if identity.get('state') == 'alive':
        owner['process_created_utc'] = identity['created_utc']
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


if __name__ == "__main__":
    cli_main()
