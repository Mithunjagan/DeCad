"""Freeze all local recognizer helpers and optional library facts for a gate."""
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def snapshot():
    paths = [ROOT/'backend/app'/name for name in
             ('digital_vision.py', 'ic_caption.py', 'recognition_catalog.py', 'pin_crop_recovery.py', 'orcad_capture.py', 'text_fallback.py',
              'pipeline_profile.py', 'vector_pdf.py', 'normalization.py', 'roi_vision.py', 'catalog_pin_solver.py')]
    paths.append(ROOT/'backend/pipeline_profiles.json')
    paths.append(Path(os.getenv('S2SDN_COMPONENT_CATALOG') or ROOT/'backend/.state/recognition-catalog.sqlite'))
    result = {}
    for path in paths:
        digest = hashlib.sha256()
        if path.is_file():
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(block)
            result[str(path.resolve())] = digest.hexdigest()
        else:
            result[str(path.resolve())] = None
    return result
