#!/usr/bin/env python3
"""Pack everything a Colab GPU session needs into one zip: training code, the backend modules the
evaluator imports, prepared datasets and the supplied adapter to continue from."""
import argparse, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_FILES = ['finetune.py', 'serve.py', 'evaluate.py', 'dataset_tools.py', 'prompts.py', 'profiles.json', 'requirements-gpu.txt']
DATASETS = ['training/prepared_amsnet', 'training/prepared_samples']
ADAPTER = 'checkpoints/circuit-lora/adapter'


def files():
    for name in TRAINING_FILES:
        yield ROOT / 'training' / name
    yield ROOT / 'backend/requirements.txt'
    yield from (p for p in (ROOT / 'backend/app').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py', '.tcl'})
    for d in DATASETS + [ADAPTER]:
        if (ROOT / d).is_dir():
            yield from (p for p in (ROOT / d).rglob('*') if p.is_file())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=ROOT / 'colab' / 'Schematic2SDN_colab.zip')
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(a.output, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, 'Schematic2SDN/' + f.relative_to(ROOT).as_posix()); count += 1
    print(f'{a.output} ({count} files, {a.output.stat().st_size // 2**20} MiB)')


if __name__ == '__main__':
    main()
