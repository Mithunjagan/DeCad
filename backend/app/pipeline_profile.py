"""One checked-in profile for API, native launcher and evaluation workers."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / 'backend/pipeline_profiles.json'


def profile():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8'))['hybrid_max_accuracy']


def configure(*, verify_checkpoint=True):
    """Profile owns recognition settings; unrelated environment settings survive.

    In particular a root .env selecting full-page vision cannot override this
    profile. Rejected OCR adapters never enter this pipeline.
    """
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'backend/.env')
    config = profile()
    checkpoint = ROOT / config['ocr_checkpoint']
    if verify_checkpoint:
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if digest != config['ocr_checkpoint_sha256']:
            raise ValueError('Production OCR checkpoint hash differs from the accepted profile.')
    os.environ.update(IMAGE_MODE=config['image_mode'], S2SDN_PIPELINE_PROFILE='hybrid_max_accuracy',
                      S2SDN_OCR_DEVICE=config['ocr_device'], S2SDN_TEXT_MODEL=str(checkpoint))
    os.environ['S2SDN_TEXT_FALLBACK_CONFIG'] = 'off'
    worker = ROOT / 'backend/.state/claude-20261018/gpu-venv/Scripts/python.exe'
    if not os.getenv('S2SDN_OCR_PYTHON') and worker.is_file():
        os.environ['S2SDN_OCR_PYTHON'] = str(worker)
    return {**config, 'profile': 'hybrid_max_accuracy',
            'profile_sha256': hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()}


def enabled():
    return os.getenv('S2SDN_PIPELINE_PROFILE') == 'hybrid_max_accuracy'
