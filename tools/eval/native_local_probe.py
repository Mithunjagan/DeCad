"""Diagnostic local-rule test against saved native observations and actual source crops."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.local_recovery import recover_locally
from app.erc import erc_self_heal
from native_recognition_gate import measure,retained
from benchmark_paths import prediction_path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--pixels',action='store_true')
    parser.add_argument('--include',nargs='+')
    parser.add_argument('--pairs',action='store_true')
    args=parser.parse_args()
    from app.pipeline_profile import configure
    configure()
    args.out.mkdir(parents=True,exist_ok=False)
    baseline=json.loads((args.baseline/'report.json').read_text())['cases']
    report={'fresh_ocr':False,'scope':'cached trace plus fresh bounded source crops; full OCR gate still required',
            'limitation':'Legacy native caches omit duplicate terminal observations; fresh full gate must validate those paths.',
            'cases':{},'regressions':[]}
    started=time.monotonic()
    for identity,row in baseline.items():
        if args.include and identity not in args.include:continue
        records=[json.loads(l) for l in (Path(row['source'])/'candidates.jsonl').read_text().splitlines()]
        record=next(r for r in records if r['sample_id']==identity)
        before=json.loads(prediction_path(args.baseline,identity).read_text())
        graph=recover_locally(before)
        if args.pixels or args.pairs:
            from PIL import Image
            import numpy as np
            from app.terminal_recovery import recover_terminals
            inverse=np.linalg.inv(np.vstack((graph.get('image_metadata',{}).get('source_affine',[[1,0,0],[0,1,0]]),[0,0,1])))
            with Image.open(Path(row['source'])/record['image']) as image:
                image=image.convert('L')
                def crop(bounds):
                    x,y,xx,yy=bounds;mapping=inverse.copy();mapping[:2,2]+=inverse[:2,:2]@np.array([x,y])
                    return np.asarray(image.transform((xx-x,yy-y),Image.Transform.AFFINE,tuple(mapping[:2].reshape(-1)),
                        resample=Image.Resampling.BICUBIC,fillcolor=255))
                if args.pixels:recover_terminals(graph,crop,max_reads=160)
                if args.pairs:
                    from app.observed_terminal_pairs import recover_observed_pairs
                    from app.digital_vision import Token
                    diagnostic=ROOT/'evidence/kaggle-20261022/native-caption-candidate'/identity/'diagnostics.json'
                    tokens=json.loads(diagnostic.read_text()).get('tokens',[]) if diagnostic.exists() else []
                    recover_observed_pairs(graph,[Token(**t) for t in tokens],crop)
        graph=erc_self_heal(graph)
        metrics=measure(record['circuit'],graph)
        errors=retained(record['circuit'],before,graph)
        report['cases'][identity]={**metrics,'before':{k:row[k] for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')},'errors':errors}
        report['regressions'] += [identity+': '+e for e in errors]
        folder=args.out/identity;folder.mkdir()
        (folder/'recognized.json').write_text(json.dumps(graph,indent=1))
        print(identity,{k:metrics[k] for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')},errors,flush=True)
    report['seconds']=time.monotonic()-started
    (args.out/'report.json').write_text(json.dumps(report,indent=2))
    print('Diagnostic regressions:',report['regressions'],'seconds:',report['seconds'],flush=True)
