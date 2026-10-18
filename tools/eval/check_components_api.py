"""Real API acceptance for unified components; creates/deletes one smoke project."""
import json
from pathlib import Path
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'backend/.state/codex-20261018/component-acceptance/cc0-source'
OUTPUT=ROOT/'backend/.state/codex-20261018/component-api'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url='http://127.0.0.1:8100',timeout=180) as client:
        def request(method,path,**kwargs):
            result=client.request(method,path,**kwargs)
            result.raise_for_status()
            return result
        request('GET','/auth/dev')
        pid='smoke-library-'+str(int(time.time()))
        location=None;created=False
        try:
            status=request('GET','/components/status').json()
            assert len(status['formats'])==12
            location=request('POST','/components/locations',json={'path':str(SOURCE),'source_license':{
                'name':'CC0-1.0','allow_import':True,'allow_redistribute':True}}).json()['id']
            scan=request('POST','/components/scan',json={'location':location}).json()
            assert not scan['errors'],scan
            symbols=request('GET','/components/search',params={'q':'DECAD-TEST-001'}).json()['items']
            footprint=next(i for i in request('GET','/components/search',params={'q':'TwoPad'}).json()['items'] if i['kind']=='footprint')
            symbol=symbols[0]
            checked=request('POST','/components/validate',json={'symbol':symbol['id'],'footprint':footprint['id']}).json()
            assert checked['cached'] and checked['validation']['pin_to_pad']=='verified'
            request('POST','/projects',json={'name':pid});created=True
            placed=request('POST',f'/projects/{pid}/components/place',json={'component':symbol['id'],'ref':'U1'}).json()
            assert placed['circuit']['components'][0]['ref']=='U1'
            preview=request('GET',f'/projects/{pid}/preview.svg')
            assert b'<svg' in preview.content
            acquired=request('POST',f'/projects/{pid}/components/acquire',json={'query':'Timer:NE555P','ref':'U2','external':False}).json()
            assert acquired['status']=='ready' and acquired['placement']['edit']['ref']=='U2'
            assert acquired['placement']['footprint'].startswith('DeCadUnified:')
            unchanged=request('GET',f'/projects/{pid}/file',params={'name':pid+'.kicad_sch'}).content
            duplicate=client.post(f'/projects/{pid}/components/acquire',json={'query':'Timer:NE555P','ref':'U2','external':False})
            assert duplicate.status_code==409
            assert request('GET',f'/projects/{pid}/file',params={'name':pid+'.kicad_sch'}).content==unchanged
            (OUTPUT/'placed-preview.svg').write_bytes(preview.content)
            for target in ('internal','kicad'):
                exported=request('GET',f'/components/export/{symbol["id"]}',params={'target':target})
                (OUTPUT/('component.'+('json' if target=='internal' else 'kicad_sym'))).write_bytes(exported.content)
            unsupported=client.get(f'/components/export/{symbol["id"]}',params={'target':'allegro'})
            assert unsupported.status_code==422 and 'no verified exporter' in unsupported.text
            report={'formats':status['formats'],'scan':scan,'symbol_id':symbol['id'],
                    'placement':placed,'acquisition':acquired,'duplicate_preserves_design':True,
                    'preview_bytes':len(preview.content),'unsupported_export':unsupported.json()}
            (OUTPUT/'report.json').write_text(json.dumps(report,indent=2))
            print('API: discovery/index, shared search, pin/pad validation/cache, real schematic placement, preview, internal/KiCad export, unsupported Allegro rejection passed')
        finally:
            if created:
                cleanup=request('DELETE',f'/projects/{pid}').json()
                assert pid not in request('GET','/projects').json()
                (OUTPUT/'cleanup.json').write_text(json.dumps(cleanup))
            if location:request('DELETE',f'/components/locations/{location}')


if __name__=='__main__':main()
