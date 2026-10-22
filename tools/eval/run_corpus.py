"""Evaluate any supplied circuit-image/netlist corpus; no built-in sample names.

python tools/eval/run_corpus.py manifest.json --out tools/eval/results/general

Manifest: {"cases": [{"id": "amplifier-photo", "source": "photo.jpg",
                     "reference": "reference.json", "reference_complete": true}]}
Paths are relative to the manifest. References use the app's Circuit JSON schema.
Incomplete references are reported as provisional and cannot pass the target.
This checks recognition output, not saved native CAD export equivalence.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.ingestion import ingest, parse_json  # noqa: E402
from corpus_metrics import score  # noqa: E402


async def evaluate(manifest, output, mode='auto', target=.99):
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    cases = payload.get('cases', [])
    if not cases:
        raise ValueError('The manifest must contain at least one case.')
    ids = [case.get('id') for case in cases]
    if any(not isinstance(value, str) or not value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise ValueError('Every corpus case needs a unique nonempty id.')
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for index, case in enumerate(cases, 1):
        started = time.monotonic()
        report = {'id': case['id'], 'reference_complete': case.get('reference_complete') is True}
        try:
            source = manifest.parent / case['source']
            reference = parse_json((manifest.parent / case['reference']).read_text(encoding='utf-8'))
            circuit, _ = await ingest(source, recognition_mode=mode)
            report.update(score(reference.model_dump(), circuit.model_dump()))
            report['warnings'] = circuit.warnings
            prediction = output / f'{index:04d}-recognized.json'
            prediction.write_text(circuit.model_dump_json(indent=2), encoding='utf-8')
            report['prediction'] = prediction.name
            # Missing denominators are undefined, not an automatic 100% score.
            required = [report[field][metric] for field in ('components', 'values', 'physical_pins', 'connections')
                        for metric in ('precision', 'recall')]
            if report['net_labels']['expected']:
                required.extend(report['net_labels'][metric] for metric in ('precision','recall'))
            report['meets_target'] = (report['reference_complete'] and report['false_connections'] == 0
                                      and all(value is not None and value >= target for value in required))
        except Exception as exc:
            report.update(error=str(exc), meets_target=False)
        report['seconds'] = round(time.monotonic() - started, 3)
        reports.append(report)
        print(f'{case["id"]}: ' + ('error: ' + report['error'] if 'error' in report else f'exact={report["sheet_exact"]}, target={report["meets_target"]}'), flush=True)
    result = {'mode': mode, 'target': target, 'cases': reports,
              'complete_references': sum(case['reference_complete'] for case in reports),
              'all_cases_meet_target': all(case['meets_target'] for case in reports),
              'measurement': 'recognition graph only; native CAD round-trip and source completeness require separate validation'}
    (output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mode', choices=['auto', 'digital', 'circuit', 'ocr', 'vision', 'hybrid_max_accuracy'], default='hybrid_max_accuracy')
    parser.add_argument('--target', type=float, default=.99)
    args = parser.parse_args()
    if not 0 < args.target <= 1:
        parser.error('--target must be greater than 0 and at most 1.')
    # Match the app's configured recognizers without importing/starting its API.
    from app.pipeline_profile import configure
    configure()
    tesseract = os.getenv('TESSERACT_DIR')
    if not tesseract and os.name == 'nt':
        candidate = Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR'
        if (candidate / 'tesseract.exe').is_file():
            tesseract = str(candidate)
    if tesseract:
        os.environ['PATH'] = tesseract + os.pathsep + os.environ.get('PATH', '')
    result = asyncio.run(evaluate(args.manifest.resolve(), args.out, args.mode, args.target))
    return 0 if result['all_cases_meet_target'] else 1


if __name__ == '__main__':
    sys.exit(main())
