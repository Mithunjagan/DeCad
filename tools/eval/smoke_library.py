"""Workspace-library smoke test against the running native backend (start-native.ps1):
add an existing Capture design, footprints and a part map to the library, then convert a blueprint
and check that the generated .DSN uses the library parts and carries PCB footprints.

  python tools/eval/smoke_library.py "path/to/Sample 4.jpg.jpeg" path/to/design.DSN [footprint files...] [--api URL]
"""
import argparse, io, json, time, zipfile
from pathlib import Path
import httpx

ap = argparse.ArgumentParser()
ap.add_argument('blueprint')
ap.add_argument('library', nargs='+', help='.DSN / .OLB / footprints / .csv / .zip to add first')
ap.add_argument('--api', default='http://127.0.0.1:8100')
a = ap.parse_args()
with httpx.Client(base_url=a.api, timeout=900) as c:
    c.get('/auth/dev').raise_for_status()
    for f in map(Path, a.library):
        r = c.post('/library/upload', params={'name': f.name}, content=f.read_bytes())
        print('add', f.name, r.status_code, r.json())
    r = c.post('/library/partmap', json={'key': '74F174', 'footprint': 'soic16'})
    print('map 74F174 -> soic16', r.status_code)
    lib = c.get('/library').json()
    print('library:', len(lib['symbols']), 'symbol libs,', len(lib['designs']), 'designs,', len(lib['footprints']),
          'footprint files,', len(lib['partmap']), 'mappings,', lib['catalog'], 'footprints available')
    print('footprint search dip14:', [i['name'] for i in c.get('/library/footprints', params={'q': 'dip14'}).json()['items'][:5]])
    for d in lib['designs']:
        print('design', d['name'], 'preview', c.get(f"/library/designs/{d['name']}/preview.svg").status_code)
    pid = f'libsmoke-{int(time.time())}'
    c.post('/projects', json={'name': pid}).raise_for_status()
    img = Path(a.blueprint)
    up = c.post(f'/projects/{pid}/attachments', params={'name': img.name.replace(' ', '_')}, content=img.read_bytes())
    up.raise_for_status()
    t = time.time()
    r = c.post(f'/projects/{pid}/orcad/auto', json={'attachment': up.json()['path']})
    print('orcad/auto', r.status_code, f'{time.time() - t:.0f} s')
    r.raise_for_status()
    st = r.json()['status']
    print('verified', st['passed'], '|', st['components'], 'parts,', st['checked_pins'], 'pins,', st['nets'], 'nets')
    print('footprints', json.dumps(st['footprints']))
    print('workspace libraries used', st['user_libraries'])
    z = zipfile.ZipFile(io.BytesIO(c.get(f'/projects/{pid}/orcad/download').content))
    print('download:', z.namelist())
    print('project', pid)
