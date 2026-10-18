"""Prepare the supplied Qwen2.5-VL language-attention adapter for llama.cpp."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

import gguf
import requests
from safetensors.numpy import load_file

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'backend/.state/vision-model'
ADAPTER = ROOT.parents[1] / 'Jrk_Adapter/adapter'
if not (ADAPTER / 'adapter_model.safetensors').is_file():
    ADAPTER = ROOT / 'checkpoints/circuit-lora/adapter'
FILES = {
    'Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf': 4683072032,
    'mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf': 853119712,
}
REVISION = '508edd0afaa66bb9e9f40587acc2184f02daf1f6'
SHA256 = {
    'Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf': '9258bf05b12686d097ff3b6b18d968ab393649780aa2b3cd67fec43d50554392',
    'mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf': '2ddb555391bae966e412deab9e07b58afa18bcc06930ba0f1c78a3695ab9e506',
}


def verify_model(path):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != SHA256[path.name]:
        raise ValueError(f'Model checksum mismatch: {path.name}')


def download(name, size):
    target = DEST / name
    if target.exists() and target.stat().st_size == size:
        verify_model(target)
        print(f'Already downloaded: {name}', flush=True)
        return
    url = f'https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF/resolve/{REVISION}/{name}'
    parts = DEST / (name + '.parts')
    parts.mkdir(exist_ok=True)
    block_size = 64 * 1024**2
    blocks = [(start, min(start + block_size, size)) for start in range(0, size, block_size)]

    def fetch_block(block):
        start, end = block
        part = parts / str(start)
        for attempt in range(4):
            have = part.stat().st_size if part.exists() else 0
            if have == end - start:
                return have
            if have > end - start:
                raise ValueError('Invalid cached download block.')
            try:
                with requests.get(url, headers={'Range': f'bytes={start + have}-{end - 1}'}, stream=True, timeout=(20, 45)) as response:
                    response.raise_for_status()
                    expected_range = f'bytes {start + have}-{end - 1}/{size}'
                    if response.status_code != 206 or response.headers.get('Content-Range') != expected_range:
                        raise ValueError('Model server did not honor the requested byte range.')
                    with part.open('ab' if have else 'wb') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                if part.stat().st_size != end - start:
                    raise ValueError('Incomplete model download block.')
                return end - start
            except (requests.RequestException, ValueError) as error:
                print(f'Retry {attempt + 1}: {name} block {start}: {type(error).__name__}', flush=True)
                if attempt == 3:
                    raise
                time.sleep(2)

    completed = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(fetch_block, block) for block in blocks]
        for future in as_completed(futures):
            completed += future.result()
            print(f'{name}: {completed / size:.0%}', flush=True)
    combined = target.with_suffix('.gguf.complete')
    with combined.open('wb') as output:
        for start, end in blocks:
            with (parts / str(start)).open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    if combined.stat().st_size != size:
        raise ValueError('Incomplete assembled model.')
    with combined.open('rb') as source:
        if source.read(4) != b'GGUF':
            raise ValueError('Downloaded file is not GGUF.')
    combined.replace(target)
    verify_model(target)
    print(f'Download complete: {name}', flush=True)


def convert_adapter(adapter=ADAPTER, output=None):
    """Preserve every F32 attention tensor; reject adapters outside this exact layout."""
    output = output or DEST / 'circuit-adapter.gguf'
    config = json.loads((adapter / 'adapter_config.json').read_text(encoding='utf-8'))
    if config['base_model_name_or_path'] != 'Qwen/Qwen2.5-VL-7B-Instruct' or config['peft_type'] != 'LORA':
        raise ValueError('This converter requires the supplied Qwen2.5-VL-7B LoRA.')
    tensors = load_file(adapter / 'adapter_model.safetensors')
    names = gguf.get_tensor_name_map(gguf.MODEL_ARCH.QWEN2VL, 28)
    writer = gguf.GGUFWriter(output, 'qwen2vl')
    writer.add_type(gguf.GGUFType.ADAPTER)
    writer.add_string(gguf.Keys.Adapter.TYPE, 'lora')
    writer.add_float32(gguf.Keys.Adapter.LORA_ALPHA, float(config['lora_alpha']))
    writer.add_name('Supplied circuit Qwen2.5-VL-7B adapter')
    seen = set()
    for name, tensor in tensors.items():
        match = re.fullmatch(r'base_model\.model\.model\.language_model\.layers\.(\d+)\.self_attn\.([qkvo])_proj\.lora_([AB])\.weight', name)
        if not match or tensor.dtype.name != 'float32':
            raise ValueError(f'Unsupported adapter tensor: {name}')
        layer, projection, side = match.groups()
        mapped = names.get_name(f'model.layers.{layer}.self_attn.{projection}_proj.weight', try_suffixes=('.weight',))
        if mapped is None or int(layer) >= 28:
            raise ValueError(f'Unmapped adapter tensor: {name}')
        if len(tensor.shape) != 2 or tensor.shape[0 if side == 'A' else 1] != config['r']:
            raise ValueError(f'Unexpected adapter rank: {name}')
        seen.add((int(layer), projection, side))
        writer.add_tensor(mapped + '.lora_' + side.lower(), tensor)
    if seen != {(layer, projection, side) for layer in range(28) for projection in 'qkvo' for side in 'AB'}:
        raise ValueError('Adapter is missing attention tensors.')
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    report = {'base_model': config['base_model_name_or_path'], 'adapter_sha256': hashlib.sha256((adapter / 'adapter_model.safetensors').read_bytes()).hexdigest(), 'tensors': len(tensors), 'dtype': 'float32', 'lora_alpha': config['lora_alpha'], 'output': str(output)}
    output.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Converted all {len(tensors)} supplied adapter tensors without changing precision.', flush=True)
    return report


def configure():
    key_file = ROOT / 'backend/.state/vision-api-key'
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(32))
    settings = {
        'IMAGE_MODE': 'vision', 'VISION_MODEL': 'schematic2sdn-qwen-vl',
        'VISION_OLLAMA_URL': 'http://host.docker.internal:11436',
        'VISION_API_PROTOCOL': 'openai', 'VISION_API_KEY': key_file.read_text().strip(),
        'VISION_ADAPTER_ID': 'supplied-circuit-lora', 'VISION_TIMEOUT_SECONDS': '840',
        'VISION_MAX_TOKENS': '6000',
    }
    env_file = ROOT / '.env'
    lines = env_file.read_text(encoding='utf-8-sig').splitlines() if env_file.exists() else []
    for key, value in settings.items():
        lines = [line for line in lines if not line.startswith(key + '=')]
        lines.append(key + '=' + value)
    env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Configured the supplied adapter endpoint. API key saved locally; no credentials printed.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--configure-only', action='store_true')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    if not args.configure_only:
        convert_adapter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda item: download(*item), FILES.items()))
    if args.configure or args.configure_only:
        configure()
