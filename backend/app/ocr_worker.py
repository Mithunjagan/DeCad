"""One local OCR job, launched by ocr_runtime; no web listener or project mutation."""
import json
import os
from pathlib import Path
import sys
import time


def session_providers(dv):
    sessions = {}
    if dv._OCR is not None:
        for name, holder in [('detector', getattr(dv._OCR.text_det, 'infer', None)),
                             ('classifier', getattr(dv._OCR.text_cls, 'infer', None)),
                             ('reader', getattr(dv._OCR.text_rec, 'session', None))]:
            session = getattr(holder, 'session', None)
            if session is not None:
                sessions[name] = session.get_providers()
    if dv._TEXT_MODEL:
        sessions['schematic_reader'] = dv._TEXT_MODEL.get_providers()
    return sessions


def workspace_library_store(request):
    if request.get('library_store'):
        store = Path(request['library_store']).resolve()
        if store.name != '.libraries':
            raise ValueError('Invalid workspace library location.')
        return store
    # Rolling upgrade: an already-running backend can still send the earlier
    # protocol. Recover context only from a source inside its exact workspace.
    workspace = Path(os.getenv('WORKSPACE_ROOT', str(Path(__file__).resolve().parents[1] / 'workspaces'))).resolve()
    source = Path(request['path']).resolve()
    if source.is_relative_to(workspace):
        parts = source.relative_to(workspace).parts
        if len(parts) >= 3:
            user = workspace / parts[0]; store = user / '.libraries'
            if store.is_dir() and not store.is_symlink() and store.resolve().parent == user:
                return store
    return None


def run(request):
    from . import digital_vision as dv
    from . import ocr_runtime as runtime
    base = {k: request[k] for k in ('requested', 'configured_python', 'started')}
    base['python'] = sys.executable
    # ContextVars cross asyncio.to_thread, but do not cross a Python process.
    # Preserve this request's uploaded libraries and explicit component mappings.
    store = workspace_library_store(request)
    if store:
        from . import orcad_library
        orcad_library.activate(store.parent)
    # Keep Windows DLL search handles alive for the whole job. Preloading uses
    # the existing Torch/NVIDIA DLLs; no large Torch import or package change.
    dll_handles = []
    try:
        import onnxruntime as ort
        if request['requested'] != 'cpu':
            import importlib.util
            spec = importlib.util.find_spec('torch')
            libraries = [os.getenv('S2SDN_CUDA_DLLS', '')]
            if spec and spec.submodule_search_locations:
                libraries.append(str(Path(list(spec.submodule_search_locations)[0]) / 'lib'))
            for directory in libraries:
                if directory and Path(directory).is_dir() and hasattr(os, 'add_dll_directory'):
                    dll_handles.append(os.add_dll_directory(directory))
            if hasattr(ort, 'preload_dlls'):
                ort.preload_dlls()
        runtime.record({**base, 'state': 'starting', 'device': 'unverified'})
        dv.ocr_engine()
        # Initialize the optional second reader too, so status covers every
        # installed OCR model, rather than just ORT's list of possible providers.
        dv.text_model()
        providers = session_providers(dv)
        gpu = all('CUDAExecutionProvider' in providers.get(n, []) for n in ('detector', 'classifier', 'reader'))
        if dv._TEXT_MODEL:
            gpu = gpu and 'CUDAExecutionProvider' in providers.get('schematic_reader', [])
        if request['requested'] == 'cuda' and not gpu:
            raise RuntimeError('CUDA sessions could not initialize. Check CUDA/cuDNN DLLs in the configured OCR environment. CPU fallback was rejected.')
        info = {**base, 'device': 'cuda' if gpu else 'cpu', 'gpu_verified': gpu,
                'providers': providers, 'onnxruntime': ort.__version__,
                'workspace_libraries': bool(store)}
        # Report actual pipeline entry points without changing their results.
        for name, stage in [('prepare', 'preprocessing'), ('tokens', 'ocr'), ('recognize', 'wiring')]:
            original = getattr(dv, name)
            def reporting(*args, _original=original, _stage=stage, **kwargs):
                runtime.record({**info, 'state': 'running', 'stage': _stage})
                return _original(*args, **kwargs)
            setattr(dv, name, reporting)
        runtime.record({**info, 'state': 'running', 'stage': 'preprocessing'})
        found = dv.extract(Path(request['path']), Path(request['state']))
        info.update(state='completed', elapsed_seconds=time.time() - request['started'])
        Path(request['result']).write_text(json.dumps({'circuit': found.model_dump(), 'runtime': info}), encoding='utf-8')
        runtime.record(info)
    except Exception as exc:
        runtime.record({**base, 'state': 'failed', 'device': 'unverified', 'error': str(exc)[:1000]})
        raise
    finally:
        for handle in dll_handles:
            handle.close()


if __name__ == '__main__':
    run(json.load(sys.stdin))
