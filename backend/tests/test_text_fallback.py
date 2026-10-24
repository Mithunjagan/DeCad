from types import SimpleNamespace
import numpy as np
from app.text_fallback import choose, decode, Reader


def test_confident_baseline_is_retained_without_candidate_inference():
    session=SimpleNamespace(run=lambda *_: (_ for _ in ()).throw(AssertionError('Unexpected fallback inference')))
    reader=Reader(session,'AB',.6,.95,'hash')
    assert reader.read(np.zeros((1,1,32,16)),('A',.6))==('A',.6)


def test_low_confidence_baseline_requires_strong_candidate():
    assert choose(('A',.59),('B',.949),.6,.95)==('A',.59)
    assert choose(('A',.59),('B',.95),.6,.95)==('B',.95)
    assert choose(None,('B',.96),.6,.95)==('B',.96)
    assert choose(('A',.3),('B',float('nan')),.6,.95)==('A',.3)


def test_fallback_failure_keeps_original_reading():
    session=SimpleNamespace(run=lambda *_: (_ for _ in ()).throw(RuntimeError('Unavailable')))
    assert Reader(session,'AB',.6,.95,'hash').read(None,('A',.4))==('A',.4)


def test_ctc_decode_collapses_repeats_and_keeps_separated_characters():
    logits=np.full((5,3),-20.0)
    for row,label in enumerate((1,1,0,1,2)):logits[row,label]=20
    assert decode(logits,'AB')[0]=='AAB'
    assert decode(np.full((2,3),np.nan),'AB') is None


def test_fallback_rejects_untrained_pin_and_net_label_outputs(monkeypatch):
    from app import text_fallback
    reader = Reader(SimpleNamespace(run=lambda *_: [np.zeros((1,1,3))]), 'AB', .6, .95, 'hash')
    baseline = ('old', .4)
    for value in ('77', 'SIS', 'UI', 'LUI', 'CS1', 'U18'):
        monkeypatch.setattr(text_fallback, 'decode', lambda *_, value=value: (value, .999))
        assert reader.read(None, baseline) == baseline
        assert reader.read(None, baseline, scope='part') == baseline
    for scope in ('pin', 'net', 'reference', None):
        assert reader.read(None, baseline, scope=scope) == baseline


def test_fallback_accepts_only_the_requested_supported_field(monkeypatch):
    from app import text_fallback
    reader = Reader(SimpleNamespace(run=lambda *_: [np.zeros((1,1,3))]), 'AB', .6, .95, 'hash')
    baseline = ('old', .4)
    for value, scope in (('5V', 'quantity'), ('0.25A', 'quantity'), ('74F244', 'part')):
        monkeypatch.setattr(text_fallback, 'decode', lambda *_, value=value: (value, .999))
        assert reader.read(None, baseline, scope=scope) == (value, .999)
        assert reader.read(None, baseline, scope='part' if scope=='quantity' else 'quantity') == baseline
