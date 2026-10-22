"""Optional, integrity-checked OCR fallback; the existing reader remains primary."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_CACHE = {}


def decode(logits, characters):
    logits = np.asarray(logits)
    if logits.ndim != 2 or logits.shape[1] != len(characters)+1 or not np.isfinite(logits).all():
        return None
    values = np.exp(logits-logits.max(-1, keepdims=True))
    probabilities = values/values.sum(-1, keepdims=True)
    out, previous, confidence = [], 0, []
    for label, probability in zip(probabilities.argmax(-1), probabilities.max(-1)):
        if label != previous and label:
            out.append(characters[label-1]); confidence.append(float(probability))
        previous = label
    return (''.join(out), min(confidence)) if out else None


def choose(baseline, candidate, baseline_max, candidate_min):
    if baseline is not None and baseline[1] >= baseline_max:
        return baseline
    if candidate and candidate[0] and math.isfinite(candidate[1]) and candidate[1] >= candidate_min:
        return candidate
    return baseline


@dataclass
class Reader:
    session: object
    characters: str
    baseline_max: float
    candidate_min: float
    model_sha256: str

    def read(self, image, baseline, *, scope='quantity'):
        # This real-data run covers quantities and printed 74-series part names.
        # It was not trained to supply references, physical pins or net labels.
        patterns = {'quantity': r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)[VAFH]',
                    'part': r'74[A-Z]{0,5}\d{1,4}[A-Z0-9]*'}
        if scope not in patterns:
            return baseline
        if baseline is not None and baseline[1] >= self.baseline_max:
            return baseline
        try:
            candidate = decode(self.session.run(None, {'image':image})[0][0], self.characters)
            if candidate is None or re.fullmatch(patterns[scope], candidate[0]) is None:
                return baseline
            return choose(baseline, candidate, self.baseline_max, self.candidate_min)
        except Exception:
            # A fallback failure cannot erase a valid baseline reading.
            return baseline


def load(baseline_path, characters, gpu):
    setting = os.getenv('S2SDN_TEXT_FALLBACK_CONFIG', '').strip()
    if setting.lower() in ('off','none','0'): return None
    config_path = Path(setting) if setting else ROOT/'checkpoints/schematic-ocr/fallback.json'
    try:
        stamp = (str(config_path.resolve()), config_path.stat().st_mtime_ns,
                 str(baseline_path.resolve()), baseline_path.stat().st_mtime_ns, gpu)
        if stamp in _CACHE: return _CACHE[stamp]
        config = json.loads(config_path.read_text(encoding='utf-8'))
        if not config.get('enabled'): return None
        model = (config_path.parent/config['model']).resolve()
        baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        model_hash = hashlib.sha256(model.read_bytes()).hexdigest()
        if baseline_hash != config['baseline_sha256'] or model_hash != config['model_sha256']:
            raise ValueError('OCR fallback weights differ from the measured model pair.')
        low, high = config['baseline_max_confidence'], config['candidate_min_confidence']
        if not 0 <= low <= 1 or not 0 <= high <= 1 or config['characters'] != characters:
            raise ValueError('Invalid OCR fallback configuration.')
        import onnxruntime as ort
        providers = ([('CUDAExecutionProvider', {'arena_extend_strategy':'kSameAsRequested',
                        'cudnn_conv_algo_search':'HEURISTIC','gpu_mem_limit':256*2**20})] if gpu else [])
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model), sess_options=options, providers=providers+['CPUExecutionProvider'])
        if gpu and 'CUDAExecutionProvider' not in session.get_providers():
            raise ValueError('Fallback did not initialize CUDA.')
        inputs, outputs = session.get_inputs(), session.get_outputs()
        if len(inputs)!=1 or inputs[0].name!='image' or len(outputs)!=1 or outputs[0].shape[-1]!=len(characters)+1:
            raise ValueError('Fallback model does not match the schematic OCR protocol.')
        reader = Reader(session,characters,low,high,model_hash)
        _CACHE.clear(); _CACHE[stamp]=reader
        return reader
    except Exception:
        return None
