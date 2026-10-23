"""Run a gate once with sampled system RAM and GPU memory; preserve actual exit."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def ram_used():
    if os.name=='nt':
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(name,ctypes.c_uint64) for name in
                ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        status=MemoryStatus();status.length=ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):raise OSError('Memory status unavailable')
        return status.total-status.available
    return (os.sysconf('SC_PHYS_PAGES')-os.sysconf('SC_AVPHYS_PAGES'))*os.sysconf('SC_PAGE_SIZE')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('command',nargs=argparse.REMAINDER)
    args=p.parse_args();command=args.command
    if command and command[0]=='--':command=command[1:]
    if not command:p.error('Command required after --')
    started=time.monotonic();process=subprocess.Popen(command)
    report={'command':command,'sampling_interval_s':2,'peak_system_ram_used_bytes':0,'peak_gpu_used_mib':0,
            'scope':'Sampled system totals, including other applications. Not exact process allocation peaks.'}
    while True:
        report['peak_system_ram_used_bytes']=max(report['peak_system_ram_used_bytes'],ram_used())
        try:
            gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
            values=[int(x.strip()) for x in gpu.stdout.splitlines()]
            if values:report['peak_gpu_used_mib']=max(report['peak_gpu_used_mib'],*values)
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        if process.poll() is not None:break
        time.sleep(2)
    report.update(exit_code=process.returncode,runtime_s=round(time.monotonic()-started,2))
    args.out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    return process.returncode


if __name__=='__main__':raise SystemExit(main())
