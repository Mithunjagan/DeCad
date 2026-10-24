"""Persist and export an actual fresh, provisional raster proposal via the API."""
import io,json,sys,zipfile
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.faculty_xml import parse,graph_fidelity
if __name__=='__main__':
    base=ROOT/'evidence/closure-20261024';out=base/'live-provisional';out.mkdir(parents=True,exist_ok=False)
    graph=json.loads((base/'accepted/original/S4-scan300/recognized.json').read_text())
    provisional=[p for n in graph['nets'] for p in n['nodes'] if p.get('source')=='provisional_stub'];assert provisional
    project='ClosureProvisional20261024';source=ROOT/'tools/eval/degraded/Sample 4-scan300.pdf'
    def checked(r):r.raise_for_status();return r
    with httpx.Client(base_url='http://127.0.0.1:8100',timeout=180) as api:
        checked(api.get('/auth/dev'));checked(api.post('/projects',json={'name':project}))
        attachment=checked(api.post(f'/projects/{project}/attachments',params={'name':source.name},content=source.read_bytes())).json()
        checked(api.put(f'/projects/{project}/review',json={'circuit':graph}))
        reopened=checked(api.get(f'/projects/{project}/review')).json()['circuit'];assert reopened==graph
        xml=checked(api.get(f'/projects/{project}/export/faculty-xml')).content;(out/'NetList.xml').write_bytes(xml)
        fidelity=graph_fidelity(graph,parse(xml));assert fidelity['passed']
        exports={}
        for kind in ('observed-kicad','orcad-dsn'):
            data=checked(api.post(f'/projects/{project}/export/{kind}',json={'circuit':graph,'source':attachment['path'],'preserve_connections':True})).content
            (out/(kind+'.zip')).write_bytes(data)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                reports=[json.loads(z.read(n)) for n in z.namelist() if n.endswith('verification.json')]
            assert reports and all(r['passed'] and r['native_readback'] for r in reports)
            exports[kind]=reports
    result={'passed':True,'project':project,'source':'Fresh S4-scan300 proposal, saved without manual correction',
            'provisional_terminals':len(provisional),'explicit_stub_ids':sum(p['pin'].startswith('STUB') for p in provisional),
            'typed_source_and_confidence_preserved':True,'faculty':fidelity,'native':exports}
    (out/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
