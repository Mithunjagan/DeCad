"""Demo-path smoke test against the running native backend (start-native.ps1):
local login -> new project -> upload a schematic -> automatic recognition -> verified OrCAD .DSN ->
status, preview and download.

  python tools/eval/smoke_api.py "path/to/Sample 4.jpg.jpeg" [--api http://127.0.0.1:8100]
"""
import argparse, time
from pathlib import Path
import httpx

ap = argparse.ArgumentParser()
ap.add_argument('image')
ap.add_argument('--api', default='http://127.0.0.1:8100')
a = ap.parse_args()
img = Path(a.image)
with httpx.Client(base_url=a.api, timeout=900) as c:
    c.get('/auth/dev').raise_for_status()
    pid = f'smoke-{int(time.time())}'
    c.post('/projects', json={'name': pid}).raise_for_status()
    up = c.post(f'/projects/{pid}/attachments', params={'name': img.name.replace(' ', '_')}, content=img.read_bytes())
    up.raise_for_status()
    t = time.time()
    r = c.post(f'/projects/{pid}/orcad/auto', json={'attachment': up.json()['path']})
    print('orcad/auto', r.status_code, f'{time.time() - t:.0f} s')
    r.raise_for_status()
    j = r.json()
    print('status', {k: v for k, v in j['status'].items() if k not in ('corrections', 'substitutions', 'generated_symbols')})
    print('warnings', *j['warnings'][:4], sep='\n  ')
    st = c.get(f'/projects/{pid}/orcad').json()
    svg = c.get(f'/projects/{pid}/orcad/preview.svg')
    dl = c.get(f'/projects/{pid}/orcad/download')
    print('capture available', st['capture'], '| preview', svg.status_code, len(svg.content), 'bytes | download', dl.status_code, len(dl.content), 'bytes')
    print('project', pid)
