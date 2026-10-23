"""Actual CPU image smoke and faculty XML semantic gate; no answer-fed recognition."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import parse,serialize,to_circuit,from_circuit,semantic_diff,graph_fidelity
from app.ingestion import extract_image


def main():
    out=ROOT/'evidence/tonight-20261023';out.mkdir(parents=True,exist_ok=True)
    fixture=ROOT/'training/faculty/NetList (1).xml'
    original=parse(fixture.read_bytes());graph=to_circuit(original)
    data=serialize(from_circuit(graph));(out/'faculty-roundtrip.xml').write_bytes(data)
    report={'scope':'Interchange fidelity, NOT image accuracy or TD9 vendor import',
            'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'faculty_semantics':semantic_diff(original,parse(data)),
            'faculty_graph':graph_fidelity(graph,parse(data)),'vendor_import':'NOT VERIFIED'}
    # This is a documented synthetic fixture smoke, explicitly not the unseen test.
    source=ROOT/'backend/tests/vision_fixtures/divider.png';started=time.monotonic()
    prediction=asyncio.run(extract_image(source,mode='circuit'))
    (out/'gate0-prediction.json').write_text(prediction.model_dump_json(indent=2))
    data=serialize(from_circuit(prediction));(out/'gate0-netlist.xml').write_bytes(data)
    report['gate0']={'source':str(source),'synthetic':True,'fresh_cpu_recognition':True,
                     'seconds':round(time.monotonic()-started,3),**graph_fidelity(prediction,parse(data))}
    report['passed']=report['faculty_semantics']['equal'] and report['faculty_graph']['passed'] and report['gate0']['passed']
    (out/'xml-gate.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return not report['passed']


if __name__=='__main__':raise SystemExit(main())
