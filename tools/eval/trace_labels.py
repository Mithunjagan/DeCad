"""Capture OCR tokens and ambiguous per-wire label votes without changing recognition decisions."""
import argparse
import builtins
from dataclasses import asdict
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import digital_vision as dv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--tokens', type=Path, help='replay a saved token file instead of running OCR')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original_tokens = dv.tokens
    traces = []

    def tokens(page):
        result = ([dv.Token(**t) for t in json.loads(args.tokens.read_text())]
                  if args.tokens else original_tokens(page))
        (args.out / 'tokens.json').write_text(json.dumps([asdict(t) for t in result], indent=1))
        return result

    def trace_max(*values, **kwargs):
        if (len(values) == 1 and isinstance(values[0], set) and len(values[0]) > 1
                and all(isinstance(v, str) for v in values[0]) and kwargs.get('key')):
            frame = inspect.currentframe().f_back
            data = frame.f_locals
            if 'own' in data and 'ref' in data and 'pin' in data:
                traces.append({'ref': data['ref'], 'pin': data['pin'], 'votes': data['own'],
                               'wire': asdict(data['wires'][data['i']]),
                               'labels': [{'token': asdict(t), 'name': name} for t, name in data['labels']]})
        return builtins.max(*values, **kwargs)

    dv.tokens = tokens
    dv.max = trace_max
    try:
        circuit = dv.extract(args.image, ROOT / 'backend/.state')
        (args.out / 'recognized.json').write_text(circuit.model_dump_json(indent=1))
        (args.out / 'ambiguous.json').write_text(json.dumps(traces, indent=1, default=lambda value: value.item()))
        (args.out / 'pin-debug.json').write_text(json.dumps(dv.PIN_DEBUG, indent=1))
        print('ambiguous votes:', [(t['ref'], t['pin'], t['votes']) for t in traces], flush=True)
    finally:
        dv.tokens = original_tokens
        del dv.max


if __name__ == '__main__':
    main()
