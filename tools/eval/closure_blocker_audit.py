"""Bounded source crops for zero-pin records; no truth enters recognition."""
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tools/eval')]
from benchmark_paths import prediction_path

if __name__=='__main__':
    base=ROOT/'evidence/upgrade-20261024/final-fresh';out=ROOT/'evidence/closure-20261024/blocker-audit';out.mkdir(parents=True,exist_ok=True)
    xml=json.loads((ROOT/'evidence/upgrade-20261024/xml-corpus/report.json').read_text())
    native=json.loads((base/'native/report.json').read_text())['cases'];rows=[];crops=[]
    for name,row in xml['xml_cases'].items():
        if row['passed']:continue
        path=prediction_path(base/'native',name) if name in native else base/'original'/name/'recognized.json'
        graph=json.loads(path.read_text());m=graph['image_metadata'];width=m['width']
        if name in native:
            source=ROOT/native[name]['source'];record=next(json.loads(l) for l in (source/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
            image=Image.open(source/record['image']).convert('L')
        else:
            sample,_,variant=name.partition('-')
            if variant:
                import fitz
                with fitz.open(ROOT/'tools/eval/degraded'/f'Sample {sample[1:]}-{variant}.pdf') as doc:
                    pix=doc[0].get_pixmap(dpi=400,colorspace=fitz.csGRAY);image=Image.frombytes('L',(pix.width,pix.height),pix.samples)
            else:image=Image.open(ROOT/'samples/orcad'/f'Sample {sample[1:]}.jpg.jpeg').convert('L')
        inverse=np.linalg.inv(np.vstack((m['source_affine'],[0,0,1])))
        for ref in row['missing_components']:
            c=next(c for c in graph['components'] if c['ref']==ref);x=c.get('x',.5)*width;y=c.get('y',.5)*width
            if name in native:
                diagnostic=ROOT/'evidence/kaggle-20261022/native-caption-candidate'/name/'diagnostics.json'
                tokens=json.loads(diagnostic.read_text())['tokens'] if diagnostic.exists() else []
                matching=[t for t in tokens if t['text'].upper()==ref]
                if matching:
                    t=max(matching,key=lambda t:t['conf']);x=(t['x0']+t['x1'])/2;y=(t['y0']+t['y1'])/2
            box=(max(0,round(x)-450),max(0,round(y)-280),min(width,round(x)+450),min(m['height'],round(y)+280))
            transform=inverse.copy();transform[:2,2]+=inverse[:2,:2]@np.array(box[:2])
            crop=image.transform((box[2]-box[0],box[3]-box[1]),Image.Transform.AFFINE,tuple(transform[:2].reshape(-1)),resample=Image.Resampling.BICUBIC,fillcolor=255)
            file=out/f'{name}-{ref}.png';crop.save(file)
            tile=Image.new('RGB',(600,410),'white');tile.paste(crop.resize((600,375)),(0,35));ImageDraw.Draw(tile).text((5,8),name+' / '+ref+' / '+c['value'],fill='black');crops.append(tile)
            rows.append({'case':name,'component':c,'working_bounds':box,'crop':str(file)})
        image.close()
    for i in range(0,len(crops),6):
        sheet=Image.new('RGB',(1200,1230),'white')
        for j,tile in enumerate(crops[i:i+6]):sheet.paste(tile,((j%2)*600,(j//2)*410))
        sheet.save(out/f'contact-{i//6+1}.png')
    (out/'report.json').write_text(json.dumps(rows,indent=2));print('Source crops',len(rows))
