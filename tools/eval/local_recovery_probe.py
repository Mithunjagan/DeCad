"""Fast cached-observation probe. Diagnostic scores never replace a fresh OCR gate."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.local_recovery import recover_locally
from app import orcad_capture as oc
from app.erc import erc_self_heal
from run_eval import GT_DIR,norm_ref,score


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--samples',nargs='+',default=['S1','S3','S4','S5'])
    parser.add_argument('--pixels',action='store_true',help='also read uncovered local body-edge crops with CUDA OCR')
    parser.add_argument('--max-reads',type=int,default=64)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    def unavailable(*args,**kwargs):raise RuntimeError('Frozen library cache miss')
    oc._run=unavailable
    report={'fresh_ocr':False,'scope':'cached local recovery diagnostic','cases':{}}
    previous=json.loads((args.phase/'library/report.json').read_text())
    started=time.monotonic()
    if args.pixels:
        from app.pipeline_profile import configure
        configure()
    for name in args.samples:
        source=json.loads((args.phase/'original'/name/'recognized.json').read_text())
        graph=recover_locally(source)
        if args.pixels:
            import numpy as np
            from PIL import Image
            from app.terminal_recovery import recover_terminals
            reads=json.loads((args.phase/'original'/name/'pin-debug.json').read_text())
            graph['image_metadata']['terminal_observations']=[{'ref':r[0],'pin':r[3]} for r in reads]
            affine=np.vstack((graph['image_metadata']['source_affine'],[0,0,1]))
            inverse=np.linalg.inv(affine)
            if '-' in name:
                import fitz
                sample,_,variant=name.partition('-')
                with fitz.open(ROOT/'tools/eval/degraded'/f'Sample {sample[1:]}-{variant}.pdf') as document:
                    pix=document[0].get_pixmap(dpi=400,colorspace=fitz.csGRAY)
                    loaded=Image.frombytes('L',(pix.width,pix.height),pix.samples)
            else:loaded=Image.open(ROOT/'samples/orcad'/f'Sample {name[1:]}.jpg.jpeg')
            with loaded as image:
                image=image.convert('L')
                def crop(bounds):
                    x,y,xx,yy=bounds
                    mapping=inverse.copy();mapping[:2,2]+=inverse[:2,:2]@np.array([x,y])
                    return np.asarray(image.transform((xx-x,yy-y),Image.Transform.AFFINE,
                        tuple(mapping[:2].reshape(-1)),resample=Image.Resampling.BICUBIC,fillcolor=255))
                actions=recover_terminals(graph,crop,max_reads=args.max_reads)
                graph['image_metadata']['local_recovery_actions'].extend(actions)
        graph=erc_self_heal(graph)
        checked,_=oc.check(graph,ROOT/'backend/.state')
        values={norm_ref(c['ref']):c['value'] for c in checked['components']}
        pins={f"{norm_ref(p['ref'])}.{p['pin']}":n['name'].upper() for n in checked['nets'] for p in n['nodes']}
        truth=json.loads((GT_DIR/(name.partition('-')[0]+'.json')).read_text())
        measured=score(truth,values,pins,values)
        old_wrong={p[0] for p in previous[name]['wrong_pins']}
        lost=[p for p in measured['wrong_pins'] if p[0] not in old_wrong]
        report['cases'][name]={'before':previous[name]['pins_exact'],'after':measured['pins_exact'],
                                'lost_correct':lost,'wrong_pins':measured['wrong_pins'],
                                'actions':graph['image_metadata'].get('local_recovery_actions',[])}
        folder=args.out/name;folder.mkdir()
        (folder/'recognized.json').write_text(json.dumps(graph,indent=1))
        print(name,json.dumps(report['cases'][name]),flush=True)
    report['seconds']=time.monotonic()-started
    report['clear_total']=sum(r['after'] for n,r in report['cases'].items() if n in ('S1','S3','S4','S5'))
    (args.out/'report.json').write_text(json.dumps(report,indent=2))
    print('Diagnostic total:',report['clear_total'],'seconds:',report['seconds'])
