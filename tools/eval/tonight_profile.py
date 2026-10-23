"""Run a gate once with sampled system RAM and GPU memory; preserve actual exit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('command',nargs=argparse.REMAINDER)
    args=p.parse_args();command=args.command
    if command and command[0]=='--':command=command[1:]
    if not command:p.error('Command required after --')
    started=time.monotonic();process=subprocess.Popen(command)
    report={'command':command,'sampling_interval_s':2,'peak_system_ram_used_bytes':0,'peak_gpu_used_mib':0,
            'scope':'Sampled system totals, including other applications. Not exact process allocation peaks.'}
    while True:
        report['peak_system_ram_used_bytes']=max(report['peak_system_ram_used_bytes'],psutil.virtual_memory().used)
        try:
            gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
            report['peak_gpu_used_mib']=max(report['peak_gpu_used_mib'],*[int(x.strip()) for x in gpu.stdout.splitlines()])
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        if process.poll() is not None:break
        time.sleep(2)
    report.update(exit_code=process.returncode,runtime_s=round(time.monotonic()-started,2))
    args.out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    return process.returncode


if __name__=='__main__':raise SystemExit(main())
