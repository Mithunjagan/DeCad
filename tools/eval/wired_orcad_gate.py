"""Reopen native OrCAD exports and check visible wires independently of net labels."""
import argparse
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import orcad_capture as oc
from app.observed_export import orcad_bundle


def main(args):
    cases = {p.parent.name: p for p in sorted(args.phase.glob('**/recognized.json'))}
    cases['SallenKey'] = ROOT / 'evidence/closure-20261024/unseen-final/unseen-raw-prediction.json'
    if args.case:
        cases = {name: path for name, path in cases.items() if name in args.case}
    args.out.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'expected_cases':len(cases), 'scope': 'Visible wire continuity and reviewed graph export fidelity', 'cases': {}}
    for name, path in cases.items():
        print('Wiring/readback:', name, flush=True)
        folder = args.out / name
        folder.mkdir(exist_ok=True)
        try:
            data, report = orcad_bundle(name, json.loads(path.read_text()), folder)
            (folder / (name + '-wired.zip')).write_bytes(data)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for filename in archive.namelist():
                    (folder / filename).write_bytes(archive.read(filename))
            pages = oc.drawing(folder / (name + '.DSN'))
            (folder / 'preview.svg').write_text(oc.svg(pages, name), encoding='utf-8')
            (folder / 'drawing.json').write_text(json.dumps(pages, indent=2))
            result['cases'][name] = report
            routing=report['routing'];source=routing.get('source_reconstruction',{})
            print(name, json.dumps({'passed':report['passed'],'wired_nets':routing['wired_nets'],
                                   'retained_source_unit_edges':source.get('retained_source_unit_edges'),
                                   'inferred_segments':len(source.get('inferred_segments',[]))}), flush=True)
        except Exception as error:
            result['cases'][name] = {'passed': False, 'error': str(error)}
            print(name, 'FAILED', str(error), flush=True)
        result['passed'] = bool(cases) and len(result['cases'])==len(cases) and all(r['passed'] for r in result['cases'].values())
        (args.out / 'report.json').write_text(json.dumps(result, indent=2))
    return not result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', type=Path, default=ROOT / 'evidence/closure-20261024/accepted')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', action='append')
    raise SystemExit(main(parser.parse_args()))
