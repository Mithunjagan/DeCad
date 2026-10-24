"""Fast closure postprocessing on accepted raster observations; never fresh OCR."""
import json
from copy import deepcopy
from pathlib import Path
import sys
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tools/eval')]
from app.provisional_terminals import complete_zero_pin_components
from app.digital_vision import Token
from app.ingestion import Circuit
from app.faculty_xml import from_circuit,serialize,parse,graph_fidelity
from native_recognition_gate import measure,retained,facts
from run_eval import GT_DIR,score,norm_ref
from benchmark_paths import prediction_path
from recognition_provenance import snapshot

def read(p):return json.loads(p.read_text())

if __name__=='__main__':
    from app.pipeline_profile import configure
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'evidence/closure-20261024/cached');args=parser.parse_args()
    configure();base=ROOT/'evidence/upgrade-20261024/final-fresh';out=args.out
    out.mkdir(parents=True,exist_ok=False);original=read(base/'original/report.json');native=read(base/'native/report.json')['cases']
    errors=[];reviewed=[];frozen=snapshot()
    for name in list(original)+list(native):
        is_native=name in native;before=read(prediction_path(base/'native',name) if is_native else base/'original'/name/'recognized.json');graph=deepcopy(before)
        m=graph['image_metadata'];width,height=m['width'],m['height']
        if is_native:
            source=ROOT/native[name]['source'];record=next(json.loads(l) for l in (source/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
            image=Image.open(source/record['image']).convert('L')
            diagnostic=ROOT/'evidence/kaggle-20261022/native-caption-candidate'/name/'diagnostics.json'
            data=read(diagnostic);tokens=[Token(**t) for t in data['tokens']];ch=m.get('character_height',data['ch'])
        else:
            sample,_,variant=name.partition('-')
            if variant:
                import fitz
                with fitz.open(ROOT/'tools/eval/degraded'/f'Sample {sample[1:]}-{variant}.pdf') as doc:
                    pix=doc[0].get_pixmap(dpi=400,colorspace=fitz.csGRAY);image=Image.frombytes('L',(pix.width,pix.height),pix.samples)
            else:image=Image.open(ROOT/'samples/orcad'/f'Sample {sample[1:]}.jpg.jpeg').convert('L')
            tokens=[Token(**t) for t in read(base/'original'/name/'ocr-tokens.json')];ch=m['character_height']
        inverse=np.linalg.inv(np.vstack((m['source_affine'],[0,0,1])))
        def crop(box):
            x,y,xx,yy=box;transform=inverse.copy();transform[:2,2]+=inverse[:2,:2]@np.array([x,y])
            return np.asarray(image.transform((xx-x,yy-y),Image.Transform.AFFINE,tuple(transform[:2].reshape(-1)),resample=Image.Resampling.BICUBIC,fillcolor=255))
        complete_zero_pin_components(graph,tokens,crop,ch);image.close();graph=Circuit.from_image_graph(graph).model_dump()
        folder=out/('native' if is_native else 'original')/name;folder.mkdir(parents=True);(folder/'recognized.json').write_text(json.dumps(graph,indent=1))
        if is_native:
            truth=record['circuit'];issues=retained(truth,before,graph)
            # A caption-only zero-pin record can leave the active electrical
            # graph only when its complete candidate survives in review metadata.
            quarantined={q['component']['ref']:q['component'] for q in graph['image_metadata'].get('quarantined_components',[]) if q.get('kind')=='unanchored_zero_pin_caption'}
            old_refs={c['ref']:c for c in before['components']};new_refs={c['ref'] for c in graph['components']}
            removed=set(old_refs)-new_refs
            if removed and all(r in quarantined and quarantined[r]==old_refs[r] and not any(p[0]==r for p in facts(before)[2]) for r in removed):
                issues=[e for e in issues if e!='lost recognized reference'];reviewed.extend(name+': '+r for r in removed)
            errors.extend(name+': '+e for e in issues);native[name]={**native[name],**measure(truth,graph),'fresh_ocr':False}
        else:
            values={norm_ref(c['ref']):c['value'] for c in graph['components']};pins={f"{norm_ref(p['ref'])}.{p['pin']}":n['name'].upper() for n in graph['nets'] for p in n['nodes']}
            metric=score(read(GT_DIR/(name.partition('-')[0]+'.json')),values,pins,values)
            for field in ('wrong_pins','wrong_values','missed_parts'):
                old={x[0] if isinstance(x,(list,tuple)) else x for x in original[name][field]}
                new={x[0] if isinstance(x,(list,tuple)) else x for x in metric[field]}
                errors.extend(name+': lost correct '+field+' '+p for p in new-old)
            original[name]={**original[name],**metric,'fresh_ocr':False}
        fidelity=graph_fidelity(graph,parse(serialize(from_circuit(graph,board=name))))
        print(name,'XML',fidelity['passed'],'unresolved',fidelity.get('missing_components'),flush=True)
    (out/'original/report.json').write_text(json.dumps(original,indent=2));(out/'native/report.json').write_text(json.dumps({'cases':native,'regressions':errors},indent=2))
    gate={'passed':not errors,'fresh_ocr':False,'scope':'Cached raster postprocessing; not a fresh eighteen-case OCR run','source_snapshot':frozen,
        'sample_scope':list(original),'errors':errors,'caption_records_preserved_in_quarantine':reviewed,
        'clear_pin_total':sum(original[n]['pins_exact'] for n in ('S1','S3','S4','S5')),
        'native_totals':{k:sum(r[k] for r in native.values()) for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}}
    assert snapshot()==frozen
    (out/'gate.json').write_text(json.dumps(gate,indent=2));print(json.dumps({k:v for k,v in gate.items() if k!='source_snapshot'},indent=2))
    raise SystemExit(bool(errors))
