"""Dispatch unchanged digital recognition to an explicitly configured local runtime.

KiCad's Python can keep its CPU-only dependencies; CUDA OCR runs in a separate
process and releases its GPU/RAM when finished. Never silently downgrade CUDA.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from .engine import OperationError, atomic_text

BASE = Path(__file__).resolve().parents[1]


def state_dir():
    return Path(os.getenv('STATE_ROOT', str(BASE / '.state'))).resolve()


def settings():
    device = os.getenv('S2SDN_OCR_DEVICE', 'auto').lower()
    if device not in ('auto', 'cuda', 'cpu'):
        raise OperationError('S2SDN_OCR_DEVICE must be auto, cuda, or cpu.')
    python = os.getenv('S2SDN_OCR_PYTHON', '').strip()
    return device, str(Path(python).resolve()) if python else None


def record(data):
    folder = state_dir(); folder.mkdir(parents=True, exist_ok=True)
    atomic_text(folder / 'ocr-runtime.json', json.dumps({**data, 'updated': time.time()}))


def runtime_status():
    device, python = settings()
    report = {}
    try:
        saved = json.loads((state_dir() / 'ocr-runtime.json').read_text())
        if saved.get('requested') == device and saved.get('configured_python') == python:
            report = saved
    except (OSError, ValueError, TypeError):
        pass
    return {'requested': device, 'worker_configured': bool(python),
            'worker_exists': bool(python and Path(python).is_file()),
            'device': 'unverified', 'state': 'idle', 'gpu_verified': False, **report}


def extract_digital(path):
    """Blocking call; ingestion already runs it in a thread under VISION_LOCK."""
    device, python = settings()
    started = time.time()
    base = {'requested': device, 'configured_python': python, 'started': started}
    if device == 'cpu' or not python:
        from . import digital_vision as dv
        if device == 'cuda' and not dv.use_gpu():
            raise OperationError('CUDA OCR is requested, but the backend has no CUDA runtime. Configure S2SDN_OCR_PYTHON with a verified GPU Python executable.')
        record({**base, 'state': 'running', 'device': 'unverified'})
        try:
            found = dv.extract(path, state_dir())
            from .ocr_worker import session_providers
            providers = session_providers(dv)
            gpu = bool(providers) and all('CUDAExecutionProvider' in p for p in providers.values())
            if device == 'cuda' and not gpu:
                raise OperationError('The backend did not confirm CUDA sessions; no circuit was applied.')
            record({**base, 'state': 'completed', 'device': 'cuda' if gpu else 'cpu',
                    'gpu_verified': gpu, 'providers': providers, 'elapsed_seconds': time.time() - started})
            return found
        except Exception as exc:
            record({**base, 'state': 'failed', 'error': str(exc)[:1000]})
            raise
    if not Path(python).is_file():
        raise OperationError('Configured OCR Python was not found. Correct S2SDN_OCR_PYTHON or explicitly select CPU mode.')
    record({**base, 'state': 'starting', 'device': 'unverified'})
    env = {**os.environ, 'S2SDN_OCR_DEVICE': device, 'PYTHONIOENCODING': 'utf-8',
           'OMP_NUM_THREADS': '2', 'STATE_ROOT': str(state_dir())}
    # No shell command, project writes, package installs, or network calls.
    with tempfile.TemporaryDirectory(prefix='ocr-job-', dir=state_dir()) as temp:
        result_path = Path(temp) / 'result.json'
        request = {**base, 'path': str(Path(path).resolve()), 'state': str(state_dir()),
                   'result': str(result_path)}
        from . import orcad_library
        active_library = orcad_library.active()
        request['library_store'] = str(active_library.resolve()) if active_library else None
        try:
            result = subprocess.run([python, '-m', 'app.ocr_worker'], cwd=BASE, env=env,
                                    input=json.dumps(request), capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=1200)
            if result.returncode or not result_path.is_file():
                report = runtime_status()
                detail = report.get('error') or result.stderr[-1200:] or 'Worker exited without a result.'
                raise OperationError('Local GPU recognition failed: ' + detail)
            from .ingestion import Circuit
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            found = Circuit.model_validate(payload['circuit'])
            if device == 'cuda' and not payload['runtime'].get('gpu_verified'):
                raise OperationError('The OCR worker did not confirm CUDA execution; no circuit was applied.')
            return found
        except (subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
            error = 'Local OCR worker timed out; no circuit was applied.' if isinstance(exc, subprocess.TimeoutExpired) else f'Local OCR worker failed: {exc}'
            record({**base, 'state': 'failed', 'error': error[:1000]})
            raise OperationError(error) from exc
        except OperationError as exc:
            record({**base, 'state': 'failed', 'error': str(exc)[:1000]})
            raise
