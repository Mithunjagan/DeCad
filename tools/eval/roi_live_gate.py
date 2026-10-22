"""One real component crop through the configured helper; no mock/model training."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import cv2
from app.roi_vision import RoIReader


if __name__=='__main__':
    out=ROOT/'evidence/pipeline-sprint-20261022/roi-live'
    out.mkdir(parents=True,exist_ok=True)
    rows=json.loads((ROOT/'evidence/pipeline-sprint-20261022/baseline-original/S4/pin-debug.json').read_text())
    selected=[row for row in rows if row[0]=='U15']
    box=(min(row[1] for row in selected),min(row[2] for row in selected)-48,
         max(row[1] for row in selected),max(row[2] for row in selected)+48)
    source=ROOT/'samples/orcad/Sample 4.jpg.jpeg'
    gray=cv2.imread(str(source),cv2.IMREAD_GRAYSCALE)
    reader=RoIReader()
    try:answer=reader.query(gray,box,'component',margin=48)
    finally:reader.close()
    report={'scope':'One real schematic component crop; does not establish full-circuit or arbitrary-input accuracy.',
            'source':str(source),'component_locator':'U15 stubs from the fresh local OCR baseline; no reference netlist was sent.',
            'bbox':box,'response':answer.model_dump() if answer else None,'audit':reader.audit}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
