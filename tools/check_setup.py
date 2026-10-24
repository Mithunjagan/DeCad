"""Read-only checks for the pinned native Windows setup. Never installs or launches apps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def run(args):
    return subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=25,creationflags=0x08000000 if os.name=='nt' else 0)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kicad-dir')
    parser.add_argument('--ocr-python')
    parser.add_argument('--orcad-root')
    parser.add_argument('--require-orcad',action='store_true')
    parser.add_argument('--probe-services',action='store_true')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    config=dict(os.environ)
    env_file=ROOT/'backend/.env'
    allowed={'S2SDN_KICAD_DIR','S2SDN_OCR_PYTHON','ORCAD_ROOT'}
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip() in allowed and key.strip() not in config:
                config[key.strip()]=value.strip().strip('"\'')
    checks=[]
    def check(name,passed,detail,required=True):
        checks.append({'name':name,'passed':bool(passed),'required':required,'detail':detail})
    check('Windows',os.name=='nt','Native Capture and the desktop host require Windows.')
    check('Git',shutil.which('git'),'Git must be available in PATH.')
    node=shutil.which('node')
    try:
        version=run([node,'--version']).stdout.strip() if node else ''
        valid=tuple(int(part) for part in version.lstrip('v').split('.')[:3])>=(20,9,0) if version else False
    except (OSError,ValueError,subprocess.TimeoutExpired):version='unavailable';valid=False
    check('Node.js',valid,version or 'Node.js 20.9 or newer is required.')
    kicad=Path(args.kicad_dir or config.get('S2SDN_KICAD_DIR') or 'D:/KICAD')
    check('KiCad CLI',(kicad/'bin/kicad-cli.exe').is_file(),str(kicad/'bin/kicad-cli.exe'))
    check('KiCad Python',(kicad/'bin/python.exe').is_file(),str(kicad/'bin/python.exe'))
    check('KiCad symbol libraries',(kicad/'share/kicad/symbols/Device.kicad_sym').is_file(),str(kicad/'share/kicad/symbols'))
    backend=ROOT/'backend/.venv/Scripts/python.exe'
    check('Backend Python',backend.is_file(),str(backend))
    if backend.is_file():
        try:
            code="import importlib.util,json; names=['fastapi','uvicorn','httpx','pydantic','fitz','cv2','rapidocr_onnxruntime']; print(json.dumps([n for n in names if importlib.util.find_spec(n) is None]))"
            probe=run([str(backend),'-c',code]);missing=json.loads(probe.stdout) if probe.returncode==0 else ['dependency probe failed']
        except (OSError,ValueError,subprocess.TimeoutExpired):missing=['dependency probe failed']
        check('Backend dependencies',not missing,'Missing: '+', '.join(missing) if missing else 'Core API, document and OCR modules found.')
    check('Frontend dependencies',(ROOT/'frontend/node_modules/next/package.json').is_file(),'Run npm ci in frontend.')
    profile=json.loads((ROOT/'backend/pipeline_profiles.json').read_text())['hybrid_max_accuracy']
    model=ROOT/profile['ocr_checkpoint']
    valid_model=model.is_file() and hashlib.sha256(model.read_bytes()).hexdigest()==profile['ocr_checkpoint_sha256']
    check('Pinned OCR checkpoint',valid_model,str(model)+'; SHA-256 must match backend/pipeline_profiles.json.')
    worker=args.ocr_python or config.get('S2SDN_OCR_PYTHON')
    if not worker:
        legacy=ROOT/'backend/.state/claude-20261018/gpu-venv/Scripts/python.exe'
        if legacy.is_file():worker=str(legacy)
    check('CUDA OCR Python',worker and Path(worker).is_file(),str(worker or 'Set S2SDN_OCR_PYTHON in backend/.env.'))
    if worker and Path(worker).is_file():
        try:
            probe=run([worker,'-c',"import torch,onnxruntime as o,json; print(json.dumps({'cuda_available':torch.cuda.is_available(),'providers':o.get_available_providers()}))"])
            runtime=json.loads(probe.stdout) if probe.returncode==0 else {}
            ready=runtime.get('cuda_available') and 'CUDAExecutionProvider' in runtime.get('providers',[])
        except (OSError,ValueError,subprocess.TimeoutExpired):ready=False
        check('CUDA runtime availability',ready,'Availability only; recognition must confirm the providers used by each session.')
    candidates=[args.orcad_root,config.get('ORCAD_ROOT'),'D:/','C:/Cadence/OrCADX_26.1']
    orcad=next((Path(p) for p in candidates if p and all((Path(p)/f).is_file() for f in ('tools/bin/orDb_Dll_Tcl64.dll','tools/bin/tclsh.exe'))),None)
    check('OrCAD native automation',orcad is not None,str(orcad) if orcad else 'Set ORCAD_ROOT to the directory containing tools/bin; a working license is checked during export.',args.require_orcad)
    if args.probe_services:
        for name,url in [('API','http://127.0.0.1:8100/health'),('Frontend','http://localhost:3100/manifest.webmanifest')]:
            try:
                with urllib.request.urlopen(url,timeout=8) as response:ready=response.status==200
            except (OSError,ValueError):ready=False
            check(name+' service',ready,url)
    passed=all(c['passed'] for c in checks if c['required'])
    report={'passed':passed,'scope':'Native Windows setup prerequisites; no inference, licensing or accuracy certification','checks':checks}
    if args.json:print(json.dumps(report,indent=2))
    else:
        for c in checks:
            status='PASS' if c['passed'] else 'FAIL' if c['required'] else 'OPTIONAL'
            print(f'{status:8} {c["name"]}: {c["detail"]}')
        print('Setup prerequisites passed.' if passed else 'Resolve the required checks above; see docs/SETUP.md.')
    return 0 if passed else 1

if __name__=='__main__':
    sys.exit(main())
