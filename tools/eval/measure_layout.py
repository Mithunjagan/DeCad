"""Compare saved body-centre arrangement to recognized source positions, allowing scale/translation.

Errors are fractions of source-sheet width. Multiple Capture sections of one reference are
represented by their mean pin-extent centre. This measures placement, not OCR position accuracy.
"""
import argparse
import json
import math
from pathlib import Path
from statistics import median
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import orcad_capture as oc


def measure(folder):
    recognized = json.loads((folder / 'recognized.json').read_text())
    for attempt in range(3):
        try:
            page = oc.drawing(next((folder / 'orcad').glob('*.DSN')))[0]
            break
        except oc.OperationError as error:
            if 'License not found' not in str(error) or attempt == 2:
                raise
            print('Retrying transient Capture license checkout:', folder, flush=True)
            time.sleep(1)
    points = []
    for component in recognized['components']:
        if component.get('x') is None or component.get('y') is None:
            continue
        centres = []
        for part in page['parts']:
            if part['base'] != component['ref'] or not part['pins']:
                continue
            xs = [p['hx'] for p in part['pins']]
            ys = [p['hy'] for p in part['pins']]
            centres.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
        if centres:
            points.append((component['x'], component['y'],
                           sum(c[0] for c in centres) / len(centres),
                           sum(c[1] for c in centres) / len(centres)))
    if len(points) < 2:
        return {'page': [page['width'], page['height']], 'positioned_refs': len(points)}
    means = [sum(p[j] for p in points) / len(points) for j in range(4)]
    denominator = sum((p[0] - means[0])**2 + (p[1] - means[1])**2 for p in points)
    if not denominator:
        return {'page': [page['width'], page['height']], 'positioned_refs': len(points)}
    scale = sum((p[0] - means[0]) * (p[2] - means[2]) +
                (p[1] - means[1]) * (p[3] - means[3]) for p in points) / denominator
    if scale <= 0:
        return {'page': [page['width'], page['height']], 'positioned_refs': len(points),
                'error': 'No positive source-to-page similarity fit'}
    errors = [math.hypot(p[2] - means[2] - scale * (p[0] - means[0]),
                         p[3] - means[3] - scale * (p[1] - means[1])) / scale for p in points]
    return {'page': [page['width'], page['height']], 'positioned_refs': len(points),
            'similarity_rms_sheet_width': math.sqrt(sum(e * e for e in errors) / len(errors)),
            'similarity_median_sheet_width': median(errors)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('before', type=Path)
    ap.add_argument('after', type=Path)
    args = ap.parse_args()
    result = {}
    for sample in range(1, 6):
        key = f'S{sample}'
        if all((base / key / 'recognized.json').exists() and list((base / key / 'orcad').glob('*.DSN'))
               for base in (args.before, args.after)):
            result[key] = {'before': measure(args.before / key), 'after': measure(args.after / key)}
            print(key, result[key], flush=True)
            (args.after / 'layout-metrics.json').write_text(json.dumps(result, indent=2))
    (args.after / 'layout-metrics.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
