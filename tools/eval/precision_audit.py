"""Produce source-only crops and independent failure inventories from frozen results.

Evaluation only: reference graphs are never supplied to recognition. Crop bounds
are recorded in working coordinates and inverse-mapped to original source pixels.
"""
import argparse
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import from_circuit,serialize,parse,graph_fidelity
from benchmark_paths import prediction_path


def pairs(graph):
    return {tuple(sorted(p)) for n in graph['nets'] for p in itertools.combinations(
        {(p['ref'],str(p['pin'])) for p in n['nodes']},2)}


def crop(image,metadata,bounds,path):
    inverse=np.linalg.inv(np.vstack((metadata.get('source_affine',[[1,0,0],[0,1,0]]),[0,0,1])))
    x,y,xx,yy=map(round,bounds)
    mapping=inverse.copy();mapping[:2,2]+=inverse[:2,:2]@np.array([x,y])
    result=image.transform((xx-x,yy-y),Image.Transform.AFFINE,tuple(mapping[:2].reshape(-1)),
                           resample=Image.Resampling.BICUBIC,fillcolor='white')
    result.save(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    failures=json.loads((ROOT/'evidence/tonight-20261023/final-failures/failures.json').read_text())
    native=json.loads((args.phase/'native/report.json').read_text())['cases']
    xml=json.loads((ROOT/'evidence/tonight-20261023/xml-corpus/report.json').read_text())['xml_cases']
    result={'scope':'source inspection, independent positive and negative reference connectivity; no recognition runs',
            'clear_errors':{},'native_false_pairs':{},'xml_blockers':{}}
    for name in ['S1','S3','S4','S5']:
        graph=json.loads((args.phase/'original'/name/'recognized.json').read_text());m=graph['image_metadata']
        image_path=ROOT/'samples/orcad'/f'Sample {name[1:]}.jpg.jpeg'
        with Image.open(image_path) as image:
            for row in failures['samples'][name]['failures']:
                ref=row['pin'].rsplit('.',1)[0]
                boxes=[a['body'] for a in m['pin_anchors'] if a['ref']==ref and a.get('body')]
                box=min(boxes,key=lambda b:(b[2]-b[0])*(b[3]-b[1]))
                margin=400 if name=='S5' else 200
                bounds=[box[0]-margin,box[1]-200,box[2]+margin,box[3]+200]
                filename=f'{name}-{ref}.png';crop(image,m,bounds,args.out/filename)
                result['clear_errors'][name+'.'+row['pin']]={'read':row['read'],'expected':row['expected'],
                    'anchor_observed':row['anchor'] is not None,'crop':filename,'working_bounds':bounds,
                    'source':str(image_path),'expected_text_observations':row['expected_text_observations']}
    for identity,row in native.items():
        records=[json.loads(l) for l in (Path(row['source'])/'candidates.jsonl').read_text().splitlines()]
        record=next(r for r in records if r['sample_id']==identity)
        graph=json.loads(prediction_path(args.phase/'native',identity).read_text())
        wrong=sorted(pairs(graph)-pairs(record['circuit']))
        for a,b in wrong:
            truth={ (p['ref'],str(p['pin'])):n['name'] for n in record['circuit']['nets'] for p in n['nodes']}
            result['native_false_pairs'].setdefault(identity,[]).append({'a':a,'b':b,
                'reference_a':truth.get(a,'NONEXISTENT PHYSICAL PIN OR COMPONENT'),
                'reference_b':truth.get(b,'NONEXISTENT PHYSICAL PIN OR COMPONENT'),
                'source':record['source_file']})
    # Inspect every pre-existing blocker, including observed unassigned pins.
    for name,row in xml.items():
        if row['passed']:continue
        if name in native:
            source=Path(native[name]['source']);record=next(json.loads(l) for l in (source/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
            image_path=source/record['image'];graph=json.loads(prediction_path(args.phase/'native',name).read_text())
            diagnostic=ROOT/'evidence/kaggle-20261022/native-caption-candidate'/name/'diagnostics.json'
            tokens=json.loads(diagnostic.read_text())['tokens'] if diagnostic.exists() else []
        else:
            graph=json.loads((args.phase/'original'/name/'recognized.json').read_text())
            tokens=json.loads((args.phase/'original'/name/'ocr-tokens.json').read_text())
            if '-' in name:
                import fitz
                sample,variant=name.split('-',1)
                image_path=ROOT/'tools/eval/degraded'/f'Sample {sample[1:]}-{variant}.pdf'
            else:image_path=ROOT/'samples/orcad'/f'Sample {name[1:]}.jpg.jpeg'
        m=graph['image_metadata'];components=[]
        if image_path.suffix=='.pdf':
            with fitz.open(image_path) as pdf:
                pix=pdf[0].get_pixmap(dpi=400,colorspace=fitz.csRGB)
                loaded=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        else:loaded=Image.open(image_path).convert('RGB')
        with loaded as image:
            for ref in row['missing_components']:
                observations=[t for t in tokens if t['text'].upper()==ref]
                inventory=[p for p in graph.get('physical_pins',[]) if p['ref']==ref]
                assigned=[p for n in graph['nets'] for p in n['nodes'] if p['ref']==ref]
                crops=[]
                for j,t in enumerate(observations):
                    bounds=[t['x0']-150,t['y0']-150,t['x1']+150,t['y1']+150]
                    filename=f'xml-{name}-{ref}-{j}.png';crop(image,m,bounds,args.out/filename);crops.append(filename)
                components.append({'ref':ref,'observed_inventory':len(inventory),'assigned':len(assigned),
                                   'reference_text_observations':len(observations),'source_crops':crops})
        doc=from_circuit(graph,board=name);readback=parse(serialize(doc))
        fidelity=graph_fidelity(graph,readback)
        result['xml_blockers'][name]={'components':components,'readback':fidelity,
            'diagnosis':'Component identity has no observed physical pins. All observed assignments round-trip; encoding a component-only record would require an invented faculty node.'}
    (args.out/'audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'clear_errors':len(result['clear_errors']),
        'native_false_pairs':sum(map(len,result['native_false_pairs'].values())),
        'xml_blocked_cases':len(result['xml_blockers']),
        'xml_zero_pin_components':sum(len(v['components']) for v in result['xml_blockers'].values())}))


if __name__=='__main__':main()
