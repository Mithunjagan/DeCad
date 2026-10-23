"""Check XML fidelity and independent graph metrics on completed fresh predictions."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import from_circuit,serialize,parse,graph_fidelity,semantic_diff
from benchmark_paths import prediction_path
from tonight_metrics import measure,counts


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();gate=json.loads((args.phase/'gate.json').read_text())
    if not gate['passed']:raise SystemExit('Requires a successful fresh recognition gate.')
    args.out.mkdir(parents=True,exist_ok=False)
    paths={name:args.phase/'original'/name/'recognized.json' for name in gate['sample_scope']}
    native=json.loads((args.phase/'native/report.json').read_text())['cases']
    paths.update({name:prediction_path(args.phase/'native',name) for name in native})
    xml={};metrics={}
    for name,path in paths.items():
        graph=json.loads(path.read_text())
        try:
            document=from_circuit(graph,board=name);data=serialize(document);readback=parse(data)
            report=graph_fidelity(graph,readback)
            report.update(semantic_equal=semantic_diff(document,readback)['equal'],nodes=len(readback.nodes),nets=len(readback.nets))
            if report['passed'] and report['semantic_equal']:
                (args.out/(name+'.xml')).write_bytes(data);report['status']='PASS'
            else:report['status']='BLOCKED: source review required; zero-pin components cannot be encoded as faculty nodes'
            xml[name]=report
        except Exception as error:xml[name]={'passed':False,'status':'BLOCKED','error':str(error)}
        if name in native:
            row=native[name];records=[json.loads(line) for line in (Path(row['source'])/'candidates.jsonl').read_text().splitlines()]
            truth=next(r['circuit'] for r in records if r['sample_id']==name)
            metrics[name]=measure(truth,graph)
    totals={}
    for metric in ('component_detection','physical_pin_coverage','topology_pairwise'):
        totals[metric]=counts(*(sum(row[metric][key] for row in metrics.values()) for key in ('tp','fp','fn')))
    result={'scope':'XML fidelity independent of image accuracy; native metrics use independent original graphs and count extras.',
            'xml_cases':xml,'xml_passed':sum(r['passed'] for r in xml.values()),'xml_total':len(xml),
            'native_cases':metrics,'native_totals':totals,
            'note':'Physical pin coverage includes explicit observed unassigned inventory; sprint_gate reports assigned pins separately.'}
    (args.out/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'xml_passed':result['xml_passed'],'xml_total':len(xml),'native_totals':totals},indent=2))


if __name__=='__main__':main()
