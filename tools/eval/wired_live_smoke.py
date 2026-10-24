"""Export a source-layout wired copy of an existing saved review through the live API."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.observed_export import facts


def checked(response):
    response.raise_for_status()
    return response


def main(args):
    args.out.mkdir(exist_ok=True,parents=True)
    with httpx.Client(base_url='http://127.0.0.1:8100',timeout=900) as api:
        checked(api.get('/auth/dev'))
        original = checked(api.get(f'/projects/{args.source}/review')).json()
        graph = original['circuit']
        refresh=False
        if args.project in checked(api.get('/projects')).json():
            existing=api.get(f'/projects/{args.project}/review')
            if args.refresh_export and existing.status_code==200 and existing.json()['circuit']==graph:
                refresh=True
            existing_files=checked(api.get(f'/projects/{args.project}/files')).json()
            if not refresh and (not args.resume_empty or existing.status_code not in (404,422)
                    or set(existing_files)!={args.project+'.kicad_pro',args.project+'.kicad_sch'}):
                raise SystemExit('Choose an unused demonstration project name to preserve existing work.')
        else:
            checked(api.post('/projects',json={'name':args.project}))
        files = checked(api.get(f'/projects/{args.source}/files')).json()
        for filename in ([] if refresh else files):
            filename=filename.replace('\\','/')
            if filename.startswith('references/'):
                content=checked(api.get(f'/projects/{args.source}/file',params={'name':filename})).content
                checked(api.post(f'/projects/{args.project}/attachments',params={'name':Path(filename).name},content=content))
        if not refresh:
            checked(api.put(f'/projects/{args.project}/review',json={'circuit':graph}))
        download=checked(api.post(f'/projects/{args.project}/export/orcad-dsn',json={'circuit':graph,'preserve_connections':False}))
        (args.out/(args.project+'.zip')).write_bytes(download.content)
        design=checked(api.get(f'/projects/{args.project}/orcad')).json()['design']
        assert design['passed'] and design['routing']['all_connections_wired']
        assert design['routing']['visible_wire_verification']['passed']
        copied=checked(api.get(f'/projects/{args.project}/review')).json()
        assert facts(copied['circuit'])==facts(graph)
        assert checked(api.get(f'/projects/{args.source}/review')).json()==original
        report={'passed':True,'project':args.project,'source_project':args.source,
                'original_review_unchanged':True,'recognition_rerun':False,
                'zip_sha256':hashlib.sha256(download.content).hexdigest(),'design':design}
        (args.out/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='demosample1')
    parser.add_argument('--project',default='demosample1-wired')
    parser.add_argument('--out',type=Path,default=ROOT/'evidence/wired-orcad-20261024/live')
    parser.add_argument('--resume-empty',action='store_true')
    parser.add_argument('--refresh-export',action='store_true')
    main(parser.parse_args())
