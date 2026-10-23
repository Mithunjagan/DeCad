"""Publish final sprint tables only after recognition, evidence and native gates pass."""
import argparse
import json
import re
from pathlib import Path
from sprint_diff import report as diff_report

ROOT=Path(__file__).resolve().parents[2]


def load(path):return json.loads(path.read_text())


def main(args):
    gate=load(args.phase/'gate.json');confidence=load(args.phase/'confidence-gate.json');exports=load(args.exports/'report.json')
    if not all(x['passed'] for x in (gate,confidence,exports)):
        raise SystemExit('Every required final gate must pass before publishing completion')
    checks=ROOT/'evidence/pipeline-sprint-20261022'
    if not load(checks/'phase6-final-test-gate.json')['passed']:
        raise SystemExit('The final complete backend suite must pass')
    test_log=(checks/'phase6-final-full-tests.log').read_text()
    counts=re.search(r'(\d+) passed, (\d+) skipped',test_log)
    if not counts:raise SystemExit('Missing final test counts')
    changes,table=diff_report(args.phase,args.baseline,args.native_baseline)
    (args.phase/'diff.json').write_text(json.dumps(changes,indent=2))
    (args.phase/'diff.md').write_text(table)
    current=load(args.phase/'library/report.json')
    gained=sum(r['delta'] for r in changes['clear'].values())
    total=sum(r['after'] for r in changes['clear'].values())
    denominator=sum(r['total'] for r in changes['clear'].values())
    if any(r['lost_pins'] for r in changes['clear'].values()):raise SystemExit('Previously correct clear pins were lost')
    accepted=load(ROOT/'evidence/pipeline-sprint-20261022/phase5-clear-fresh/library/report.json')
    for name in changes['clear']:
        if {p[0] for p in current[name]['wrong_pins']}-{p[0] for p in accepted[name]['wrong_pins']}:
            raise SystemExit(name+': a latest accepted clear checkpoint regressed after library checking')
    if any(r['lost_correct_pairs'] or r['new_incorrect_pairs'] for r in changes['native'].values()):
        raise SystemExit('Native connectivity regression')
    lines=['# Schematic2SDN final pipeline sprint — 23 October 2026','',
        f'Phase 6 is complete. Fresh clear-sample pin-to-net checkpoints: **{total}/{denominator} ({100*total/denominator:.2f}%)**, **{gained:+d} correct pins** versus the original 217/245. All previously correct checkpoints were retained.',
        '', 'Completion means implementation and its required gates finished; it does not mean 100% source recognition accuracy.',
        '',table,'','## Degraded cases','',
        '| Case | Before | Final fresh | Delta |','|---|---:|---:|---:|']
    old=load(args.baseline/'report.json')
    for name in ('S4-scan300','S4-scan200','S4-blur300'):
        a,b,n=old[name]['pins_exact'],current[name]['pins_exact'],current[name]['pins_gt']
        lines.append(f'| {name} | {a}/{n} | {b}/{n} | {b-a:+d} |')
    lines+=['','S2 is included in graph regression and export checks but excluded from labelled-pin percentages because its annotation is incomplete.',
        '', '## Recovered clear checkpoints','', '| Sample | Newly correct pin → net |','|---|---|']
    for name,row in changes['clear'].items():
        lines.append('| '+name+' | '+', '.join(p['pin']+' → '+p['net'] for p in row['gained_pins'])+' |')
    lines+=['','## Verification','',
        f'- Complete final backend suite: {counts[1]} passed, {counts[2]} skipped. The live attachment-metadata fix also passed 16 focused confidence/attachment/routing tests.',
        '- Frontend: 14 model tests passed; Next.js 16.4.2 production build passed.',
        '- Live workbench: actual Sample 4 CUDA recognition; 271 source regions on the 9917×7016 image; confirmation preserved all scores; zoom, stale evidence after editing, Undo and a native-verified KiCad download passed.',
        '- Actual authenticated PDF page previews switched between pages 1 and 2. The synthetic UI fixture recovered two components and zero connections and is excluded from accuracy metrics.',
        f'- Confidence/source and source-coordinate validation passed on {len(confidence["cases"])} final predictions.',
        '- Final recognition ran serially with fresh OCR and successful worker exits, per-observation regression checks, recorded CUDA providers and an application-source snapshot held throughout the gate.',
        '- The primary original baseline is Phase 4, with the four latest Phase 5 clear records overlaid explicitly. This comparator is assembled from accepted fresh runs and is not itself a new eight-case run. The native gate protects Phase 4’s accepted nine correct pairs.',
        '', '## Actual native export readback','', '| Format | Graphs passing | Observed pin assignments matched |','|---|---:|---:|']
    for format in ('kicad','orcad'):
        rows=[r[format] for r in exports['cases'].values()]
        checked=sum(r['checked_pins'] for r in rows);matched=sum(r['matched_pins'] for r in rows)
        if len(rows)!=18 or checked!=matched or not all(r['passed'] and r['native_readback'] for r in rows):
            raise SystemExit('Incomplete native readback')
        lines.append(f'| {format} | {sum(r["passed"] for r in rows)}/18 | {matched}/{checked} |')
    lines+=['', 'Explicit observed-pin modes use generated symbols with literal observed IDs. KiCad CLI XML and actual Capture reopen compare every component reference, value and pin-to-net assignment, including unexpected extras. Capture net-name aliases are reversible and saved in the bundle. Native readback fidelity applies to these observed graphs; it does not prove recognition accuracy, original symbol appearance or faithful substitution in the separate normal library export modes.',
        '', '## Remaining errors and limits','']
    for name in ('S1','S3','S4','S5'):
        misses=current[name]['wrong_pins']
        lines.append(f'- {name}: '+('; '.join(f'{pin}: {read or "missing"} → expected {expected}' for pin,read,expected in misses) or 'none')+'.')
    wrong=changes['native_totals']['connected_pin_pairs_wrong']['after']
    lines += [f'- {wrong} incorrect native connected-pin pairs remain. The native corpus includes hidden pins/fields and uses physical-pin coverage and connected pairs, separately from the 245 manually labelled checkpoints.',
        '- Confident observations are retained; uncertain local recovery requires observed anchors, source ink and reader/catalog support. There is no sheet-wide complete-anchoring bypass. Unresolved regions remain for review rather than receiving guessed connections.',
        '- Evidence scores are heuristic, not calibrated probabilities. Confirmation changes only a review flag. Unknown or unlocated pins may retain low evidence scores without invented precise coordinates.',
        '- Base RoI vision helpers were unavailable or timed out in live attempts. No successful RoI-model gain is claimed. No weights were trained and rejected adapters stayed inactive.',
        '- Multiple source files retain separate region metadata; the current compare panel overlays the first attachment. Import other files separately to inspect their own source regions.',
        '', '## Evidence','',
        f'- Fresh recognition and exact diffs: `{args.phase}`.',
        f'- Native export/readback artifacts and verification: `{args.exports}`.',
        '- Original 28-pin / 14-pair diagnostic: `evidence/pipeline-sprint-20261022/local-recovery-diagnostic/failures.md`.',
        '- Final remaining-error inspection: `evidence/pipeline-sprint-20261022/phase6-final-failures/failures.md`.',
        '- UI checks/screenshots: `phase6-browser-qa.json`, `phase6-review-overlay.jpg`, `phase6-pdf-page2.jpg` under the sprint evidence folder.',
        f'- Protected OCR checkpoint SHA256: `{gate["protected_model_sha256"]}`.', '']
    text='\n'.join(lines)
    target=ROOT/'training/PIPELINE_SPRINT_FINAL_20261023.md'
    target.write_text(text,encoding='utf-8')
    history=ROOT/'training/COMPLETE_CIRCUIT_RESULTS_20261022.md'
    marker='\n<!-- FINAL-SPRINT-20261023 -->\n'
    original=history.read_text(encoding='utf-8').split(marker)[0]
    history.write_text(original+marker+text,encoding='utf-8')
    print(target)
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',type=Path,required=True)
    p.add_argument('--exports',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=ROOT/'evidence/pipeline-sprint-20261022/phase4-awake-final/library')
    p.add_argument('--native-baseline',type=Path,default=ROOT/'evidence/fullgraph-20261022/early-caption-v2-native')
    raise SystemExit(main(p.parse_args()))
