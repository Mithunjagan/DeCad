"""Inspect benchmark failures using saved observations; never supplies GT to recognition."""
import argparse
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def pairs(graph):
    return {tuple(sorted(pair)) for net in graph['nets'] for pair in itertools.combinations(
        sorted({(p['ref'],str(p['pin'])) for p in net['nodes']}),2)}


def inspect(phase):
    library=json.loads((phase/'library/report.json').read_text())
    result={'scope':'cached diagnostic only; not a fresh recognition gate','samples':{},'native':{}}
    lines=['# Saved-observation failure diagnostic','',result['scope'],'']
    for name in ('S1','S3','S4','S5','S4-scan300'):
        graph=json.loads((phase/'original'/name/'recognized.json').read_text())
        meta=graph.get('image_metadata',{})
        tokens=json.loads((phase/'original'/name/'ocr-tokens.json').read_text())
        anchors=meta.get('pin_anchors',[])
        rows=[]
        lines += [f'## {name}: {library[name]["pins_exact"]}/{library[name]["pins_gt"]}','',
                  '| Pin | Read net | Expected | Anchor / trace | Local observed labels |',
                  '|---|---|---|---|---|']
        for identity,read,expected in library[name]['wrong_pins']:
            ref,pin=identity.rsplit('.',1)
            anchor=next((a for a in anchors if a['ref']==ref and a['pin']==pin),None)
            siblings=[a for a in anchors if a['ref']==ref]
            matching=[t for t in tokens if t['text'].strip().upper()==expected.upper()]
            observed=[]
            if anchor:
                observed=sorted(meta.get('external_labels',[]),key=lambda t:math.hypot(
                    (t['bbox'][0]+t['bbox'][2])/2-anchor['x'],
                    (t['bbox'][1]+t['bbox'][3])/2-anchor['y']))[:4]
            row={'pin':identity,'read':read,'expected':expected,'anchor':anchor,
                 'observed_component_anchors':siblings,'expected_text_observations':matching,
                 'nearest_observed_labels':observed}
            rows.append(row)
            where='missing physical pin' if anchor is None else f"({anchor['x']:.1f},{anchor['y']:.1f}), root={anchor.get('physical_net')}"
            local=', '.join(t['text'] for t in observed)
            lines.append(f'| {identity} | {read or "missing"} | {expected} | {where} | {local} |')
        result['samples'][name]={'failures':rows,'trace_applied':meta.get('applied'),
                                'anchors':len(anchors),'anchored':sum(a.get('physical_net') is not None for a in anchors)}
        lines.append('')
    native=json.loads((phase/'native/report.json').read_text())['cases']
    for identity,row in native.items():
        records=[json.loads(line) for line in (Path(row['source'])/'candidates.jsonl').read_text().splitlines()]
        record=next(r for r in records if r['sample_id']==identity)
        graph=json.loads((phase/'native'/identity/identity/'recognized.json').read_text())
        truth=pairs(record['circuit']);wrong=sorted(pairs(graph)-truth)
        result['native'][identity]={'source':record.get('source_file'),'incorrect_pairs':wrong}
        lines += [f'## {identity}: {record.get("source_file",identity)}','']
        lines += [f'- {a[0]}.{a[1]} -- {b[0]}.{b[1]}' for a,b in wrong] or ['No incorrect pairs.']
        lines.append('')
    result['clear_failure_count']=sum(len(result['samples'][n]['failures']) for n in ('S1','S3','S4','S5'))
    result['native_incorrect_pair_count']=sum(len(r['incorrect_pairs']) for r in result['native'].values())
    return result,'\n'.join(lines)+'\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    data,markdown=inspect(args.phase)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'failures.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (args.out/'failures.md').write_text(markdown,encoding='utf-8')
    print(markdown)
