import os
from app.pipeline_profile import configure, enabled, profile, ROOT


def test_profile_overrides_root_vision_drift_and_rejected_ocr_adapters(monkeypatch):
    for key in ('IMAGE_MODE','S2SDN_PIPELINE_PROFILE','S2SDN_OCR_DEVICE','S2SDN_TEXT_MODEL',
                'S2SDN_TEXT_FALLBACK_CONFIG','S2SDN_OCR_PYTHON'):
        monkeypatch.setenv(key, os.getenv(key,''))
    monkeypatch.setenv('IMAGE_MODE','vision')
    monkeypatch.setenv('S2SDN_TEXT_MODEL','rejected-adapter.onnx')
    monkeypatch.setenv('S2SDN_TEXT_FALLBACK_CONFIG','rejected-ocr.json')
    config=configure()
    assert enabled() and os.environ['IMAGE_MODE']=='hybrid_max_accuracy'
    assert os.environ['S2SDN_OCR_DEVICE']=='cuda'
    assert os.environ['S2SDN_TEXT_MODEL']==str(ROOT/config['ocr_checkpoint'])
    assert os.environ['S2SDN_TEXT_FALLBACK_CONFIG']=='off'
    assert config['roi_primary']['model']=='Qwen/Qwen3-VL-8B-Instruct'


def test_profile_file_contains_no_full_page_model_route():
    assert profile()['image_mode']=='hybrid_max_accuracy'
    assert profile()['roi_max_requests']<=12
