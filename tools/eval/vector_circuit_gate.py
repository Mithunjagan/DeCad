"""Actual recognition of three original real designs exported as native PDFs.

This is separate from raster regression acceptance: the rendering/ingestion
mode differs. Native targets can include hidden fields/pins; no arbitrary-image
accuracy certification is implied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'tools/eval'))


def main(args):
    rows=[json.loads(line) for line in (ROOT/'training/native_candidates_20261021/candidates.jsonl').read_text().splitlines()][:3]
    args.out.mkdir(parents=True,exist_ok=True)
    if not args.case:
        reports={};failed=[]
        for row in rows:
            identity=row['sample_id'];folder=args.out/identity
            with (args.out/(identity+'.log')).open('w',encoding='utf-8') as stream:
                process=subprocess.run([sys.executable,str(Path(__file__)), '--case',identity,'--out',str(folder)],
                                       cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            if process.returncode:failed.append(identity)
            if (folder/'report.json').is_file():reports[identity]=json.loads((folder/'report.json').read_text())
            print(identity,'completed' if not process.returncode else 'failed',flush=True)
        (args.out/'report.json').write_text(json.dumps({'scope':'Native-PDF recognition; separate from unchanged-input raster acceptance.',
            'cases':reports,'failed':failed,'fresh_ocr':True,'process_isolated':True},indent=2))
        return bool(failed)
    from app.pipeline_profile import configure
    configure()
    from app import digital_vision as dv,orcad_capture as oc
    from app.ocr_worker import session_providers
    from native_recognition_gate import measure
    from recognition_provenance import snapshot
    source_snapshot=snapshot()
    row=next(row for row in rows if row['sample_id']==args.case)
    original=ROOT/'training/native_candidates_20261021'/Path(row['native_netlist']).parent/'source.kicad_sch'
    assert hashlib.sha256(original.read_bytes()).hexdigest()==row['source_sha256']
    pdf=ROOT/'evidence/pipeline-sprint-20261022/vector-pdf'/(args.case+'.pdf')
    oc.available=lambda:False
    started=time.monotonic()
    graph=dv.extract(pdf,ROOT/'backend/.state').model_dump()
    (args.out/'recognized.json').write_text(json.dumps(graph,indent=1))
    assert snapshot()==source_snapshot
    report=measure(row['circuit'],graph)
    report.update(seconds=round(time.monotonic()-started,2),scope='Original real native source exported as PDF; targets may include hidden pins.',
                  source_sha256=row['source_sha256'],pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                  providers=session_providers(dv),recognizer_support_files=source_snapshot)
    (args.out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ('components_found','components_gt','physical_pins_found','physical_pins_gt',
                                          'connected_pin_pairs_correct','connected_pin_pairs_wrong','seconds')},indent=2))
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--case')
    raise SystemExit(main(parser.parse_args()))
