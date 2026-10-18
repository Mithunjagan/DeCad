"""Harvest real text crops from scanned schematics for the schematic text reader.

Only confident, pattern-valid OCR readings are kept as labels (pin numbers, net labels, part
numbers, references). Keep the images used for evaluation out of --train, so held-out accuracy
is measured on sheets the model never saw.

  python tools/harvest_crops.py --train a.jpg b.jpg --holdout c.jpg --out real-crops
"""
import argparse, json, re, sys
from pathlib import Path
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import digital_vision as dv   # noqa: E402

VALID = re.compile(r'^(\d{1,3}|[A-Z]{1,7}\d{0,2}|74[A-Z]{0,4}\d{2,4}|[UR]\d{1,3}|[PJ]\d-[A-D]?\d{1,2}|\d[KR]\d{2}|\d{3}R)$')


def truth_label(t, toks, truth, ch):
    """The verified text of a reading, from an independent transcription of the sheet (ground truth):
    an exact reference or net label, or a misread IC reference ("US8", "!84", "C17") beside an IC part
    number whose repair names a transcribed reference. These are the hard cases worth teaching."""
    text = t.text.upper().strip('<>[]()=_.')
    refs = set(truth.get('components', {}))
    names = refs | set(truth.get('pins', {}).values()) | set(truth.get('components', {}).values())
    if text in names and t.conf >= 0.5:
        return text
    u = dv.lost_u(t.text) if hasattr(dv, 'lost_u') else None
    if u and u != text and u in refs and any(
            dv.IC_VALUE_RE.match(p.text.upper()) and abs(p.cx - t.cx) + abs(p.cy - t.cy) < 5 * ch for p in toks if p is not t):
        return u
    return None


def crops(path, min_conf, page_tokens=None, truth=None):
    page, toks = page_tokens or (lambda p: (p, dv.tokens(p)))(dv.prepare(path))
    ch = dv.char_height(page.text) or 40.0
    for t in toks:
        text = t.text.upper()
        verified = truth_label(t, toks, truth, ch) if truth else None
        if verified:
            text = verified
        elif t.conf < min_conf or not VALID.match(text):
            continue
        img = 255 - page.text[max(0, t.y0 - 3):t.y1 + 3, max(0, t.x0 - 3):t.x1 + 3]
        if img.size == 0:
            continue
        if t.vertical:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        yield img, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', nargs='*', default=[]); ap.add_argument('--holdout', nargs='*', default=[])
    ap.add_argument('--out', required=True); ap.add_argument('--min-conf', type=float, default=0.97)
    ap.add_argument('--tokens', nargs='*', default=[], help='saved ocr-tokens.json per image (--train then --holdout order)')
    ap.add_argument('--truth', nargs='*', default=[], help='ground-truth json per image, same order; adds verified labels')
    a = ap.parse_args()
    out = Path(a.out); (out / 'img').mkdir(parents=True, exist_ok=True)
    every = a.train + a.holdout
    saved = dict(zip(every, a.tokens)); truths = dict(zip(every, a.truth))
    for split, paths in (('crops', a.train), ('holdout', a.holdout)):
        rows = []
        for path in paths:
            page_tokens = None
            if path in saved:
                page = dv.prepare(Path(path))
                page_tokens = page, [dv.Token(**t) for t in json.loads(Path(saved[path]).read_text())]
            truth = json.loads(Path(truths[path]).read_text()) if path in truths else None
            for k, (img, text) in enumerate(crops(path, a.min_conf, page_tokens, truth)):
                name = f'img/{Path(path).stem.replace(" ", "_")}_{split}_{k}.png'
                cv2.imwrite(str(out / name), img); rows.append({'image': name, 'text': text})
        (out / f'{split}.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        print(split, len(rows))


if __name__ == '__main__':
    main()
