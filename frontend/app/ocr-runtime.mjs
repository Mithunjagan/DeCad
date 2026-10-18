export function ocrRuntimeLabel(runtime, active = false) {
  if (!runtime) return 'Checking OCR runtime';
  if (runtime.state === 'failed') return 'OCR runtime failed';
  if (runtime.state === 'starting') return 'Starting OCR runtime';
  if (active && runtime.state !== 'running') return 'Preparing recognition';
  if (runtime.gpu_verified && runtime.device === 'cuda') {
    if (runtime.state === 'running') {
      return runtime.stage === 'wiring' ? 'CUDA OCR · tracing connections' : runtime.stage === 'preprocessing' ? 'CUDA ready · preparing image' : 'CUDA OCR · reading text';
    }
    return 'Last OCR: NVIDIA CUDA';
  }
  if (runtime.device === 'cpu') return runtime.state === 'running' ? 'CPU recognition running' : 'Last OCR: CPU';
  if (runtime.requested === 'cpu') return 'CPU recognition selected';
  if (runtime.worker_configured) return 'GPU runtime configured · not yet verified';
  return 'Backend OCR · device not yet verified';
}
