"""Fresh CPU reference for the app's saved GPU S1 design. No training or user edits."""
import os
os.environ['S2SDN_OCR_DEVICE'] = 'cpu'
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / 'backend'), str(root / 'tools/eval')]
from app import digital_vision as dv, orcad_capture as oc, orcad_library
from run_eval import score, read_dsn, norm_ref, GT_DIR, SAMPLES

out = root / 'backend/.state/codex-20261018/gpu-runtime'
orcad_library.activate(root / 'backend/workspaces/local')
image = SAMPLES / 'Sample 1.jpg.jpeg'
start = time.monotonic()
found = dv.extract(image, root / 'backend/.state')
elapsed = time.monotonic() - start
graph = found.model_dump(exclude={'warnings'})
(out / 'S1-cpu-proposal.json').write_text(found.model_dump_json(indent=2))
folder = out / 'S1-cpu'; folder.mkdir(exist_ok=True)
_, status = oc.save_to_project(folder, 'S1-cpu', graph, root / 'backend/.state')
parts, pins = read_dsn(next((folder / 'orcad').glob('*.DSN')))
values = {norm_ref(c['ref']): c['value'] for c in graph['components'] if norm_ref(c['ref']) in parts}
cpu = score(json.loads((GT_DIR / 'S1.json').read_text()), parts, pins, values)
gpu = json.loads((out / 'S1-app-score.json').read_text())
passed = all(gpu[k] >= cpu[k] for k in ['parts_found', 'values_ok', 'pins_exact']) and gpu['parts_spurious'] <= cpu['parts_spurious']
result = {'passed': passed, 'cpu_seconds': elapsed, 'gpu_seconds': json.loads((out / 'app-result.json').read_text())['runtime']['runtime']['elapsed_seconds'],
          'cpu': cpu, 'gpu': gpu, 'dsn_passed': status['passed'],
          'scope': 'S1 no-regression check only; no new full recognition gate'}
(out / 'S1-comparison.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2), flush=True)
assert passed, 'GPU result regressed against the fresh CPU S1 reference.'
