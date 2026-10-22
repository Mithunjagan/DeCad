import numpy as np
from app import digital_vision as dv


def examples():
    layer = np.zeros((500, 900), np.uint8)
    page = dv.Page(layer, layer, layer, layer, layer, soft=layer)
    boxes = [(x, 0, x + 200, 400) for x in (0, 300, 600)]
    toks = [dv.Token('74F374', .95, x + 100, 180, x + 130, 300, True) for x in (0, 300)]
    toks.append(dv.Token('PAFNA', .5, 700, 180, 730, 300, True))
    return page, boxes, toks


def test_second_reader_needs_two_crops_and_two_matching_independent_bodies(monkeypatch):
    page, boxes, toks = examples()
    calls = []
    monkeypatch.setattr(dv, 'read_text_model', lambda *args, **kwargs: calls.append(args) or ('74F374', .96))
    assert dv.reread_part_tokens(page, toks, boxes, 26) == [('PAFNA', '74F374')]
    assert toks[-1].text == '74F374' and len(calls) == 2
    assert calls[0][1:5] != calls[1][1:5]


def test_readable_part_number_is_preserved_even_if_other_copies_use_a_different_part(monkeypatch):
    page, boxes, toks = examples()
    toks[-1].text = '74F240'
    def unexpected(*args):
        raise AssertionError('Readable values must not be submitted for replacement.')
    monkeypatch.setattr(dv, 'read_text_model', unexpected)
    assert dv.reread_part_tokens(page, toks, boxes, 26) == []
    assert toks[-1].text == '74F240'


def test_uncertain_or_inconsistent_reader_does_not_replace_a_value(monkeypatch):
    for predictions in [[('74F374', .99), ('74F273', .99)], [('74F374', .89)] * 2, [None] * 2]:
        page, boxes, toks = examples()
        iterator = iter(predictions)
        monkeypatch.setattr(dv, 'read_text_model', lambda *args, **kwargs: next(iterator))
        assert dv.reread_part_tokens(page, toks, boxes, 26) == []
        assert toks[-1].text == 'PAFNA'


def test_value_shape_and_repeated_geometry_must_all_have_support(monkeypatch):
    monkeypatch.setattr(dv, 'read_text_model', lambda *args, **kwargs: ('74F374', .99))
    page, boxes, toks = examples()
    assert dv.reread_part_tokens(page, toks[1:], boxes, 26) == []  # one independent template
    boxes[-1] = (600, 0, 800, 200)
    assert dv.reread_part_tokens(page, toks, boxes, 26) == []  # incompatible body
    page, boxes, toks = examples()
    monkeypatch.setattr(dv, 'read_text_model', lambda *args, **kwargs: ('74F999', .99))
    assert dv.reread_part_tokens(page, toks, boxes, 26) == []  # value not read elsewhere
