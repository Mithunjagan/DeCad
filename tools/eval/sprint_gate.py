"""Serialized, process-isolated actual OCR gates. Never replay model outputs.

Run with the CUDA Python; --tests uses KiCad's native Python for API/CLI checks.
Every subprocess log and raw prediction is retained in the selected phase folder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SAMPLES=('S1','S2','S3','S4','S5','S4-scan300','S4-scan200','S4-blur300')


def run(command,log,environment):
    print('Running',log.name,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(x) for x in command],cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{log.name} failed ({result.returncode}); see {log}')


def main(args):
    args.out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONPATH':str(ROOT/'backend'),
         'KICAD_CLI':'D:/KICAD/bin/kicad-cli.exe','KICAD_SYMBOL_DIR':'D:/KICAD/share/kicad/symbols',
         'KICAD_FOOTPRINT_DIR':'D:/KICAD/share/kicad/footprints','KICAD_PYTHON':'D:/KICAD/bin/python.exe'}
    summary={'passed':False,'fresh_ocr':True,'process_isolated':True,'errors':[]}
    try:
        if args.tests:
            run([ROOT/'backend/.venv/Scripts/python.exe','-m','pytest','backend/tests','-q','--disable-warnings'],args.out/'tests.log',env)
        original=args.out/'original'
        for name in SAMPLES:
            command=[sys.executable,'tools/eval/profile_eval.py','recognition_gate',name,'--out',original]
            run(command,args.out/(name+'.log'),env)
        # Compare the complete report at once, after all eight isolated workers.
        sys.path.insert(0,str(ROOT/'tools/eval'))
        from recognition_gate import regressions
        after=json.loads((original/'report.json').read_text())
        before=json.loads((args.original_baseline/'report.json').read_text())
        summary['errors']+=regressions(before,after)
        run([sys.executable,'tools/eval/profile_eval.py','library_gate',original,'--out',args.out/'library'],args.out/'library.log',env)
        lib=json.loads((args.out/'library/report.json').read_text())
        summary['clear_pins']={n:[lib[n]['pins_exact'],lib[n]['pins_gt']] for n in ('S1','S3','S4','S5')}
        summary['clear_pin_total']=sum(v[0] for v in summary['clear_pins'].values())
        if summary['clear_pin_total']<217:summary['errors'].append('Clear pin score below 217/245')
        if not args.original_only:
            baseline=json.loads((args.native_baseline/'report.json').read_text())
            combined={'cases':{},'regressions':[]}
            for identity,row in baseline['cases'].items():
                piece=args.out/'native'/identity
                command=[sys.executable,'tools/eval/profile_eval.py','native_recognition_gate','--sources',row['source'],
                         '--include',identity,'--baseline',args.native_baseline,'--out',piece]
                run(command,args.out/(identity+'.log'),env)
                report=json.loads((piece/'report.json').read_text())
                combined['cases'].update(report['cases']);combined['regressions']+=report['regressions']
            (args.out/'native/report.json').write_text(json.dumps(combined,indent=2))
            summary['errors']+=combined['regressions']
            summary['native_totals']={k:sum(r[k] for r in combined['cases'].values()) for k in
                                      ('components_found','physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}
            if summary['native_totals']['physical_pins_found']<103:summary['errors'].append('Physical pin coverage below 103')
        model=ROOT/'checkpoints/schematic-ocr/model.onnx'
        summary['protected_model_sha256']=hashlib.sha256(model.read_bytes()).hexdigest()
        summary['passed']=not summary['errors']
    except Exception as error:
        summary['errors'].append(str(error))
    (args.out/'gate.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)
    return not summary['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--original-baseline',type=Path,default=ROOT/'evidence/fullgraph-20261022/early-caption-v2-original')
    p.add_argument('--native-baseline',type=Path,default=ROOT/'evidence/fullgraph-20261022/early-caption-v2-native')
    p.add_argument('--original-only',action='store_true')
    p.add_argument('--tests',action='store_true')
    raise SystemExit(main(p.parse_args()))
