"""Geometry-only diagnosis from saved OCR (run in the single image-job queue)."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app import digital_vision as dv


def main():
    image,tokens,output=map(Path,sys.argv[1:4])
    page=dv.prepare(image)
    ch=dv.char_height(page.text) or 40.
    toks=[dv.Token(**t) for t in json.loads(tokens.read_text())]
    segs=dv.segments(page)
    contour=dv.boxes(page,ch)
    segment=dv.seg_boxes(segs,ch,max(4.,ch*.25))
    merged=dv._merge_boxes(contour+segment)
    split=dv._split_stacked(merged,segs,toks,ch)
    refs=[(dv.normalize_ref(t.text),t.cx,t.cy) for t in toks if dv.normalize_ref(t.text)]
    report={'char_height':ch,'contour_boxes':contour,'segment_boxes':segment,'merged':merged,'split':split,
            'segments':[[s.x0,s.y0,s.x1,s.y1,s.thick,s.horizontal] for s in segs],
            'refs':refs,'composites':[]}
    for box in merged:
        held=[r for r in refs if dv._inside(box,r[1],r[2]) and r[0].startswith(('U','IC'))]
        if len(held)<2 and not any(r[0]=='U43' for r in held):continue
        cuts=[]
        for horizontal in (True,False):
            lo,hi=(box[1],box[3]) if horizontal else (box[0],box[2])
            a0,a1=(box[0],box[2]) if horizontal else (box[1],box[3])
            selected=[s for s in segs if s.horizontal==horizontal and lo+2.5*ch<(s.y0 if horizontal else s.x0)<hi-2.5*ch
                      and min(a1,s.x1 if horizontal else s.y1)-max(a0,s.x0 if horizontal else s.y0)>=.8*(a1-a0)]
            cuts.append(dict(horizontal=horizontal,positions=[s.y0 if horizontal else s.x0 for s in selected]))
        report['composites'].append(dict(box=box,held=held,cuts=cuts))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=1))
    print(json.dumps({'char_height':ch,'composites':report['composites']},indent=1))


if __name__=='__main__':main()
