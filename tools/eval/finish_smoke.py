"""Preserve and score the supplied API smoke test, then delete its exact temporary project."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from run_eval import read_dsn, score, norm_ref, GT_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--sample', type=int, default=1)
    args = ap.parse_args()
    names = re.findall(r'^project (smoke-\d+)\s*$', args.log.read_text(), re.M)
    if len(names) != 1:
        raise ValueError('Expected one completed smoke project in the supplied log')
    pid = names[0]
    workspace = (ROOT / 'backend/workspaces/local').resolve()
    source = (workspace / pid).resolve()
    if source.parent != workspace or not source.is_dir():
        raise ValueError('Smoke project does not resolve directly inside the local workspace')
    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / 'orcad', args.out / 'orcad', dirs_exist_ok=True)
    shutil.copy2(args.log, args.out / 'smoke-api.log')
    graph = json.loads((args.out / 'orcad/circuit.json').read_text())
    parts, pins = read_dsn(next((args.out / 'orcad').glob('*.DSN')))
    values = {norm_ref(c['ref']): c['value'] for c in graph['components'] if norm_ref(c['ref']) in parts}
    result = score(json.loads((GT_DIR / f'S{args.sample}.json').read_text()), parts, pins, values)
    with httpx.Client(base_url='http://127.0.0.1:8100', timeout=30) as client:
        client.get('/auth/dev').raise_for_status()
        response = client.delete(f'/projects/{pid}')
        response.raise_for_status()
        result['cleanup'] = response.json()
    if source.exists():
        raise RuntimeError('Temporary smoke project still exists after API deletion')
    (args.out / 'score.json').write_text(json.dumps(result, indent=1))
    print({k: v for k, v in result.items() if not isinstance(v, list)}, flush=True)


if __name__ == '__main__':
    main()
