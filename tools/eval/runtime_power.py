"""Hold a Windows system power request only while an active benchmark runs."""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os


@contextmanager
def system_awake():
    if os.name!='nt':
        yield
        return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    change=kernel.SetThreadExecutionState
    change.argtypes=[wintypes.DWORD];change.restype=wintypes.DWORD
    if not change(0x80000001):raise ctypes.WinError(ctypes.get_last_error())
    print('Active benchmark system power request acquired.',flush=True)
    try:yield
    finally:
        change(0x80000000)
        print('Active benchmark system power request released.',flush=True)


def watch_process(pid):
    """Companion for an already-running gate; process exit ends the request."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        with system_awake():
            while True:
                status=kernel.WaitForSingleObject(handle,5000)
                if status==0:return
                if status!=258:raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.CloseHandle(handle)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch-pid',type=int,required=True)
    watch_process(parser.parse_args().watch_pid)
