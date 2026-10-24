import asyncio
import json
import subprocess
from pathlib import Path
import pytest
from app import ingestion, ocr_runtime as runtime
from app.engine import OperationError


@pytest.fixture
def configured(tmp_path, monkeypatch):
    python = tmp_path / 'python.exe'; python.write_bytes(b'fixture')
    monkeypatch.setenv('STATE_ROOT', str(tmp_path))
    monkeypatch.setenv('S2SDN_OCR_PYTHON', str(python))
    monkeypatch.setenv('S2SDN_OCR_DEVICE', 'cuda')
    return tmp_path


def test_cuda_configuration_does_not_claim_execution(configured):
    status = runtime.runtime_status()
    assert status['worker_exists'] and not status['gpu_verified']
    assert status['device'] == 'unverified'


def test_gpu_worker_result_validated_and_cpu_downgrade_rejected(configured, monkeypatch):
    calls = []
    from app import orcad_library
    monkeypatch.setattr(orcad_library, 'active', lambda: configured / 'user' / '.libraries')
    def worker(args, **kwargs):
        request = json.loads(kwargs['input']); calls.append((args, kwargs))
        assert request['library_store'] == str(configured / 'user' / '.libraries')
        Path(request['result']).write_text(json.dumps({'circuit': {'components': [{'ref': 'U1', 'value': '74LS00'}]},
                                                     'runtime': {'gpu_verified': False}}))
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(runtime.subprocess, 'run', worker)
    with pytest.raises(OperationError, match='did not confirm CUDA'):
        runtime.extract_digital(configured / 'sheet.png')
    assert calls[0][0][1:] == ['-m', 'app.ocr_worker']
    assert not calls[0][1].get('shell') and calls[0][1]['env']['S2SDN_OCR_DEVICE'] == 'cuda'
    assert runtime.runtime_status()['state'] == 'failed'
    assert not list(configured.glob('ocr-job-*'))


def test_worker_failure_and_timeout_never_apply_or_silently_fallback(configured, monkeypatch):
    def failed(args, **kwargs):return subprocess.CompletedProcess(args, 1, '', 'CUDA initialization failed')
    monkeypatch.setattr(runtime.subprocess, 'run', failed)
    with pytest.raises(OperationError, match='CUDA initialization failed'):
        runtime.extract_digital(configured / 'sheet.png')
    def timeout(args, **kwargs):raise subprocess.TimeoutExpired(args, 1200)
    monkeypatch.setattr(runtime.subprocess, 'run', timeout)
    with pytest.raises(OperationError, match='timed out'):
        runtime.extract_digital(configured / 'sheet.png')
    assert runtime.runtime_status()['state'] == 'failed'


def test_changed_configuration_discards_previous_gpu_confirmation(configured, monkeypatch):
    device, python = runtime.settings()
    runtime.record({'requested': device, 'configured_python': python, 'gpu_verified': True, 'device': 'cuda'})
    assert runtime.runtime_status()['gpu_verified']
    monkeypatch.setenv('S2SDN_OCR_DEVICE', 'cpu')
    assert not runtime.runtime_status()['gpu_verified']


@pytest.mark.parametrize('mode', ['digital', 'auto'])
def test_real_ingestion_modes_dispatch_to_configured_worker(configured, monkeypatch, mode):
    calls = []
    def found(path):
        calls.append(path)
        return ingestion.Circuit(components=[{'ref': 'U1', 'value': '74LS00'}],
            nets=[{'name': 'SIG', 'nodes': [{'ref': 'U1', 'pin': '1'}]}])
    monkeypatch.setattr(runtime, 'extract_digital', found)
    image = configured / 'sheet.png'
    result = asyncio.run(ingestion.extract_image(image, mode))
    assert calls == [image] and result.components[0].ref == 'U1'


def test_cpu_mode_keeps_working_without_worker(configured, monkeypatch):
    from app import digital_vision as dv
    monkeypatch.setenv('S2SDN_OCR_DEVICE', 'cpu')
    monkeypatch.setattr(dv, 'extract', lambda *a: ingestion.Circuit(components=[{'ref': 'R1', 'value': '1K'}]))
    from app import ocr_worker
    monkeypatch.setattr(ocr_worker, 'session_providers', lambda _: {'reader': ['CPUExecutionProvider']})
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: pytest.fail('CPU mode started a worker'))
    assert runtime.extract_digital(configured / 'sheet.png').components[0].ref == 'R1'
    assert runtime.runtime_status()['device'] == 'cpu'


def test_auto_mode_does_not_hide_cuda_failure_with_discrete_cpu_recognizer(configured, monkeypatch):
    def failed(path):raise OperationError('CUDA runtime failed')
    monkeypatch.setattr(runtime, 'extract_digital', failed)
    with pytest.raises(OperationError, match='CUDA runtime failed'):
        asyncio.run(ingestion.extract_image(configured / 'sheet.png', 'auto'))


def test_worker_recognition_failure_is_distinct_from_cuda_failure(configured, monkeypatch):
    def failed(args, **kwargs):
        request = json.loads(kwargs['input'])
        runtime.record({**request, 'state': 'failed', 'error_kind': 'recognition',
                        'gpu_verified': True, 'error': 'No legible part references.'})
        return subprocess.CompletedProcess(args, 1, '', '')
    monkeypatch.setattr(runtime.subprocess, 'run', failed)
    with pytest.raises(runtime.RecognitionError, match='No legible part references'):
        runtime.extract_digital(configured / 'sheet.png')


def test_unverified_gpu_failure_cannot_claim_to_be_a_recognition_failure(configured, monkeypatch):
    def failed(args, **kwargs):
        request = json.loads(kwargs['input'])
        runtime.record({**request, 'state': 'failed', 'error_kind': 'recognition',
                        'gpu_verified': False, 'error': 'CUDA was not initialized.'})
        return subprocess.CompletedProcess(args, 1, '', '')
    monkeypatch.setattr(runtime.subprocess, 'run', failed)
    with pytest.raises(OperationError, match='CUDA was not initialized'):
        runtime.extract_digital(configured / 'sheet.png')


def test_worker_preserves_only_the_source_users_library_context(configured, monkeypatch):
    from app.ocr_worker import workspace_library_store
    workspace = configured / 'workspaces'; mine = workspace / 'alice' / '.libraries'; mine.mkdir(parents=True)
    (workspace / 'bob' / '.libraries').mkdir(parents=True)
    monkeypatch.setenv('WORKSPACE_ROOT', str(workspace))
    assert workspace_library_store({'path': str(workspace / 'alice' / 'project' / 'references' / 'scan.png')}) == mine
    assert workspace_library_store({'path': str(configured / 'elsewhere' / 'scan.png')}) is None
    with pytest.raises(ValueError, match='Invalid workspace library'):
        workspace_library_store({'library_store': str(workspace / 'bob')})
