"""Live raw-raster proposal, draft persistence and native download verification.

Creates a new demonstration project. Existing reviewed projects are untouched;
no reference netlist or manual correction enters the recognition request.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import parse,graph_fidelity


def checked(response):response.raise_for_status();return response


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',default='FinalClosure20261024')
    args=p.parse_args();out=ROOT/'evidence/closure-20261024/live-automatic';out.mkdir(parents=True,exist_ok=False)
    image=ROOT/'evidence/precision-20261023/unseen-sallen-key.png';started=time.monotonic()
    with httpx.Client(base_url='http://127.0.0.1:8100',timeout=1800) as api:
        checked(api.get('/auth/dev'))
        checked(api.post('/projects',json={'name':args.project}))
        upload=checked(api.post(f'/projects/{args.project}/attachments',params={'name':image.name},content=image.read_bytes())).json()
        response=checked(api.post('/ai/chat',json={'project':args.project,'message':'Import circuit source',
            'attachments':[upload['path']],'recognition_mode':'hybrid_max_accuracy'})).json()
        graph=response['proposal'];(out/'proposal.json').write_text(json.dumps(graph,indent=2))
        assert len(graph['components'])==8 and sum(len(n['nodes']) for n in graph['nets'])==19
        assert any(p.get('source')=='implicit_passive_terminal' for n in graph['nets'] for p in n['nodes'])
        saved=checked(api.put(f'/projects/{args.project}/review',json={'circuit':graph})).json()
        reopened=checked(api.get(f'/projects/{args.project}/review')).json()
        assert saved['revision']==reopened['revision'] and saved['circuit']==reopened['circuit']
        xml=checked(api.get(f'/projects/{args.project}/export/faculty-xml')).content
        (out/'NetList.xml').write_bytes(xml)
        faculty=graph_fidelity(reopened['circuit'],parse(xml));assert faculty['passed'],faculty
        native={}
        for kind in ('observed-kicad','orcad-dsn'):
            download=checked(api.post(f'/projects/{args.project}/export/{kind}',json={
                'circuit':reopened['circuit'],'source':'references/'+image.name,'preserve_connections':True}))
            (out/(kind+'.zip')).write_bytes(download.content)
            with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                receipts=[json.loads(archive.read(name)) for name in archive.namelist() if name.endswith('verification.json')]
            assert receipts and all(r['passed'] and r['native_readback'] for r in receipts),(kind,receipts)
            native[kind]={'passed':True,'receipts':receipts,'sha256':hashlib.sha256(download.content).hexdigest()}
        result={'passed':True,'project':args.project,'fresh_live_raster_recognition':True,'native_truth_supplied':False,
                'manual_correction':False,'components':len(graph['components']),
                'assigned_pins':sum(len(n['nodes']) for n in graph['nets']),
                'saved_revision':saved['revision'],'reopen_equal':True,'faculty':faculty,'native':native,
                'seconds':time.monotonic()-started,'source_sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
        (out/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
