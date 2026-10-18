"""Diagnostic replay of saved OCR tokens; acceptance still requires a fresh full evaluation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import digital_vision as dv, orcad_capture as oc
from run_eval import norm_ref, read_dsn, score, GT_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', type=Path)
    ap.add_argument('tokens', type=Path)
    ap.add_argument('--sample', type=int, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--strips', type=Path, help='replay saved pin-strip text at unchanged pixel positions')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original = dv.tokens
    original_strip = dv.read_pin_strip
    strip_stats = {'hits': 0, 'misses': 0}
    if args.strips:
        strips = {(int(p[1]), int(p[2])): (p[3], p[4]) for p in json.loads(args.strips.read_text())}

        def read_strip(page, x, y, ux, uy, ch):
            key = int(x), int(y)
            if key in strips:
                strip_stats['hits'] += 1
                return strips[key]
            strip_stats['misses'] += 1
            return original_strip(page, x, y, ux, uy, ch)

        dv.read_pin_strip = read_strip
    dv.tokens = lambda page: [dv.Token(**t) for t in json.loads(args.tokens.read_text())]
    try:
        circuit = dv.extract(args.image, ROOT / 'backend/.state')
    finally:
        dv.tokens = original
        dv.read_pin_strip = original_strip
    graph = circuit.model_dump(exclude={'warnings'})
    (args.out / 'recognized.json').write_text(circuit.model_dump_json(indent=1))
    (args.out / 'pin-debug.json').write_text(json.dumps(dv.PIN_DEBUG))
    _, status = oc.save_to_project(args.out, f'S{args.sample}', graph, ROOT / 'backend/.state')
    parts, pins = read_dsn(next((args.out / 'orcad').glob('*.DSN')))
    values = {norm_ref(c['ref']): c['value'] for c in graph['components'] if norm_ref(c['ref']) in parts}
    result = score(json.loads((GT_DIR / f'S{args.sample}.json').read_text()), parts, pins, values)
    result.update(token_replay=True, dsn_passed=status['passed'], dsn_pins=status['checked_pins'])
    if args.strips:result['strip_replay'] = strip_stats
    (args.out / 'score.json').write_text(json.dumps(result, indent=1))
    print({k: v for k, v in result.items() if not isinstance(v, list)}, flush=True)


if __name__ == '__main__':
    main()
