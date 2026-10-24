"""Run selected native OCR cases in serialized, isolated GPU processes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,default=ROOT/'evidence/precision-20261023/accepted-fresh/native')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--include',nargs='+',required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    baseline=json.loads((args.baseline/'report.json').read_text())['cases']
    combined={'cases':{},'regressions':[],'fresh_ocr':True,'process_isolated':True}
    for name in args.include:
        folder=args.out/name
        command=[sys.executable,'tools/eval/profile_eval.py','native_recognition_gate','--sources',baseline[name]['source'],
                 '--include',name,'--baseline',str(args.baseline),'--out',str(folder),'--diagnostic']
        print('Recognizing',name,flush=True)
        with (args.out/(name+'.log')).open('w',encoding='utf-8') as stream:
            result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        if (folder/'report.json').exists():
            observed=json.loads((folder/'report.json').read_text());combined['cases'].update(observed['cases'])
            combined['regressions']+=observed['regressions']
        if result.returncode and not any(name in e for e in combined['regressions']):combined['regressions'].append(name+': worker failed')
        (args.out/'report.json').write_text(json.dumps(combined,indent=2))
    print('Regressions:',combined['regressions'],flush=True)
    raise SystemExit(bool(combined['regressions']))
