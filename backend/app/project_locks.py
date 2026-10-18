"""Explicit recovery from stale local KiCad locks, without deleting lock assets."""
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from .engine import OperationError


def running_kicad_processes():
    if os.name != 'nt':
        raise OperationError('Force recovery of KiCad locks is currently supported on Windows.')
    command = "Get-CimInstance Win32_Process -Filter \"Name='eeschema.exe' OR Name='kicad.exe' OR Name='pcbnew.exe'\" -ErrorAction Stop | Select-Object ProcessId,Name | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError('Process inspection failed.')
        processes = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(processes, dict):
            processes = [processes]
        if not isinstance(processes, list):
            raise ValueError('Invalid process list.')
        return processes
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise OperationError('Could not verify whether KiCad is still running. Close KiCad and retry.') from exc


def verified_other_editors(state, project):
    """Exclude only live owned editors proven to display a different project."""
    if os.name != 'nt':return set()
    import ctypes as ct
    from ctypes import wintypes as wt
    user32=ct.WinDLL('user32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wt.HWND,ct.POINTER(wt.DWORD)]
    user32.GetWindowTextW.argtypes=[wt.HWND,wt.LPWSTR,ct.c_int]
    user32.IsWindow.argtypes=[wt.HWND]
    other=set()
    for file in (Path(state)/'native-desktop').glob('*/status.json'):
        try:
            status=json.loads(file.read_text())
            if status.get('closed') or time.time()-status['updated']>6:continue
            active=Path(status['project']).resolve();path=Path(status['path']).resolve()
            if active==Path(project).resolve() or path.parent!=active:continue
            hwnd=status.get('hwnd');pid=status.get('editor_pid')
            if not hwnd or not pid or not user32.IsWindow(hwnd):continue
            owner=wt.DWORD();user32.GetWindowThreadProcessId(hwnd,ct.byref(owner))
            title=ct.create_unicode_buffer(1024);user32.GetWindowTextW(hwnd,title,len(title))
            if owner.value==pid and path.stem in title.value and 'Schematic Editor' in title.value:other.add(pid)
        except (OSError,ValueError,KeyError,TypeError):continue
    return other


def allow_stale_lock_recovery(locks, state=None, project=None):
    if state is None:
        from .main import STATE
        state=STATE
    if project is None:project=locks[0].parent
    # KiCad locks contain a host/user, not a PID. Their age cannot prove safety.
    # Unknown editors could have opened the design through File > Open, so their
    # command line alone cannot establish that a stale lock is safe to bypass.
    processes=running_kicad_processes()
    other=verified_other_editors(state,project) if processes else set()
    if any(p.get('ProcessId') not in other for p in processes):
        raise OperationError('KiCad may still be using this project. Save and close that window, then force move to trash.')
    for path in locks:
        if path.is_symlink() or not path.name.endswith(('.kicad_pro.lck', '.kicad_sch.lck', '.kicad_pcb.lck')):
            raise OperationError('An unrecognized lock blocks recovery. Close the application using this project.')
        try:
            owner = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise OperationError('The lock owner could not be verified. Close the application using this project.') from exc
        if not isinstance(owner, dict) or str(owner.get('hostname', '')).casefold() != socket.gethostname().casefold():
            raise OperationError('This lock belongs to another computer. Release it there before moving the project.')
    # Keep every lock in the recoverable project trash, alongside the design.
