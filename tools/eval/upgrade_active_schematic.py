"""Save the owned, active schematic with real KiCad and verify connectivity."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / 'backend'), str(root / 'desktop')]
os.environ.setdefault('KICAD_CLI', r'D:\KICAD\bin\kicad-cli.exe')
os.environ.setdefault('KICAD_SYMBOL_DIR', r'D:\KICAD\share\kicad\symbols')
from app.engine import Schematic
import native_host as host


def canonical(graph):
    return {
        'components': sorted((c['ref'], c['value'], c['footprint'], c['library']) for c in graph['components']),
        'nets': sorted((n['name'], sorted((p['ref'], p['pin']) for p in n['nodes'])) for n in graph['nets']),
    }


sessions = [json.loads(p.read_text()) for p in (root / 'backend/.state/native-desktop').glob('*/status.json')]
active = [s for s in sessions if not s.get('closed') and s.get('hwnd') and time.time() - s['updated'] < 5]
assert len(active) == 1, 'Expected exactly one active owned editor.'
session = active[0]
path = Path(session['path'])
assert path.stem in host.title(session['hwnd']), 'Editor is displaying another schematic.'
owner = host.wt.DWORD()
host.user32.GetWindowThreadProcessId(session['hwnd'], ct.byref(owner))
assert owner.value == session['editor_pid'], 'Editor process identity changed.'
folder = root / 'backend/.state/codex-20261018/format-upgrades' / (path.stem + '-' + str(time.time_ns()))
folder.mkdir(parents=True)
for source in (path, path.with_suffix('.kicad_pro')):
    if source.is_file():
        shutil.copy2(source, folder / source.name)
before = canonical(Schematic(path.parent).graph())
original = path.read_bytes()
host.user32.PostMessageW(session['hwnd'], 0x111, session['commands']['save'], 0)
deadline = time.monotonic() + 12
while path.read_bytes() == original and time.monotonic() < deadline:
    time.sleep(.2)
after = canonical(Schematic(path.parent).graph())
report = {'project': str(path.parent), 'backup': str(folder),
          'before_sha256': hashlib.sha256(original).hexdigest(),
          'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
          'version': re.search(r'\(version (\d+)\)', path.read_text()).group(1),
          'preserved': before == after, 'before': before, 'after': after}
(folder / 'verification.json').write_text(json.dumps(report, indent=2))
assert report['preserved'], 'Native conversion changed electrical connectivity; inspect preserved versions.'
assert report['version'] == '20260306', 'Expected the installed KiCad 10 native format.'
print(json.dumps({k: v for k, v in report.items() if k not in ('before', 'after')}))
