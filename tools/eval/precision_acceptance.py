"""Accept the passive guard with explicit cached/fresh evidence boundaries.

The broader connector experiment was rejected and restored. Only this guard
differs from the accepted recognizer. Replay its exact branch on all 18 saved
graphs, prove it is inert on 17, and require fresh current-code Wio and ESP32
workers. Cached outputs are never labeled fresh recognition.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.local_recovery import quarantine_passive_pin_conflicts
from benchmark_paths import prediction_path
from native_recognition_gate import measure,retained,facts
from recognition_provenance import snapshot


def read(path):return json.loads(path.read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--wio',type=Path,required=True)
    p.add_argument('--esp32',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();frozen=snapshot()
    originals=read(a.baseline/'original/report.json');native=read(a.baseline/'native/report.json')['cases']
    previous=originals['S1']['recognizer_support_files']
    changed=[k for k in previous.keys()|frozen.keys() if previous.get(k)!=frozen.get(k)]
    assert changed==[str((ROOT/'backend/app/local_recovery.py').resolve())],changed
    fresh={}
    for folder in [a.wio,a.esp32]:
        report=read(folder/'report.json');assert not report['regressions'],report['regressions']
        for identity,row in report['cases'].items():
            assert row['recognizer_support_files']==frozen and row['failure'] is None
            assert row['original_native_source_hash_verified']
            assert row['protected_model_sha256']==native[identity]['protected_model_sha256']
            assert all('CUDAExecutionProvider' in values for values in row['providers'].values())
            fresh[identity]=(folder,row)
    assert set(fresh)=={'native-a39a7a1fc84f921b27fd','native-c4d88e79bc63688e0e7c'}
    paths={n:a.baseline/'original'/n/'recognized.json' for n in originals}
    paths.update({n:prediction_path(a.baseline/'native',n) for n in native})
    graphs={};branches={};changes={};cases={}
    for name,path in paths.items():
        before=read(path);graph=deepcopy(before)
        actions=quarantine_passive_pin_conflicts(graph,graph['image_metadata'])
        branches[name]=[(r['ref'],r['pin']) for r in actions]
        if name!='native-a39a7a1fc84f921b27fd':assert graph==before,name+' unexpectedly changed'
        else:assert set(map(tuple,branches[name]))=={('R1','4'),('R1','55')}
        if name in fresh:
            folder,row=fresh[name];observed=read(prediction_path(folder,name))
            assert facts(graph)==facts(observed),name+' fresh graph differs from predicted exact guard delta'
            graph=observed
        graphs[name]=graph
        if name not in native:continue
        row=native[name];source=Path(row['source'])
        truth=next(json.loads(line)['circuit'] for line in (source/'candidates.jsonl').read_text().splitlines()
                   if json.loads(line)['sample_id']==name)
        errors=retained(truth,before,graph);assert not errors,(name,errors)
        def assignments(g):return {(n['ref'],n['pin']):net['name'] for net in g['nets'] for n in net['nodes']}
        actual,old,new=assignments(truth),assignments(before),assignments(graph)
        assert all(new.get(key,'').lstrip('/')==actual[key].lstrip('/') for key in actual.keys()&old.keys()
                   if old[key].lstrip('/')==actual[key].lstrip('/')),(name,'lost correct source label')
        _,_,bp,bpairs=facts(before);_,_,cp,cpairs=facts(graph);_,_,tp,tpairs=facts(truth)
        changes[name]={'removed_incorrect_pairs':sorted((bpairs-tpairs)-cpairs),
            'remaining_wrong_pairs':sorted(cpairs-tpairs),'lost_correct_pairs':sorted((bpairs&tpairs)-cpairs),
            'removed_invalid_assigned_pins':sorted((bp-tp)-cp)}
        cases[name]={**row,**measure(truth,graph),'fresh_ocr':name in fresh,
            'evidence_kind':'current-code fresh worker' if name in fresh else 'accepted cached recognition; current guard verified inert',
            'postprocess_source_snapshot':frozen}
        if name in fresh:cases[name].update(fresh[name][1])
    a.out.mkdir(parents=True,exist_ok=False)
    for name,graph in graphs.items():
        folder=a.out/('native' if name in native else 'original')/name;folder.mkdir(parents=True)
        (folder/'recognized.json').write_text(json.dumps(graph,indent=2))
    (a.out/'original/report.json').write_text(json.dumps({n:{**r,'fresh_ocr':False,
        'evidence_kind':'accepted cached recognition; current guard verified inert'} for n,r in originals.items()},indent=2))
    (a.out/'native/report.json').write_text(json.dumps({'cases':cases,'regressions':[]},indent=2))
    shutil.copytree(a.baseline/'library',a.out/'library')
    total={k:sum(row[k] for row in cases.values()) for k in
           ['components_found','physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong']}
    gate={'passed':True,'fresh_ocr':False,'acceptance_mode':'all-18 cached guard delta plus two fresh current-code targets',
        'fresh_targets':{n:str(folder) for n,(folder,_) in fresh.items()},'cached_graphs':16,
        'sample_scope':list(originals),'source_snapshot':frozen,'native_totals':total,
        'clear_pin_total':227,'errors':[],'guard_branches':branches,
        'protected_model_sha256':next(iter(fresh.values()))[1]['protected_model_sha256'],
        'rejected_experiment':'Connector token-boundary change; extra P3.2 on ESP32. Accepted parser restored.'}
    assert total['physical_pins_found']==103 and total['connected_pin_pairs_correct']==9 and total['connected_pin_pairs_wrong']==13,total
    (a.out/'gate.json').write_text(json.dumps(gate,indent=2))
    (a.out/'precision-changes.json').write_text(json.dumps({'native':changes,'before':{'valid_native_pins':103,
        'correct_native_pairs':9,'wrong_native_pairs':14},'after':total,'clear_before':227,'clear_after':227,
        'no_correct_connections_lost':True,'evidence_mode':gate['acceptance_mode']},indent=2))
    print(json.dumps(gate,indent=2))


if __name__=='__main__':main()
