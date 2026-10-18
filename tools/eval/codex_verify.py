"""Sequential, reproducible checks for the October 18 repair work (no parallel OCR)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import orcad_capture as oc


def compare(before, after):
    failures = []
    for sample, old in before.items():
        new = after.get(sample, {})
        if 'error' in new or not new.get('dsn_passed'):
            failures.append(f'{sample}: {new}')
            continue
        for field in ('parts_found', 'values_ok', 'pins_exact'):
            if new.get(field, -1) < old.get(field, 0):
                failures.append(f'{sample}: {field} {old[field]} -> {new.get(field)}')
        if new.get('parts_spurious', 0) > old.get('parts_spurious', 0):
            failures.append(f'{sample}: spurious parts increased')
        for value, (found, _) in old.get('value_counts', {}).items():
            if new.get('value_counts', {}).get(value, [0])[0] < found:
                failures.append(f'{sample}: fewer {value}')
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage')
    ap.add_argument('--netlist-only', action='store_true')
    ap.add_argument('--skip-clear', action='store_true', help='resume at PDFs using completed clear results')
    ap.add_argument('--baseline', default='backend/.state/codex-20261018/supplied-baseline.json')
    args = ap.parse_args()
    out = ROOT / 'tools/eval/results' / args.stage
    out.mkdir(parents=True, exist_ok=True)
    if not args.netlist_only:
        commands = [[sys.executable, 'tools/eval/run_eval.py', '--cache-ocr', '--out', str(out), '1', '2', '3', '4', '5']]
        commands += [[sys.executable, 'tools/eval/run_eval.py', '--cache-ocr', '--out', str(out), '--images',
                      'tools/eval/degraded', '--variant', variant, '4']
                     for variant in ('scan300', 'scan200', 'blur300')]
        for i, command in enumerate(commands):
            if i == 0 and args.skip_clear:
                continue
            with (out / f'run-{i}.log').open('w', encoding='utf-8') as log:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True,
                               env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            print((out / f'run-{i}.log').read_text(encoding='utf-8', errors='replace'), flush=True)
    failures = compare(json.loads((ROOT / args.baseline).read_text()),
                       json.loads((out / 'report.json').read_text()))
    netlists = {}
    for dsn in sorted(out.glob('S*/orcad/*.DSN')):
        dest = dsn.parent.parent / 'pcb-netlist'
        dest.mkdir(exist_ok=True)
        command = [r'D:\tools\bin\pstswp.exe', '-pst', '-d', str(dsn), '-n', str(dest),
                   '-c', r'D:\tools\capture\allegro.cfg', '-v', '3', '-l', '31', '-s', '',
                   '-j', 'PCB Footprint', '-hpath', 'HPathForCollision']
        proc = subprocess.run(command, capture_output=True, timeout=180,
                              env={**os.environ, 'CDSROOT': 'D:\\',
                                   'PATH': r'D:\tools\bin' + os.pathsep + os.environ.get('PATH', '')})
        (dest / 'netlister-output.log').write_bytes(proc.stdout + proc.stderr)
        logpath = dest / 'netlist.log'
        log = logpath.read_text(errors='replace') if logpath.exists() else ''
        import re
        counts = re.findall(r'(\d+)\s+errors?\b', log, re.I)
        # This Capture build logs ERROR(...) entries but no numeric summary on success.
        errors = len(re.findall(r'\b(?:ERROR|FATAL)\s*[:(]', log, re.I))
        passed = (logpath.exists() and proc.returncode == 0 and errors == 0
                  and all(int(n) == 0 for n in counts)
                  and all((dest / name).is_file() for name in ('pstchip.dat', 'pstxprt.dat', 'pstxnet.dat')))
        netlists[dsn.parent.parent.name] = {'passed': passed, 'returncode': proc.returncode,
                                           'errors': errors, 'summary_counts': counts}
        if not passed:
            failures.append(f'{dsn.parent.parent.name}: PCB netlist did not report zero errors')
        print(dsn.parent.parent.name, netlists[dsn.parent.parent.name], flush=True)
    source_files = ['backend/app/ingestion.py', 'backend/app/digital_vision.py',
                    'backend/app/orcad_capture.py', 'backend/app/orcad_writer.tcl',
                    'backend/app/orcad_route.py', 'tools/eval/run_eval.py']
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files}
    (out / 'gate.json').write_text(json.dumps({'regressions': failures, 'netlists': netlists,
                                              'source_sha256': source_hashes}, indent=2))
    print('REGRESSIONS:', failures, flush=True)
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
