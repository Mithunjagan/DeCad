"""Fast cached-source diagnostic. Never represents a fresh OCR acceptance gate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.digital_vision import Token
from app.implicit_terminals import attach_passives,quarantine_unverified,reread_reference
from app.faculty_xml import from_circuit,serialize,parse,graph_fidelity
from app.ingestion import Circuit
from benchmark_paths import prediction_path
from native_recognition_gate import measure,retained
from run_eval import GT_DIR,score,norm_ref


def read(path):return json.loads(path.read_text())


def run(args):
    args.out.mkdir(parents=True,exist_ok=False)
    baseline=args.baseline
    old_native=read(baseline/'native/report.json')['cases'];originals=read(baseline/'original/report.json')
    report={'fresh_ocr':False,'scope':'cached graphs plus bounded raster geometry; no OCR', 'cases':{},'regressions':[]}
    for name in list(originals)+list(old_native):
        if args.include and name not in args.include:continue
        native=name in old_native
        before=read(prediction_path(baseline/'native',name) if native else baseline/'original'/name/'recognized.json')
        graph=deepcopy(before);m=graph.get('image_metadata',{})
        if native:
            source=Path(old_native[name]['source'])
            record=next(json.loads(l) for l in (source/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
            image=source/record['image'];truth=record['circuit']
            diagnostic=ROOT/'evidence/kaggle-20261022/native-caption-candidate'/name/'diagnostics.json'
            data=read(diagnostic) if diagnostic.exists() else {}
            raw_tokens=data.get('tokens',[]);ch=data.get('ch',40.)
        else:
            sample,_,variant=name.partition('-')
            image=ROOT/'samples/orcad'/f'Sample {sample[1:]}.jpg.jpeg'
            if variant:image=ROOT/'tools/eval/degraded'/f'Sample {sample[1:]}-{variant}.pdf'
            raw_tokens=read(ROOT/'evidence/tonight-20261023/final-fresh/original'/name/'ocr-tokens.json')
            ch=float(np.median([t['x1']-t['x0'] if t['vertical'] else t['y1']-t['y0'] for t in raw_tokens]))
            truth=read(GT_DIR/(sample+'.json'))
        tokens=[Token(**t) for t in raw_tokens]
        if tokens:
            if image.suffix=='.pdf':
                import fitz
                with fitz.open(image) as doc:
                    pix=doc[0].get_pixmap(dpi=400,colorspace=fitz.csGRAY);loaded=Image.frombytes('L',(pix.width,pix.height),pix.samples)
            else:loaded=Image.open(image).convert('L')
            inverse=np.linalg.inv(np.vstack((m['source_affine'],[0,0,1])))
            working=loaded.transform((m['width'],m['height']),Image.Transform.AFFINE,tuple(inverse[:2].reshape(-1)),resample=Image.Resampling.BICUBIC,fillcolor=255)
            if args.read_aliases:
                from app.digital_vision import Seg
                from app.ic_caption import visible_pin_ends,inside
                wires=[Seg(*w['p0'],*w['p1'],2,abs(w['p1'][0]-w['p0'][0])>=abs(w['p1'][1]-w['p0'][1])) for w in m.get('wires',[])]
                m['verified_component_refs']=[c['ref'] for c in graph['components'] if c.get('x') is not None and c['ref'].startswith(('U','IC'))
                    and any(inside(box,c['x']*m['width'],c['y']*m['width']) and len(visible_pin_ends(box,wires,.55*ch))>=3 for box in m.get('component_bodies',[]))]
                graph=quarantine_unverified(graph,tokens,lambda t:reread_reference(np.asarray(working),t))
            graph=attach_passives(graph,np.asarray(working),tokens,ch)
            loaded.close();working.close()
        graph=Circuit.from_image_graph(graph).model_dump()
        def xml(g):
            return graph_fidelity(g,parse(serialize(from_circuit(g,board=name))))
        old_xml=xml(before);new_xml=xml(graph)
        if native:
            metric=measure(truth,graph);errors=retained(truth,before,graph)
            counts={k:metric[k] for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}
        else:
            def measured(g):
                values={norm_ref(c['ref']):c['value'] for c in g['components']}
                pins={f"{norm_ref(p['ref'])}.{p['pin']}":n['name'].upper() for n in g['nets'] for p in n['nodes']}
                return score(truth,values,pins,values)
            old_score=measured(before);metric=measured(graph)
            old_wrong={p[0] for p in old_score['wrong_pins']}
            errors=['lost correct '+p[0] for p in metric['wrong_pins'] if p[0] not in old_wrong]
            counts={'pins_exact':metric['pins_exact'],'before':old_score['pins_exact']}
        if old_xml['passed'] and not new_xml['passed']:errors.append('lost passing XML export')
        report['regressions'] += [name+': '+e for e in errors]
        report['cases'][name]={'metrics':counts,'errors':errors,'xml_before':old_xml,'xml_after':new_xml,
            'actions':graph.get('image_metadata',{}).get('local_recovery_actions',[]),'tokens_available':bool(tokens)}
        folder=args.out/name;folder.mkdir();(folder/'recognized.json').write_text(json.dumps(graph,indent=1))
        print(name,counts,'XML',old_xml['passed'],'->',new_xml['passed'],errors,flush=True)
        (args.out/'report.json').write_text(json.dumps(report,indent=2))
    return bool(report['regressions'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--include',nargs='+')
    p.add_argument('--baseline',type=Path,default=ROOT/'evidence/precision-20261023/accepted-fresh')
    p.add_argument('--read-aliases',action='store_true',help='Bounded fresh OCR of zero-pin reference crops only')
    from app.pipeline_profile import configure
    configure()
    raise SystemExit(run(p.parse_args()))
