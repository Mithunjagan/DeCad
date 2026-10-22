"""Apply cached production library checks without starting native CAD processes.

This checks recognized graphs, not saved DSN files. Missing cache data fails.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import orcad_capture as oc
from run_eval import GT_DIR, norm_ref, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    def unavailable(*args, **kwargs):
        raise RuntimeError('Native library lookup needed; frozen-cache gate cannot validate this graph.')
    oc._run = unavailable
    report = {}
    state = ROOT / 'backend/.state'
    cache_hashes = {name: hashlib.sha256((state / name).read_bytes()).hexdigest()
                    for name in ('orcad-pins.json', 'orcad-lib-index-v2.tsv')}
    for folder in sorted(args.input.iterdir()):
        source = folder / 'recognized.json'
        if not source.is_file():
            continue
        graph, notes = oc.check(json.loads(source.read_text()), state)
        out = args.out / folder.name
        out.mkdir(exist_ok=True)
        (out / 'recognized.json').write_text(json.dumps({**graph, 'warnings': notes}, indent=1))
        values = {norm_ref(c['ref']): c['value'] for c in graph['components']}
        pins = {f"{norm_ref(p['ref'])}.{p['pin']}": n['name'].upper() for n in graph['nets'] for p in n['nodes']}
        result = score(json.loads((GT_DIR / f'{folder.name.partition("-")[0]}.json').read_text()), values, pins, values)
        result.update(scope='recognition_with_cached_library_check', components=len(values), connections=len(pins),
                      cache_hashes=cache_hashes, native_export_verified=False)
        report[folder.name] = result
        print(folder.name, {k: v for k, v in result.items() if not isinstance(v, (list, dict))}, flush=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
