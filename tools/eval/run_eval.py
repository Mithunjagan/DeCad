"""End-to-end accuracy check: sample image -> recognition -> native OrCAD .DSN -> reopen -> score.

The score is taken from the saved .DSN itself (reopened through Capture's database), not from the
recognizer's intermediate output, and compared with hand-transcribed ground truth in
ground_truth/S<n>.json (part references/numbers and explicitly labelled pin->net checkpoints).

  python tools/eval/run_eval.py [--samples DIR] [--out DIR] 1 2 3 4 5
"""
import argparse, json, re, sys, time, traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.digital_vision import extract           # noqa: E402
from app import orcad_capture as oc              # noqa: E402

GT_DIR = Path(__file__).parent / 'ground_truth'
SAMPLES = ROOT / 'samples' / 'orcad'
if not SAMPLES.is_dir():  # original download location beside the repo
    SAMPLES = ROOT.parents[1] / 'ORCAD JPG Source file-20261015T225949Z-1-001' / 'ORCAD JPG Source file'
WILDCARD_VALUES = {'CONNECTOR', 'SWITCH', 'PROM'}


def norm_ref(r):
    return re.sub(r'[A-H]$', '', r) if re.match(r'^U\d+[A-H]$', r) else r


def read_dsn(dsn):
    """Parts and pin->net map of a saved design, read back through Capture's database."""
    parts, pins = {}, {}
    for line in oc._run(oc.orcad_root(), 'orcad_dump.tcl', dsn).splitlines():
        if line.startswith(('PIN ', 'PART ')):
            w = oc._tcl_list(line)
            if w[0] == 'PART':
                parts[norm_ref(w[1])] = (w[3] if len(w) > 3 else '').upper()
            elif len(w) > 3 and w[3]:
                pins[f'{norm_ref(w[1])}.{w[2]}'] = w[3].upper()
    return parts, pins


def score(gt, parts, pins, values):
    G = {k: v.upper() for k, v in gt['components'].items()}
    tp = [r for r in G if r in parts]
    fp = [r for r in parts if r not in G]
    if gt.get('partial'):       # only part of the sheet was transcribed: unlisted U-refs are not errors
        fp = [r for r in fp if not re.match(r'^U\d+$', r)]
    val_ok = [r for r in tp if values.get(r, '').upper() == G[r] or G[r] in WILDCARD_VALUES]
    P = {k: v.upper() for k, v in gt.get('pins', {}).items()}
    exact = [k for k, v in P.items() if pins.get(k) == v]
    res = {'parts_gt': len(G), 'parts_found': len(tp), 'parts_spurious': len(fp), 'values_ok': len(val_ok),
           'pins_gt': len(P), 'pins_exact': len(exact), 'pins_present': sum(k in pins for k in P),
           'missed_parts': [r for r in G if r not in parts], 'spurious_parts': fp,
           'wrong_values': [(r, values.get(r), G[r]) for r in tp if r not in val_ok],
           'wrong_pins': [(k, pins.get(k), v) for k, v in P.items() if k not in exact]}
    if gt.get('value_counts'):
        got = Counter(v.upper() for v in values.values())
        res['value_counts'] = {k: [got.get(k, 0), v] for k, v in gt['value_counts'].items()}
    return res


def pct(a, b):
    return f'{a / b:.0%}' if b else '–'


def extract_for_eval(src, state, folder, cache_ocr=False):
    if not cache_ocr:
        return extract(src, state)
    from dataclasses import asdict
    from app import digital_vision as dv
    original = dv.tokens

    def capture(page):
        result = original(page)
        (folder / 'ocr-tokens.json').write_text(json.dumps([asdict(t) for t in result]))
        return result

    dv.tokens = capture
    try:
        circuit = extract(src, state)
        (folder / 'pin-debug.json').write_text(json.dumps(dv.PIN_DEBUG))
        return circuit
    finally:
        dv.tokens = original


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('samples', nargs='*', type=int, default=[1, 2, 3, 4, 5])
    ap.add_argument('--images', default=str(SAMPLES))
    ap.add_argument('--out', default=str(Path(__file__).parent / 'results'))
    ap.add_argument('--variant', help='score "Sample <n>-<variant>.pdf" (see make_degraded.py) against sample n')
    ap.add_argument('--cache-ocr', action='store_true', help='save raw OCR tokens for diagnostic replay')
    ap.add_argument('--resume-export', action='store_true', help='retry export of an already recognized graph')
    a = ap.parse_args()
    out, state = Path(a.out), str(ROOT / 'backend' / '.state')
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.is_file() else {}
    for i in a.samples:
        t = time.time()
        key = f'S{i}-{a.variant}' if a.variant else f'S{i}'
        src = Path(a.images) / (f'Sample {i}-{a.variant}.pdf' if a.variant else f'Sample {i}.jpg.jpeg')
        d = out / key
        d.mkdir(exist_ok=True)
        previous_seconds = report.get(key, {}).get('seconds', 0) if a.resume_export else 0
        try:
            if a.resume_export:
                g = json.loads((d / 'recognized.json').read_text())
            else:
                c = extract_for_eval(src, state, d, a.cache_ocr)
                g = c.model_dump()
                (d / 'recognized.json').write_text(json.dumps(g, indent=1))
            graph = {**g, 'nets': [n for n in g['nets'] if n['nodes']]}
            _, st = oc.save_to_project(d, key.replace('-', '_'), graph, state)
            parts, pins = read_dsn(next((d / 'orcad').glob('*.DSN')))
            values = {norm_ref(x['ref']): x['value'] for x in g['components'] if norm_ref(x['ref']) in parts}
            gt = json.loads((GT_DIR / f'S{i}.json').read_text())
            r = score(gt, parts, pins, values)
            r.update(seconds=previous_seconds + round(time.time() - t), dsn_passed=st['passed'], dsn_components=st['components'],
                     dsn_pins=st['checked_pins'], dsn_nets=st['nets'], notes=[w for w in g.get('warnings', [])
                                                                              if 'upscaled' in w or 'resolution' in w.lower()])
            if a.resume_export:r['export_retry'] = True
        except Exception as e:
            traceback.print_exc()
            r = {'error': repr(e)[:400], 'seconds': round(time.time() - t)}
        report[key] = r
        report_path.write_text(json.dumps(report, indent=1))
        print(f'{key}:', {k: v for k, v in r.items() if not isinstance(v, list)}, flush=True)
    lines = ['| Sample | Parts found | Precision | Values | Labelled pins exact | DSN | Time |', '|---|---|---|---|---|---|---|']
    for k in sorted(report):
        r = report[k]
        if 'error' in r:
            lines.append(f'| {k[1:]} | error: {r["error"][:80]} | | | | | |')
            continue
        lines.append(f'| {k[1:]} | {r["parts_found"]}/{r["parts_gt"]} ({pct(r["parts_found"], r["parts_gt"])}) | '
                     f'{pct(r["parts_found"], r["parts_found"] + r["parts_spurious"])} | {pct(r["values_ok"], r["parts_found"])} | '
                     f'{r["pins_exact"]}/{r["pins_gt"]} ({pct(r["pins_exact"], r["pins_gt"])}) | '
                     f'{"verified" if r["dsn_passed"] else "FAILED"}, {r["dsn_components"]} parts, {r["dsn_pins"]} pins | {r["seconds"]} s |')
        if r.get('value_counts'):
            lines.append(f'| | part-number counts (found/expected): ' + ', '.join(f'{v} {a}/{b}' for v, (a, b) in r['value_counts'].items()) + ' | | | | | |')
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
