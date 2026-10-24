"""Three source-backed native reconstructions, electrical checks and visual comparisons."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.observed_export import orcad_bundle
from app.orcad_source_raster import enrich
from app import orcad_capture as oc
from app.faculty_xml import from_circuit,serialize,parse,graph_fidelity


def comparison(graph,source,preview,title):
    from PIL import Image
    size=Image.open(source).size
    meta=graph['image_metadata'];scale=graph['_export_scale'];width=meta['width'];k=width/scale
    a,b,c=meta.get('source_affine',[[1,0,0],[0,1,0]])[0]
    d,e,f=meta.get('source_affine',[[1,0,0],[0,1,0]])[1]
    det=a*e-b*d
    coefficients=[e/det*k,-d/det*k,-b/det*k,a/det*k,
                  (b*f-e*c)/det-300*k*(e-b)/det,(d*c-a*f)/det-300*k*(a-d)/det]
    embedded=base64.b64encode(source.read_bytes()).decode()
    mime='image/png' if source.suffix.lower()=='.png' else 'image/jpeg'
    body=re.sub(r'^<svg[^>]*>|</svg>$','',preview.strip())
    panel=1000;height=round(panel*size[1]/size[0]);gap=20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{panel*2+gap}" height="{height+70}" viewBox="0 0 {panel*2+gap} {height+70}">'
            '<rect width="100%" height="100%" fill="white"/>'
            f'<text x="20" y="24" font-family="Arial" font-size="18">{oc._esc(title)} — original source</text>'
            f'<text x="{panel+gap+20}" y="24" font-family="Arial" font-size="18">Native .DSN readback, registered to source coordinates</text>'
            f'<svg x="0" y="45" width="{panel}" height="{height}" viewBox="0 0 {size[0]} {size[1]}">'
            f'<image href="data:{mime};base64,{embedded}" width="{size[0]}" height="{size[1]}"/></svg>'
            f'<svg x="{panel+gap}" y="45" width="{panel}" height="{height}" viewBox="0 0 {size[0]} {size[1]}">'
            f'<g transform="matrix({" ".join(str(v) for v in coefficients)})">{body}</g></svg>'
            f'<text x="20" y="{height+65}" font-family="Arial" font-size="13">Geometry and appearance are audited separately from electrical equivalence. See discrepancies.json; inferred routes are not source observations.</text></svg>')


def main(args):
    review=ROOT/'backend/workspaces/local/demosample1-wired/.review/circuit.json'
    before=hashlib.sha256(review.read_bytes()).hexdigest()
    cases={'demosample1-wired':(review,ROOT/'backend/workspaces/local/demosample1-wired/references/Sample 1.jpg.jpeg'),
           'SallenKey':(ROOT/'evidence/closure-20261024/unseen-final/unseen-raw-prediction.json',ROOT/'evidence/precision-20261023/unseen-sallen-key.png'),
           'Sample4':(ROOT/'evidence/closure-20261024/accepted/original/S4/recognized.json',ROOT/'samples/orcad/Sample 4.jpg.jpeg')}
    args.out.mkdir(parents=True,exist_ok=False)
    result={'passed':False,'electrical_passed':False,'source_faithful':False,'cases':{},'review_sha256_before':before,
            'acceptance':'Electrical and source fidelity are separate; unresolved discrepancies remain explicit.'}
    for name,(path,image) in cases.items():
        print('Source reconstruction:',name,flush=True)
        folder=args.out/name;folder.mkdir()
        graph=json.loads(path.read_text())
        data,report=orcad_bundle(name,graph,ROOT/'backend/.state',source_image=image)
        (folder/(name+'.zip')).write_bytes(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for filename in archive.namelist():(folder/filename).write_bytes(archive.read(filename))
        shutil.copy2(image,folder/('source'+image.suffix))
        visual=report['visual_comparison']
        (folder/'discrepancies.json').write_text(json.dumps(visual,indent=2))
        compare_graph={**graph,'_export_scale':report['source_layout']['source_scale']}
        (folder/'source-versus-output.svg').write_text(comparison(compare_graph,image,(folder/'preview.svg').read_text(),name),encoding='utf-8')
        (folder/'electrical-comparison.json').write_text(json.dumps({key:report[key] for key in
             ('passed','checked_pins','matched_pins','missing_parts','extra_parts','missing_pins','extra_pins','wrong_pins','electrical_group_errors','native_pin_memberships')},indent=2))
        xml=serialize(from_circuit(graph,board=name))
        xml_check=graph_fidelity(graph,parse(xml));assert xml_check['passed']
        (folder/'NetList.xml').write_bytes(xml)
        result['cases'][name]={'electrical_passed':report['passed'],'xml_passed':xml_check['passed'],
                              'components':report['components'],'checked_pins':report['checked_pins'],
                              'source_faithful':visual['source_faithful'],
                              'drawing_complete':report['routing'].get('drawing_complete',False),
                              'free_wire_ends':visual.get('endpoint_verification',{}).get('free_end_count'),
                              'source_supported_gap_repairs':len(visual.get('source_supported_gap_repairs',[])),
                              'observed_source_edges_kept':visual['observed_source_edges_kept'],
                              'inferred_segments':len(visual['inferred_segments']),
                              'fallback_symbols':visual['component_fallbacks'],
                              'symbol_mismatches':len(visual['symbol_mismatches']),
                              'pins_above_grid_tolerance':visual['pins_above_grid_tolerance'],
                              'route_segments_missing_or_deviating':len(visual['source_route_segments_missing_or_deviating']),
                              'missing_junctions':len(visual['missing_source_junctions']),
                              'incorrect_crossing_junctions':len(visual['incorrect_source_crossing_junctions']),
                              'dsn_sha256':hashlib.sha256((folder/(name+'.DSN')).read_bytes()).hexdigest()}
        print(name,json.dumps(result['cases'][name]),flush=True)
        (args.out/'report.json').write_text(json.dumps(result,indent=2))
    result['review_sha256_after']=hashlib.sha256(review.read_bytes()).hexdigest()
    result['original_review_unchanged']=result['review_sha256_after']==before
    result['electrical_passed']=all(row['electrical_passed'] for row in result['cases'].values())
    result['source_faithful']=all(row['source_faithful'] for row in result['cases'].values())
    result['electrical_and_review_checks_passed']=result['electrical_passed'] and result['original_review_unchanged'] and len(result['cases'])==3
    result['source_reconstruction_complete']=result['source_faithful'] and all(row['drawing_complete'] for row in result['cases'].values())
    result['passed']=result['electrical_and_review_checks_passed'] and result['source_reconstruction_complete']
    (args.out/'report.json').write_text(json.dumps(result,indent=2))
    return not result['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(parser.parse_args()))
