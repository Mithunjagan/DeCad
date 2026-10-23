"""Summarize measured phase gates; never substitute cached outputs for fresh OCR."""
import argparse
import itertools
import json
from pathlib import Path


def report(phase, original_baseline, native_baseline):
    gate=json.loads((phase/'gate.json').read_text())
    old=json.loads((original_baseline/'report.json').read_text())
    new=json.loads((phase/'library/report.json').read_text())
    lines=[f"Phase gate: {'PASS' if gate['passed'] else 'FAIL'}",'',
           '| Sample | Before | After | Correct-pin delta | Percentage-point delta |',
           '|---|---:|---:|---:|---:|']
    result={'passed':gate['passed'],'clear':{},'native':{}}
    for name in ('S1','S3','S4','S5'):
        before,after,total=old[name]['pins_exact'],new[name]['pins_exact'],new[name]['pins_gt']
        assert old[name]['pins_gt']==total
        delta=after-before
        result['clear'][name]={'before':before,'after':after,'total':total,'delta':delta,
                               'percentage_point_delta':100*delta/total}
        lines.append(f'| {name} | {before}/{total} | {after}/{total} | {delta:+d} | {100*delta/total:+.2f} |')
    before=sum(r['before'] for r in result['clear'].values())
    after=sum(r['after'] for r in result['clear'].values())
    total=sum(r['total'] for r in result['clear'].values())
    lines.append(f'| **Total** | **{before}/{total}** | **{after}/{total}** | **{after-before:+d}** | **{100*(after-before)/total:+.2f}** |')
    lines+=['','Native-design metrics are valid physical-pin coverage and connected-pin pairs against the native reference. These are separate from the manually annotated clear-sample pin-to-net label score; native targets may include hidden pins.',
            '', '| Native design | Valid pins before -> after (delta) | Correct pairs before -> after (delta) | Incorrect pairs before -> after (delta) |',
            '|---|---:|---:|---:|']
    old_native=json.loads((native_baseline/'report.json').read_text())['cases']
    new_native=json.loads((phase/'native/report.json').read_text())['cases']
    design_names={};truths={}
    for source in {r['source'] for r in old_native.values()}:
        for line in (Path(source)/'candidates.jsonl').read_text().splitlines():
            record=json.loads(line)
            design_names[record['sample_id']]=record.get('source_file',record['sample_id'])
            if record['sample_id'] in old_native:truths[record['sample_id']]=record['circuit']
    result['native_source_designs']={identity:design_names.get(identity,identity) for identity in old_native}
    keys=('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')
    totals={key:[0,0] for key in keys}
    for identity,row in old_native.items():
        if identity not in new_native:
            lines.append(f'| {identity} | NOT RUN | NOT RUN | NOT RUN |');continue
        now=new_native[identity];cells=[];result['native'][identity]={}
        for key in keys:
            a,b=row[key],now[key]
            totals[key][0]+=a;totals[key][1]+=b
            result['native'][identity][key]={'before':a,'after':b,'delta':b-a}
            cells.append(f'{a} -> {b} ({b-a:+d})')
        def pairs(g):
            return {tuple(sorted(pair)) for net in g['nets'] for pair in itertools.combinations(
                sorted({(p['ref'].upper(),str(p['pin'])) for p in net['nodes']}),2)}
        truth_pairs=pairs(truths[identity])
        before_pairs=pairs(json.loads((native_baseline/identity/'recognized.json').read_text()))
        after_pairs=pairs(json.loads((phase/'native'/identity/identity/'recognized.json').read_text()))
        result['native'][identity]['new_correct_pairs']=sorted((after_pairs-before_pairs)&truth_pairs)
        result['native'][identity]['lost_correct_pairs']=sorted((before_pairs-after_pairs)&truth_pairs)
        result['native'][identity]['new_incorrect_pairs']=sorted(after_pairs-before_pairs-truth_pairs)
        result['native'][identity]['removed_incorrect_pairs']=sorted(before_pairs-after_pairs-truth_pairs)
        lines.append('| '+identity+' | '+' | '.join(cells)+' |')
    lines.append('| **Total** | '+' | '.join(f'**{a} -> {b} ({b-a:+d})**' for a,b in totals.values())+' |')
    result['native_totals']={key:{'before':a,'after':b,'delta':b-a} for key,(a,b) in totals.items()}
    result['trace_coverage']={}
    result['original_graphs_identical']={}
    predictions=list((phase/'original').glob('*/recognized.json'))
    predictions+=list((phase/'native').glob('*/*/recognized.json'))
    for path in predictions:
        graph=json.loads(path.read_text())
        metadata=graph.get('image_metadata',{})
        anchors=metadata.get('pin_anchors',[])
        result['trace_coverage'][path.parent.name]={
            'anchors':len(anchors),'mapped_anchors':sum(p.get('physical_net') is not None for p in anchors),
            'connectivity_rewrite_applied':bool(metadata.get('applied')),
            'retained_legacy_groups':metadata.get('retained_legacy_groups',0)}
        baseline_path=original_baseline.parent/'original'/path.parent.name/'recognized.json'
        if path.parent.parent.name=='original' and baseline_path.is_file():
            baseline_graph=json.loads(baseline_path.read_text())
            def signature(g):
                return (sorted((p['ref'],p['value']) for p in g['components']),
                        sorted((n['name'],sorted((p['ref'],p['pin']) for p in n['nodes'])) for n in g['nets']))
            result['original_graphs_identical'][path.parent.name]=signature(graph)==signature(baseline_graph)
    lines+=['','Gate errors: '+('; '.join(gate['errors']) if gate['errors'] else 'none'),'',
            'Accuracy numbers above are read from persisted actual evaluation reports. Unit tests and export fidelity are not counted as recognition accuracy.']
    return result,'\n'.join(lines)+'\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',type=Path)
    parser.add_argument('--original-baseline',type=Path,default=Path('evidence/pipeline-sprint-20261022/phase3-revised/library'))
    parser.add_argument('--native-baseline',type=Path,default=Path('evidence/fullgraph-20261022/early-caption-v2-native'))
    args=parser.parse_args()
    data,markdown=report(args.phase,args.original_baseline,args.native_baseline)
    (args.phase/'diff.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (args.phase/'diff.md').write_text(markdown,encoding='utf-8')
    print(markdown)
