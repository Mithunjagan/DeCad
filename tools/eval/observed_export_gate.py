"""Actual KiCad CLI and Capture reopen of all final recognized graphs, serially.

Measures export fidelity of the observed graph, never source recognition accuracy.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.observed_export import write_kicad,orcad_bundle
from benchmark_paths import prediction_path


def main(args):
    gate=json.loads((args.phase/'gate.json').read_text())
    if not gate['passed']:raise SystemExit('Requires a passing fresh recognition gate')
    args.out.mkdir(parents=True,exist_ok=False)
    cases={name:args.phase/'original'/name/'recognized.json' for name in gate['sample_scope']}
    native=json.loads((args.phase/'native/report.json').read_text())['cases']
    cases.update({name:prediction_path(args.phase/'native',name) for name in native})
    result={'passed':False,'scope':'Complete observed graph export fidelity, not recognition accuracy',
            'source_phase':str(args.phase),'cases':{},'errors':[]}
    for name,path in cases.items():
        print('Native export/readback:',name,flush=True)
        graph=json.loads(path.read_text());folder=args.out/name;folder.mkdir()
        row={}
        for format in ('kicad','orcad'):
            try:
                if format=='kicad':row[format]=write_kicad(graph,folder/'kicad',name)
                else:
                    data,row[format]=orcad_bundle(name,graph,folder)
                    (folder/(name+'-orcad.zip')).write_bytes(data)
                if not row[format]['passed']:result['errors'].append(name+': '+format+' comparison failed')
            except Exception as error:
                row[format]={'passed':False,'error':str(error)}
                result['errors'].append(name+': '+format+': '+str(error))
        result['cases'][name]=row
        (args.out/'report.json').write_text(json.dumps(result,indent=2))
    result['passed']=not result['errors'] and len(result['cases'])==18
    (args.out/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'passed':result['passed'],'cases':len(cases),'errors':result['errors']},indent=2),flush=True)
    return not result['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(p.parse_args()))
