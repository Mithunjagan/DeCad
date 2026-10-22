"""Exercise native extraction on original real KiCad designs, without OCR scores."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.pipeline_profile import configure
from app.vector_pdf import extract_page
import fitz


def main(out):
    configure()
    out.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(line) for line in (ROOT/'training/native_candidates_20261021/candidates.jsonl').read_text().splitlines()]
    reports=[]
    for row in rows[:3]:
        source=ROOT/'training/native_candidates_20261021'/Path(row['native_netlist']).parent/'source.kicad_sch'
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        assert digest==row['source_sha256']
        pdf=out/(row['sample_id']+'.pdf')
        proc=subprocess.run(['D:/KICAD/bin/kicad-cli.exe','sch','export','pdf','--black-and-white',
                             '--exclude-drawing-sheet','--pages','1','--output',str(pdf),str(source)],capture_output=True,text=True,timeout=90)
        (out/(row['sample_id']+'.log')).write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
        with fitz.open(pdf) as doc:
            page=extract_page(doc[0])
            assert page is not None
            reports.append({'sample':row['sample_id'],'native_source_sha256':digest,
                            'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                            'vector_primitives':page.primitive_count,'line_segments':len(page.lines),
                            'text_words':len(page.text),'junction_candidates':len(page.dots)})
    (out/'report.json').write_text(json.dumps({'scope':'Real native PDF geometry extraction only; no pin/net accuracy measured.',
                                             'cases':reports},indent=2))
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
