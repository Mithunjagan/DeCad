"""Check evidence fields on every actual final benchmark prediction."""
import argparse
import json
import math
from pathlib import Path
from benchmark_paths import prediction_path


def main(args):
    gate=json.loads((args.phase/'gate.json').read_text())
    if not gate['passed']:raise SystemExit('Requires a passing fresh recognition gate')
    sources={name:args.phase/'original'/name/'recognized.json' for name in gate['sample_scope']}
    native=json.loads((args.phase/'native/report.json').read_text())['cases']
    sources.update({name:prediction_path(args.phase/'native',name) for name in native})
    allowed={'vector','wire_trace','net_label','erc_healed','vlm_tiebreak'}
    result={'passed':False,'scope':'Schema and source-coordinate evidence validation, not recognition accuracy','cases':{},'errors':[]}
    for name,path in sources.items():
        graph=json.loads(path.read_text());errors=[];pins=0
        def scored(row,where):
            score=row.get('confidence')
            if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score) or not 0<=score<=1:
                errors.append(where+': missing or invalid confidence')
            if row.get('source') not in allowed:errors.append(where+': missing or invalid source')
        for net in graph['nets']:
            scored(net,'net '+net['name'])
            for node in net['nodes']:
                scored(node,node['ref']+'.'+node['pin']);pins+=1
        regions=graph.get('review_hotspots',[])
        for h in regions:
            scored(h,'region '+h['id'])
            box=h['bbox'];width,height=h['source_width'],h['source_height']
            if h.get('coordinate_space')!='source_pixels' or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height:
                errors.append('Invalid source-pixel region '+h['id'])
        if graph['components'] and not graph.get('image_metadata',{}).get('source_frames'):
            errors.append('Missing source frame for recognized components')
        result['cases'][name]={'pins_checked':pins,'nets_checked':len(graph['nets']),'regions_checked':len(regions),'errors':errors}
        result['errors'] += [name+': '+error for error in errors]
    result['passed']=len(sources)==18 and not result['errors']
    (args.phase/'confidence-gate.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    return not result['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',type=Path)
    raise SystemExit(main(p.parse_args()))
