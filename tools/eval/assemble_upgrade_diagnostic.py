"""Assemble explicitly cached diagnostics; final acceptance requires sprint_gate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from benchmark_paths import prediction_path
from native_recognition_gate import measure,retained
from run_eval import GT_DIR,score,norm_ref


def read(p):return json.loads(p.read_text())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--patch',type=Path,nargs='+',required=True,help='Later folders take precedence; absent cases retain the accepted baseline')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    baseline=ROOT/'evidence/precision-20261023/accepted-fresh';original=read(baseline/'original/report.json');native=read(baseline/'native/report.json')['cases']
    errors=[];provenance={}
    for name in list(original)+list(native):
        is_native=name in native
        source=prediction_path(baseline/'native',name) if is_native else baseline/'original'/name/'recognized.json'
        before=read(source)
        for patch in args.patch:
            try:source=prediction_path(patch,name)
            except FileNotFoundError:pass
        graph=read(source);provenance[name]=str(source)
        folder=args.out/('native' if is_native else 'original')/name;folder.mkdir(parents=True)
        (folder/'recognized.json').write_text(json.dumps(graph,indent=1))
        if is_native:
            row=native[name];truth=next(json.loads(l)['circuit'] for l in (Path(row['source'])/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
            errors += [name+': '+e for e in retained(truth,before,graph)]
            native[name]={**row,**measure(truth,graph),'fresh_ocr':False,'diagnostic_input':str(source)}
        else:
            values={norm_ref(c['ref']):c['value'] for c in graph['components']}
            pins={f"{norm_ref(p['ref'])}.{p['pin']}":n['name'].upper() for n in graph['nets'] for p in n['nodes']}
            metric=score(read(GT_DIR/(name.partition('-')[0]+'.json')),values,pins,values)
            old_wrong={a[0] for a in original[name]['wrong_pins']}
            errors += [name+': lost correct '+a[0] for a in metric['wrong_pins'] if a[0] not in old_wrong]
            original[name]={**original[name],**metric,'fresh_ocr':False,'diagnostic_input':str(source)}
    (args.out/'original/report.json').write_text(json.dumps(original,indent=2))
    (args.out/'native/report.json').write_text(json.dumps({'cases':native,'regressions':errors},indent=2))
    gate={'passed':not errors,'fresh_ocr':False,'scope':'Cached diagnostic assembly, not fresh full recognition acceptance',
          'sample_scope':list(original),'errors':errors,'inputs':provenance,
          'clear_pin_total':sum(original[n]['pins_exact'] for n in ('S1','S3','S4','S5')),
          'native_totals':{k:sum(r[k] for r in native.values()) for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}}
    (args.out/'gate.json').write_text(json.dumps(gate,indent=2));print(json.dumps(gate,indent=2))
    raise SystemExit(bool(errors))
