"""Serialized, process-isolated actual OCR gates. Never replay model outputs.

Run with the CUDA Python; --tests uses KiCad's native Python for API/CLI checks.
Every subprocess log and raw prediction is retained in the selected phase folder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SAMPLES=('S1','S2','S3','S4','S5','S4-scan300','S4-scan200','S4-blur300')


def run(command,log,environment,allow_failure=False):
    print('Running',log.name,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(x) for x in command],cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode and not allow_failure:
        raise RuntimeError(f'{log.name} failed ({result.returncode}); see {log}')
    return result.returncode


def transient_gpu_failure(code,log,report=None):
    if not code or (report and report.get('regressions')):return False
    message=log.read_text(encoding='utf-8',errors='replace')
    return code in (3221226505,-1073740791) or any(word in message for word in
        ('CUDNN_FE failure','CUDNN_STATUS','CUDA failure','CUDA_ERROR'))


def native_case(identity,row,args,env):
    """Retry a crashed GPU worker once, preserving both actual attempts."""
    attempts=[];report=None
    for attempt in (1,2):
        piece=args.out/'native-attempts'/identity/f'attempt-{attempt}'
        log=args.out/f'{identity}.attempt-{attempt}.log'
        command=[sys.executable,'tools/eval/profile_eval.py','native_recognition_gate','--sources',row['source'],
                 '--include',identity,'--baseline',args.native_baseline,'--out',piece]
        code=run(command,log,env,allow_failure=True)
        report=json.loads((piece/'report.json').read_text()) if (piece/'report.json').exists() else None
        attempts.append({'attempt':attempt,'exit_code':code,'log':str(log),'output':str(piece)})
        if attempt==1 and transient_gpu_failure(code,log,report):
            print('Retrying crashed GPU worker in a fresh process:',identity,flush=True)
            continue
        if report is not None:
            canonical=args.out/'native'/identity
            canonical.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(piece,canonical)
        return report,code,attempts


def main(args):
    args.out.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONPATH':str(ROOT/'backend'),
         'KICAD_CLI':'D:/KICAD/bin/kicad-cli.exe','KICAD_SYMBOL_DIR':'D:/KICAD/share/kicad/symbols',
         'KICAD_FOOTPRINT_DIR':'D:/KICAD/share/kicad/footprints','KICAD_PYTHON':'D:/KICAD/bin/python.exe'}
    summary={'passed':False,'fresh_ocr':True,'process_isolated':True,'errors':[],'worker_attempts':{},'sample_scope':list(args.samples)}
    try:
        from recognition_provenance import snapshot
        frozen=snapshot()
        summary['source_snapshot']=frozen
        if args.tests:
            run([ROOT/'backend/.venv/Scripts/python.exe','-m','pytest','backend/tests','-q','--disable-warnings'],args.out/'tests.log',env)
        original=args.out/'original'
        before=json.loads((args.original_baseline/'report.json').read_text())
        summary['baseline_sources']={name:str(args.original_baseline) for name in args.samples}
        if args.original_overlay:
            overlay=json.loads((args.original_overlay/'report.json').read_text())
            before.update(overlay)
            summary['baseline_sources'].update({name:str(args.original_overlay) for name in args.samples if name in overlay})
        before={name:before[name] for name in args.samples}
        sys.path.insert(0,str(ROOT/'tools/eval'))
        from recognition_gate import regressions
        for name in args.samples:
            command=[sys.executable,'tools/eval/profile_eval.py','recognition_gate',name,'--out',original]
            attempts=[]
            for attempt in (1,2):
                log=args.out/(name+f'.attempt-{attempt}.log')
                code=run(command,log,env,allow_failure=True)
                attempts.append({'attempt':attempt,'exit_code':code,'log':str(log)})
                if attempt==1 and transient_gpu_failure(code,log):
                    saved=args.out/'original-attempts'/name/'attempt-1'
                    if (original/name).exists():shutil.copytree(original/name,saved)
                    continue
                if code:raise RuntimeError(f'{log.name} failed ({code}); see {log}')
                break
            summary['worker_attempts'][name]=attempts
            observed=json.loads((original/'report.json').read_text())[name]
            errors=regressions({name:before[name]},{name:observed})
            for reader in ('detector','classifier','reader','schematic_reader'):
                if 'CUDAExecutionProvider' not in observed['providers'].get(reader,[]):
                    errors.append(f'{name}: {reader} did not confirm CUDA')
            if errors:raise RuntimeError('; '.join(errors))
        # Compare the complete report at once, after all eight isolated workers.
        sys.path.insert(0,str(ROOT/'tools/eval'))
        from recognition_gate import regressions
        after=json.loads((original/'report.json').read_text())
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
                report,code,attempts=native_case(identity,row,args,env)
                summary['worker_attempts'][identity]=attempts
                (args.out/'worker-attempts.json').write_text(json.dumps(summary['worker_attempts'],indent=2))
                if report is None:
                    combined['regressions'].append(f'{identity}: worker failed ({code}); see its log')
                    continue
                combined['cases'].update(report['cases']);combined['regressions']+=report['regressions']
                for case,record in report['cases'].items():
                    providers=record.get('providers',{})
                    if not providers or any('CUDAExecutionProvider' not in value for value in providers.values()):
                        combined['regressions'].append(f'{case}: loaded OCR readers did not confirm CUDA')
                if code and not report['regressions']:
                    combined['regressions'].append(f'{identity}: worker failed ({code}); see its log')
            (args.out/'native/report.json').write_text(json.dumps(combined,indent=2))
            summary['errors']+=combined['regressions']
            if len(combined['cases'])!=len(baseline['cases']):summary['errors'].append('Missing native design results')
            summary['native_totals']={k:sum(r[k] for r in combined['cases'].values()) for k in
                                      ('components_found','physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}
            if summary['native_totals']['physical_pins_found']<103:summary['errors'].append('Physical pin coverage below 103')
        model=ROOT/'checkpoints/schematic-ocr/model.onnx'
        if snapshot()!=frozen:summary['errors'].append('Recognizer source changed during the complete gate')
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
    p.add_argument('--original-overlay',type=Path,help='Explicit per-case newer accepted baseline; other cases retain the primary baseline')
    p.add_argument('--original-only',action='store_true')
    p.add_argument('--samples',nargs='+',choices=SAMPLES,default=SAMPLES,help='Use the four clear cases for a quick fresh iteration before the full gate')
    p.add_argument('--tests',action='store_true')
    from runtime_power import system_awake
    with system_awake():
        raise SystemExit(main(p.parse_args()))
