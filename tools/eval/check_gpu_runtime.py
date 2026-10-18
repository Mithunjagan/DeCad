"""Run with the configured GPU Python: compare CPU/CUDA OCR and prove CUDA kernels.

This is a runtime check, not an end-to-end schematic accuracy benchmark.
"""
import json
import os
from pathlib import Path
import sys
import time
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import digital_vision as dv
from app.ocr_worker import session_providers

out = ROOT / 'backend/.state/codex-20261018/gpu-runtime'
out.mkdir(parents=True, exist_ok=True)
assert dv.use_gpu(), 'Configured Python cannot initialize CUDA.'
reader = dv.ocr_engine()
import onnxruntime as ort

holders = [dv._OCR.text_det.infer, dv._OCR.text_cls.infer, dv._OCR.text_rec.session]
for i, holder in enumerate(holders):
    old = holder.session
    options = old.get_session_options()
    options.enable_profiling = True
    options.profile_file_prefix = str(out / f'cuda-{i}')
    holder.session = ort.InferenceSession(old._model_path, sess_options=options,
        providers=[('CUDAExecutionProvider', dv.CUDA_OPTIONS), 'CPUExecutionProvider'])
image = np.full((160, 640, 3), 255, np.uint8)
cv2.putText(image, 'U43 IDT7210L', (24, 62), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 2, cv2.LINE_AA)
cv2.putText(image, 'R14 1K00 SPWE6', (24, 125), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
start = time.monotonic()
gpu, _ = reader(image)
gpu_seconds = time.monotonic() - start
providers = session_providers(dv)
profiles = [Path(h.session.end_profiling()) for h in holders]
counts = {}
for profile in profiles:
    for event in json.loads(profile.read_text()):
        provider = event.get('args', {}).get('provider')
        if provider:
            counts[provider] = counts.get(provider, 0) + 1
assert counts.get('CUDAExecutionProvider', 0) > 0, counts
from rapidocr_onnxruntime import RapidOCR
cpu_reader = RapidOCR(det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False)
start = time.monotonic(); cpu, _ = cpu_reader(image); cpu_seconds = time.monotonic() - start
gpu_text = [row[1] for row in gpu]; cpu_text = [row[1] for row in cpu]
assert gpu_text == cpu_text, (gpu_text, cpu_text)
assert any('IDT7210L' in t for t in gpu_text), gpu_text
dv.text_model(); providers = session_providers(dv)
assert all('CUDAExecutionProvider' in p for p in providers.values()), providers
result = {'passed': True, 'cuda_kernel_events': counts, 'providers': providers,
          'cpu_text': cpu_text, 'gpu_text': gpu_text,
          'gpu_seconds': gpu_seconds, 'cpu_seconds': cpu_seconds,
          'scope': 'OCR runtime/crop parity; no new schematic accuracy claim'}
(out / 'probe.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2), flush=True)
