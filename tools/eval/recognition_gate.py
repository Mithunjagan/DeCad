"""Serial recognizer regression gate. Does not export or validate native CAD files.

Use --replay only for diagnosis; acceptance requires fresh OCR on both sides.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import digital_vision as dv
from app import orcad_capture as oc
from run_eval import GT_DIR, norm_ref, score


def regressions(before, after):
    """Counts alone can hide exchanging one correct observation for a wrong one."""
    errors = []
    for name, old in before.items():
        new = after.get(name)
        if new is None:
            errors.append(f'{name}: missing candidate result')
            continue
        for field in ('scope', 'source_sha256'):
            if new[field] != old[field]:
                errors.append(f'{name}: incomparable {field}')
        if not old['fresh_ocr'] or not new['fresh_ocr']:
            errors.append(f'{name}: diagnostic replay cannot pass acceptance')
        for field in ('parts_found', 'values_ok', 'pins_exact', 'pins_present'):
            if new[field] < old[field]:
                errors.append(f'{name}: {field} {old[field]} -> {new[field]}')
        gt = json.loads((GT_DIR / f'{name.partition("-")[0]}.json').read_text())
        if gt['components'] and new['parts_spurious'] > old['parts_spurious']:
            errors.append(f'{name}: additional spurious components')
        for field in ('missed_parts', 'wrong_values', 'wrong_pins'):
            failures = lambda row: {x[0] if isinstance(x, (list, tuple)) else x for x in row[field]}
            # Newly found references with unverified values are diagnosed separately;
            # every previously correct value must still be correct.
            previous_missing = set(old['missed_parts']) if field == 'wrong_values' else set()
            if failures(new) - failures(old) - previous_missing:
                errors.append(f'{name}: lost previously correct {field}')
        for value, (count, _) in old.get('value_counts', {}).items():
            if new['value_counts'][value][0] < count:
                errors.append(f'{name}: fewer {value} components')
    return errors


def main():
    from recognition_provenance import snapshot
    source_snapshot = snapshot()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', nargs='+')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--tokens-only', action='store_true', help='with --replay, read all pin strips again for model diagnostics')
    parser.add_argument('--diagnostic', action='store_true', help='save body and label associations')
    parser.add_argument('--require-fallback', action='store_true', help='fail if the configured candidate was not loaded')
    parser.add_argument('--require-identical-graphs', action='store_true', help='reject every component or net change, including facts outside partial ground truth')
    parser.add_argument('--baseline', type=Path, help='fail if a measured result regresses')
    args = parser.parse_args()
    if args.tokens_only and not args.replay:
        parser.error('--tokens-only requires --replay')
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    recognizer_hash = hashlib.sha256(Path(dv.__file__).read_bytes()).hexdigest()
    from app import text_fallback
    fallback_source_hash = hashlib.sha256(Path(text_fallback.__file__).read_bytes()).hexdigest()
    if args.require_fallback:
        dv.text_model()
        if dv.fallback_text_model() is None:
            raise RuntimeError('The configured candidate could not load.')
    text_model = Path(os.getenv('S2SDN_TEXT_MODEL') or ROOT / 'checkpoints/schematic-ocr/model.onnx')
    text_model_hash = hashlib.sha256(text_model.read_bytes()).hexdigest() if text_model.is_file() else None
    # Isolate recognition from installed/licensed Capture and its Tcl timeout.
    # Both baseline and candidate use exactly this scope.
    oc.available = lambda: False
    original_tokens, original_strip = dv.tokens, dv.read_pin_strip
    for name in args.samples:
        sample, _, variant = name.partition('-')
        source = (ROOT / 'tools/eval/degraded' / f'Sample {sample[1:]}-{variant}.pdf' if variant else
                  ROOT / 'samples/orcad' / f'Sample {sample[1:]}.jpg.jpeg')
        folder = args.out / name
        folder.mkdir(exist_ok=True)
        hits = {'hits': 0, 'misses': 0}
        if args.replay:
            saved = args.replay / name
            tokens = json.loads((saved / 'ocr-tokens.json').read_text())
            strips = {(int(p[1]), int(p[2])): (p[3], p[4]) for p in json.loads((saved / 'pin-debug.json').read_text())}
            def read_strip(page, x, y, ux, uy, ch):
                key = int(x), int(y)
                if key in strips:
                    hits['hits'] += 1
                    return strips[key]
                hits['misses'] += 1
                return original_strip(page, x, y, ux, uy, ch)
            dv.tokens = lambda page: [dv.Token(**t) for t in tokens]
            dv.read_pin_strip = original_strip if args.tokens_only else read_strip
        else:
            def capture(page):
                print(f'{name}: OCR ({page.gray.shape}, scale={page.scale:.3f})', flush=True)
                result = original_tokens(page)
                (folder / 'ocr-tokens.json').write_text(json.dumps([asdict(t) for t in result]))
                print(f'{name}: wiring ({len(result)} tokens)', flush=True)
                return result
            dv.tokens, dv.read_pin_strip = capture, original_strip
        started = time.time()
        def profile(frame, event, arg):
            side_check = getattr(dv, 'strip_side_retains_readings', None)
            if side_check and event == 'return' and frame.f_code is side_check.__code__:
                local = frame.f_locals
                data = {'before': local['before'], 'after': local['after'], 'accepted': bool(arg)}
                with (folder / 'strip-side-audit.jsonl').open('a') as stream:
                    stream.write(json.dumps(data) + '\n')
            if event == 'return' and frame.f_code is dv.recognize.__code__:
                local = frame.f_locals
                data = {k: local[k] for k in ('ch', 'bxs', 'anchors')}
                data['parts'] = [asdict(p) for p in local['parts']]
                data['refs'] = [(asdict(t), r) for t, r in local['refs']]
                data['edge_pins'] = local['edge_pins']
                data['end_box'] = local['end_box']
                data['strip_reads'] = local['strip_reads']
                data['rows'] = list(local['rows'].items())
                (folder / 'associations.json').write_text(json.dumps(data, indent=1))
        if args.diagnostic:
            sys.setprofile(profile)
        circuit = dv.extract(source, ROOT / 'backend/.state')
        sys.setprofile(None)
        graph = circuit.model_dump()
        from app.ocr_worker import session_providers
        providers = session_providers(dv)
        fallback = getattr(dv, '_TEXT_FALLBACK', None)
        if args.require_fallback and fallback is None:
            raise RuntimeError('The candidate fallback did not load; this run cannot measure it.')
        (folder / 'recognized.json').write_text(json.dumps(graph, indent=1))
        (folder / 'pin-debug.json').write_text(json.dumps(dv.PIN_DEBUG))
        values = {norm_ref(c['ref']): c['value'] for c in graph['components']}
        pins = {f"{norm_ref(p['ref'])}.{p['pin']}": n['name'].upper() for n in graph['nets'] for p in n['nodes']}
        result = score(json.loads((GT_DIR / f'{sample}.json').read_text()), values, pins, values)
        result.update(seconds=round(time.time() - started, 2), components=len(values), connections=len(pins),
                      scope='recognition_without_CAD_library_check', fresh_ocr=not bool(args.replay),
                      providers=providers,
                      text_model_sha256=text_model_hash,
                      fallback_model_sha256=fallback.model_sha256 if fallback else None,
                      fallback_routing={'baseline_max': fallback.baseline_max, 'candidate_min': fallback.candidate_min} if fallback else None,
                      source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      recognizer_sha256=recognizer_hash,
                      fallback_source_sha256=fallback_source_hash,
                      recognizer_support_files=source_snapshot)
        if args.replay:
            result['strip_replay'] = hits
            result['pin_strips_read_fresh'] = args.tokens_only
        report[name] = result
        (args.out / 'report.json').write_text(json.dumps(report, indent=1))
        print(name, {k: v for k, v in result.items() if not isinstance(v, (list, dict))}, flush=True)
    assert snapshot() == source_snapshot, 'Recognizer code or library facts changed during evaluation.'
    if args.baseline:
        baseline = json.loads((args.baseline / 'report.json').read_text())
        errors = regressions(baseline, report)
        unchanged = {}
        for name in baseline.keys() & report.keys():
            old = json.loads((args.baseline / name / 'recognized.json').read_text())
            new = json.loads((args.out / name / 'recognized.json').read_text())
            unchanged[name] = all(old[k] == new[k] for k in ('components', 'nets'))
            if args.require_identical_graphs and not unchanged[name]:
                errors.append(f'{name}: component or net graph changed; review required')
        comparison = {'passed': not errors, 'regressions': errors, 'graphs_identical': unchanged,
                      'scope': 'recognition_without_CAD_library_check'}
        (args.out / 'comparison.json').write_text(json.dumps(comparison, indent=1))
        print(comparison, flush=True)
        if errors:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
