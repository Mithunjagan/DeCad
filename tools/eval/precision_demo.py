"""Reproducible live HTTP acceptance on the held-out Sallen-Key raster.

Run --recognize once, after other GPU gates have finished. Raw output is saved
before native reference export/read. --verify compares a separately transcribed
source review with the native graph and tests persistence and export downloads.
It never changes recognition code or feeds native data into recognition.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import parse,graph_fidelity,from_circuit,serialize
from tonight_metrics import measure


def check(response):
    response.raise_for_status();return response


def independent_native(path):
    xml=ET.parse(path).getroot()
    return {'components':[{'ref':c.attrib['ref'],'value':c.findtext('value') or ''}
                          for c in xml.findall('./components/comp')],
            'nets':[{'name':n.attrib['name'],'nodes':[{'ref':p.attrib['ref'],'pin':p.attrib['pin']}
                                                     for p in n.findall('node')]}
                     for n in xml.findall('./nets/net')]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recognize',action='store_true');p.add_argument('--verify',action='store_true')
    p.add_argument('--out',type=Path,default=ROOT/'evidence/precision-20261023')
    p.add_argument('--project',default='PrecisionUnseenFilter')
    p.add_argument('--automatic',action='store_true',help='Fresh raster-only OCR and separate literal/symmetric metrics; no saved review edits')
    p.add_argument('--image',type=Path,default=ROOT/'evidence/precision-20261023/unseen-sallen-key.png')
    args=p.parse_args();out=args.out;pid=args.project
    if args.automatic:
        from app.pipeline_profile import configure
        from app.digital_vision import extract
        from app.terminal_equivalence import symmetric_mapping
        from app.ocr_worker import session_providers
        from app import digital_vision as dv
        from recognition_provenance import snapshot
        configure();frozen=snapshot();out.mkdir(parents=True,exist_ok=False)
        started=time.monotonic();graph=extract(args.image).model_dump()
        raw=out/'unseen-raw-prediction.json';raw.write_text(json.dumps(graph,indent=2))
        # Only read independent evaluation truth after the raster prediction is
        # frozen. It is never passed into the recognizer or used for export IDs.
        truth=json.loads((ROOT/'evidence/precision-20261023/unseen-independent-truth.json').read_text())
        equivalent,receipt=symmetric_mapping(truth,graph)
        result={'fresh_ocr':True,'native_truth_read_after_prediction':True,'seconds':time.monotonic()-started,
                'literal':measure(truth,graph),'symmetric_terminal_equivalence':measure(truth,equivalent),
                'equivalence_receipt':receipt,'providers':session_providers(dv),'source_snapshot':frozen,
                'source_unchanged':snapshot()==frozen,'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
        result['faculty']=graph_fidelity(graph,parse(serialize(from_circuit(graph,board='UnseenAutomatic'))))
        (out/'report.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({k:result[k] for k in ('seconds','literal','symmetric_terminal_equivalence','faculty')},indent=2))
        return
    image=out/'unseen-sallen-key.png';native=Path('D:/KICAD/share/kicad/demos/simulation/sallen_key/sallen_key.kicad_sch')
    with httpx.Client(base_url='http://127.0.0.1:8100',timeout=1800) as api:
        check(api.get('/auth/dev'))
        if args.recognize:
            if (out/'unseen-raw-prediction.json').exists():raise SystemExit('Raw evidence already exists; refusing to overwrite.')
            check(api.post('/projects',json={'name':pid}))
            upload=check(api.post(f'/projects/{pid}/attachments',params={'name':image.name},content=image.read_bytes())).json()
            started=time.monotonic()
            response=check(api.post('/ai/chat',json={'project':pid,'message':'Import circuit source',
                'attachments':[upload['path']],'recognition_mode':'hybrid_max_accuracy'})).json()
            (out/'unseen-http-recognition.json').write_text(json.dumps(response,indent=2))
            raw=response['proposal'];(out/'unseen-raw-prediction.json').write_text(json.dumps(raw,indent=2))
            saved=check(api.put(f'/projects/{pid}/review',json={'circuit':raw})).json()
            (out/'unseen-http-raw-save.json').write_text(json.dumps({'project':pid,'revision':saved['revision'],
                'seconds':time.monotonic()-started,'raw_sha256':hashlib.sha256((out/'unseen-raw-prediction.json').read_bytes()).hexdigest(),
                'native_truth_read':False},indent=2))
            print('Raw raster recognition saved before native readback.',flush=True)
        if args.verify:
            raw=json.loads((out/'unseen-raw-prediction.json').read_text())
            review=json.loads((out/'unseen-source-transcription.json').read_text())
            # Preserve the initial pixel transcription and its failed native
            # comparison. Unprinted R/C IDs require explicit native pin/rotation
            # lookup; this manual numbering correction is not an OCR gain.
            subprocess.run(['D:/KICAD/bin/kicad-cli.exe','sch','export','netlist','--format','kicadxml',
                            '--output',str(out/'unseen-native-reference.xml'),str(native)],check=True)
            truth=independent_native(out/'unseen-native-reference.xml')
            (out/'unseen-independent-truth.json').write_text(json.dumps(truth,indent=2))
            measured={'raw':measure(truth,raw),'source_review':measure(truth,review),
                'scope':'Raw image recognition and manual review are separate. Initial guessed numbering failed independent readback; unprinted IDs were corrected from native pin definitions and rotations.',
                'transcription_sha256':hashlib.sha256((out/'unseen-source-transcription.json').read_bytes()).hexdigest()}
            physical={(p['ref'],p['pin']) for n in truth['nets'] for p in n['nodes']}
            positives={tuple(sorted(pair)) for n in truth['nets'] for pair in itertools.combinations(
                {(p['ref'],p['pin']) for p in n['nodes']},2)}
            negatives={tuple(sorted(pair)) for pair in itertools.combinations(physical,2)}-positives
            review_pairs={tuple(sorted(pair)) for n in review['nets'] for pair in itertools.combinations(
                {(p['ref'],p['pin']) for p in n['nodes']},2)}
            measured['independent_positive_negative_check']={'physical_pin_universe':len(physical),
                'positive_pairs':len(positives),'negative_pairs':len(negatives),
                'preserved_positive_pairs':len(positives&review_pairs),
                'preserved_negative_pairs':len(negatives-review_pairs)}
            (out/'unseen-metrics.json').write_text(json.dumps(measured,indent=2))
            if measured['source_review']['topology_pairwise']['fp'] or measured['source_review']['topology_pairwise']['fn']:
                raise SystemExit('Source transcription disagrees with independent native connectivity; inspect, do not claim exactness.')
            assert measured['source_review']['whole_graph_topology_and_values_exact'], 'Source component, pin inventory or value mismatch'
            # Keep source review visual evidence separate from stale automatic paths.
            review['image_metadata']=raw.get('image_metadata',{})
            review['image_metadata']['evidence_stale']=True
            for field in ('pin_anchors','wire_edges','wire_nodes','wires','label_anchors'):
                review['image_metadata'][field]=[]
            review['image_metadata']['source_attachment']='references/'+image.name
            review['image_metadata']['review_source']={'name':image.name,
                'path':f'/projects/{pid}/file?name=references%2F'+image.name}
            review['warnings']=['Manual source review with native pin-number lookup. U1 numbers are printed; unprinted R/C IDs were verified against embedded symbol pins and rotations after the initial convention failed readback. No automatic accuracy claim.']
            current=check(api.get(f'/projects/{pid}/review')).json()
            saved=check(api.put(f'/projects/{pid}/review',json={'circuit':review,'expected_revision':current['revision']})).json()
            reopened=check(api.get(f'/projects/{pid}/review')).json()
            assert saved['revision']==reopened['revision'] and saved['circuit']==reopened['circuit']
            (out/'unseen-reviewed-graph.json').write_text(json.dumps(reopened['circuit'],indent=2))
            xml=check(api.get(f'/projects/{pid}/export/faculty-xml'))
            (out/'unseen-reviewed-netlist.xml').write_bytes(xml.content)
            fidelity=graph_fidelity(reopened['circuit'],parse(xml.content));assert fidelity['passed'],fidelity
            reports={'project':pid,'saved_revision':saved['revision'],'reopen_equal':True,'faculty':fidelity,
                     'visual_ui':'NOT REPEATED: browser interaction disabled by Work settings','native':{}}
            for kind in ['observed-kicad','orcad-dsn']:
                response=check(api.post(f'/projects/{pid}/export/{kind}',json={
                    'circuit':reopened['circuit'],'source':'references/'+image.name,'preserve_connections':True}))
                path=out/f'{pid}-{kind}.zip';path.write_bytes(response.content)
                folder=out/f'unseen-{kind}';folder.mkdir(exist_ok=True)
                with zipfile.ZipFile(path) as archive:archive.extractall(folder)
                verification=list(folder.rglob('verification.json'))
                assert verification,kind+' omitted its native verification receipt'
                assert all(json.loads(f.read_text()).get('passed') and json.loads(f.read_text()).get('native_readback')
                           for f in verification),kind+' failed native readback'
                reports['native'][kind]={'http_status':response.status_code,'header':response.headers.get('x-verification'),
                    'verification':[json.loads(f.read_text()) for f in verification]}
                if kind=='observed-kicad':
                    exported=independent_native(next(folder.rglob('readback.xml')))
                else:
                    captured=json.loads(next(folder.rglob('netlist.json')).read_text())
                    exported={'components':captured['parts'],'nets':captured['nets']}
                independent=measure(truth,exported)
                assert independent['whole_graph_topology_and_values_exact'],kind+' disagrees with independent source graph'
                reports['native'][kind]['independent_source_comparison']=independent
            (out/'unseen-workflow.json').write_text(json.dumps(reports,indent=2))
            print(json.dumps({'raw':measured['raw']['topology_pairwise'],'source_review':measured['source_review']['topology_pairwise'],
                             'faculty':fidelity,'native':reports['native']},indent=2))


if __name__=='__main__':main()
