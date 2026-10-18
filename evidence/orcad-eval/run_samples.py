"""Run the app's own pipeline on the sample sheets: recognition -> library check -> native OrCAD
.DSN -> reopen verification. Then score with score.py against the hand-made ground truth.

  backend/.venv/Scripts/python evidence/orcad-eval/run_samples.py <samples folder> <output folder> 1 2 3 4 5
  python evidence/orcad-eval/score.py evidence/orcad-eval/ground-truth/S1.json <output>/S1/recognized.json
"""
import json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.digital_vision import extract          # noqa: E402
from app import orcad_capture as oc              # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2]); state = ROOT / 'backend' / '.state'
for i in map(int, sys.argv[3:]):
    t = time.time(); d = out / f'S{i}'; d.mkdir(parents=True, exist_ok=True)
    try:
        g = extract(src / f'Sample {i}.jpg.jpeg', state).model_dump()
        (d / 'recognized.json').write_text(json.dumps(g, indent=1))
        _, st = oc.save_to_project(d, f'Sample{i}', {'components': g['components'], 'nets': [n for n in g['nets'] if n['nodes']]}, state)
        print(i, 'OK', round(time.time() - t), 's', st['components'], 'parts', st['checked_pins'], 'pins', 'passed', st['passed'], flush=True)
    except Exception as e:
        print(i, 'FAIL', repr(e)[:300], flush=True); traceback.print_exc()
