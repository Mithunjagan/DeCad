"""Render documented measurements from published, dated evidence; --check detects drift."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence/release-20261024'
BEGIN = '<!-- BEGIN GENERATED MEASUREMENTS -->'
END = '<!-- END GENERATED MEASUREMENTS -->'
CLEAR = ('S1', 'S3', 'S4', 'S5')
DEGRADED = ('S4-scan300', 'S4-scan200', 'S4-blur300')
LABELS = {'S1':'Sample 1', 'S3':'Sample 3', 'S4':'Sample 4', 'S5':'Sample 5',
          'S4-scan300':'Sample 4 · 300 dpi', 'S4-scan200':'Sample 4 · 200 dpi',
          'S4-blur300':'Sample 4 · blurred'}

def load(name):
    return json.loads((EVIDENCE / name).read_text(encoding='utf-8-sig'))

def measurements():
    report = load('recognition-report.json')
    gate = load('recognition-gate.json')
    exports = load('native-export-summary.json')
    closure = load('closure-summary.json')
    visual = load('visual-audit.json')
    pcb = load('footprint-repair.json')
    assert gate['passed'] and gate['fresh_ocr'] and gate['process_isolated']
    assert exports['passed'] and all(c['passed'] for c in exports['cases'].values())
    rows = []
    for name in CLEAR + DEGRADED:
        c = report[name]
        assert c['fresh_ocr'] and c['scope'] == 'recognition_without_CAD_library_check'
        assert 0 <= c['pins_exact'] <= c['pins_gt']
        assert 0 <= c['values_ok'] <= c['parts_found']
        rows.append({'id':name, 'label':LABELS[name], **{key:c[key] for key in (
            'parts_found','parts_gt','parts_spurious','values_ok','pins_exact','pins_gt','seconds')}})
    exact = sum(report[k]['pins_exact'] for k in CLEAR)
    truth = sum(report[k]['pins_gt'] for k in CLEAR)
    assert exact == gate['clear_pin_total'] == closure['clear_pins']
    assert {k:[report[k]['pins_exact'],report[k]['pins_gt']] for k in CLEAR} == gate['clear_pins']
    sources = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(EVIDENCE.glob('*.json'))
               if p.name != 'validation.json'}
    return {'measurement_date':'2026-10-24', 'scope':'Recorded recognition before CAD library substitution; not a fresh measurement of later source changes',
            'clear_exact':exact, 'clear_labelled_pins':truth, 'clear_exact_percent':round(100*exact/truth,2),
            'cases':rows, 'native_exports':{'cases':len(exports['cases']),
                'passed':sum(c['passed'] for c in exports['cases'].values()),
                'checked_pin_memberships':sum(c['checked_pins'] for c in exports['cases'].values()),
                'scope':exports['scope']},
            'xml_exports':closure['xml'], 'provisional_terminals':closure['provisional_terminals'],
            'native_recognition_subset':closure['native'],
            'visual_audits':{'cases':len(visual['cases']),
                'source_faithful':sum(c['source_faithful'] for c in visual['cases'].values())},
            'footprint_repair':{'parts':pcb['parts'], 'assigned':pcb['footprints']['assigned'],
                'native_pcb_netlisting_verified':pcb['pcb_readiness']['native_pcb_netlisting_verified'],
                'package_review_required':pcb['pcb_readiness']['needs_review']},
            'protected_model_sha256':gate['protected_model_sha256'], 'source_sha256':sources}

def section(data):
    text = [BEGIN, '## 📊 Measured, not promised', '',
        '<img src="docs/media/accuracy-20261024.svg" alt="Recorded 24 October results: 228 of 245 labelled pins exact across four clear sheets; degraded scans scored separately" width="100%"/>', '',
        f'**Recorded clear-sheet result: {data["clear_exact"]}/{data["clear_labelled_pins"]} labelled pin → net assignments exact ({data["clear_exact_percent"]:.1f}%).**', '',
        'Measured on **24 October 2026**, with a fresh, process-isolated CUDA OCR gate. These scores',
        'measure recognized graphs **before CAD library substitution**. They cover four clear sheets and',
        'selected labelled pin checkpoints, rather than complete-circuit accuracy. Later source changes',
        'and the code-test results below do not constitute another OCR benchmark.', '',
        '| Input | Matched parts / truth | Extra detections | Correct values / matched parts | Exact labelled pins | Worker time |',
        '|---|---:|---:|---:|---:|---:|']
    for c in data['cases']:
        text.append(f'| {c["label"]} | {c["parts_found"]}/{c["parts_gt"]} | {c["parts_spurious"]} | {c["values_ok"]}/{c["parts_found"]} | **{c["pins_exact"]}/{c["pins_gt"]} ({100*c["pins_exact"]/c["pins_gt"]:.1f}%)** | {c["seconds"]:.1f} s |')
    text += ['', 'Sample 2 has no labelled-pin denominator in this report and is excluded from the aggregate.',
        'The 200 dpi and blurred inputs still have **0/72 exact labelled assignments**; a valid export does',
        'not repair an unread source. Timings belong to this recorded run and are not a speed guarantee.', '',
        '**Export and appearance checks are separate measurements:**', '',
        '| Recorded check | Result | What it establishes |',
        '|---|---|---|',
        f'| Observed-graph OrCAD export regression | **{data["native_exports"]["passed"]}/{data["native_exports"]["cases"]} cases; {data["native_exports"]["checked_pin_memberships"]:,} pin memberships** | Saved native output preserves the supplied graph; this is not fresh recognition. |',
        f'| Faculty XML closure corpus | **{data["xml_exports"]}/18 exports** | XML serialization/readback, including {data["provisional_terminals"]} explicitly provisional terminals. TD9 application import is unverified. |',
        f'| Detailed source-appearance audits | **{data["visual_audits"]["source_faithful"]}/{data["visual_audits"]["cases"]} source-faithful** | Electrical checks passed, while symbol, geometry, or junction discrepancies still need review. |',
        f'| One saved-design footprint repair | **{data["footprint_repair"]["assigned"]}/{data["footprint_repair"]["parts"]} assigned; native PCB netlisting passed** | Five suggested packages still require physical package review. This is one case, not a corpus-wide PCB certification. |', '',
        'Inspect the [raw recognition report](evidence/release-20261024/recognition-report.json),',
        '[gate](evidence/release-20261024/recognition-gate.json),',
        '[export summary](evidence/release-20261024/native-export-summary.json), and',
        '[measurement definitions](docs/RESULTS.md). The [machine-readable metrics](docs/data/metrics.json)',
        'and this chart are generated from those records with `python tools/update_readme_stats.py`.', '', END]
    return '\n'.join(text)

def chart(data):
    rows = []
    for i,c in enumerate(data['cases']):
        y = 174 + i*54
        ratio = c['pins_exact']/c['pins_gt']
        color = '#a4b89a' if c['id'] in CLEAR else '#deb18b'
        rows += [f'<text x="38" y="{y+5}" fill="#e9e7de" font-size="16">{c["label"]}</text>',
                 f'<rect x="300" y="{y-12}" width="650" height="20" rx="5" fill="#2b302b"/>',
                 f'<rect x="300" y="{y-12}" width="{650*ratio:.2f}" height="20" rx="5" fill="{color}"/>',
                 f'<text x="980" y="{y+4}" fill="#e9e7de" font-size="16">{c["pins_exact"]}/{c["pins_gt"]} · {ratio*100:.1f}%</text>']
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="610" viewBox="0 0 1200 610" role="img" aria-labelledby="title desc">\n'
            '<title id="title">Recorded recognition results, 24 October 2026</title>\n'
            '<desc id="desc">228 of 245 labelled pins exact across four clear sheets. 300 dpi: 44 of 72. 200 dpi and blurred: zero of 72.</desc>\n'
            '<rect width="1200" height="610" rx="20" fill="#151917"/>\n'
            '<g font-family="Segoe UI,Helvetica,Arial,sans-serif">\n'
            '<text x="38" y="47" font-size="13" letter-spacing="2" fill="#deb18b">RECORDED RESULTS / 24 OCT 2026</text>\n'
            f'<text x="38" y="100" font-size="38" font-weight="600" fill="#eeeae2">{data["clear_exact_percent"]:.1f}% <tspan font-size="22" font-weight="400">exact labelled pins on four clear sheets</tspan></text>\n'
            '<text x="38" y="130" font-size="14" fill="#a6afa0">Fresh OCR · recognition graph before library substitution · 228 / 245 checkpoints</text>\n'
            +'\n'.join(rows)+'\n'
            '<text x="38" y="572" font-size="14" fill="#a6afa0">Selected checkpoints, not complete-sheet accuracy. Degraded scans remain an open problem.</text>\n'
            '</g>\n</svg>\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    data=measurements()
    readme=(ROOT/'README.md').read_text(encoding='utf-8-sig')
    block=section(data)
    if BEGIN in readme:
        updated=re.sub(re.escape(BEGIN)+'.*?'+re.escape(END),lambda _:block,readme,flags=re.S)
    else:
        updated=re.sub(r'## 📊 Measured, not promised.*?(?=## 🧠 How it works)',lambda _:block+'\n\n',readme,flags=re.S)
    assert updated != readme or BEGIN in readme, 'Measurement section not found'
    outputs={ROOT/'README.md':updated,ROOT/'docs/data/metrics.json':json.dumps(data,indent=2)+'\n',
             ROOT/'docs/media/accuracy-20261024.svg':chart(data)}
    changed=[]
    for path,content in outputs.items():
        if not path.exists() or path.read_text(encoding='utf-8-sig') != content:
            changed.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8',newline='\n')
    if args.check and changed:
        print('Stale measurement outputs: '+', '.join(changed));return 1
    print(f'{"Verified" if args.check else "Updated"}: {data["clear_exact"]}/{data["clear_labelled_pins"]} clear checkpoints; {data["native_exports"]["passed"]} native export cases.')
    return 0

if __name__=='__main__':
    sys.exit(main())
