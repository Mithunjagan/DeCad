"""Run existing real evaluators under the same profile as the FastAPI backend."""
import runpy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.pipeline_profile import configure

if __name__=='__main__':
    config=configure()
    script=sys.argv.pop(1)
    if script not in ('recognition_gate','native_recognition_gate','run_eval','library_gate'):
        raise SystemExit('Unknown evaluation script.')
    print('Pipeline:',config['profile'],config['profile_sha256'],flush=True)
    runpy.run_path(str(Path(__file__).with_name(script+'.py')),run_name='__main__')
