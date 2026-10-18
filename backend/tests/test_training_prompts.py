import importlib.util, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'training' / f'{name}.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_training_prompts_match_inference_prompts():
    prompts = load('prompts')
    ingestion = (ROOT / 'backend/app/ingestion.py').read_text(encoding='utf-8')
    assert re.search(r"prompt='(Extract the electrical circuit.*?)'\n", ingestion).group(1) == prompts.USER
    assert prompts.SYSTEM in (ROOT / 'training/serve.py').read_text(encoding='utf-8')


def test_t4_profile_allows_fp16_and_matches_supplied_adapter_base():
    profiles = json.loads((ROOT / 'training/profiles.json').read_text())
    assert profiles['7b-t4']['fp16_allowed'] and not profiles['7b'].get('fp16_allowed')
    assert profiles['7b-t4']['model'] == profiles['7b']['model'] == 'Qwen/Qwen2.5-VL-7B-Instruct'
