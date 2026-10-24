import numpy as np
from app import digital_vision as dv


def drawing(bottom=True):
    ink = np.zeros((400, 1200), np.uint8)
    hlines, vlines = ink.copy(), ink.copy()
    vlines[200:301, 900] = 255
    vlines[200:301, 1100] = 255
    hlines[200, 900:1101] = 255
    if bottom:
        hlines[300, 900:1011] = 255  # a broken edge, over half the inner span
    page = dv.Page(ink, ink, hlines, vlines, ink, soft=ink)
    boxes = [(x, 0, x + 200, 100) for x in (0, 300, 600)]
    parts = [dv.Token('TC123456', .95, x + 40, 20, x + 100, 40) for x in (0, 300, 600)]
    parts.append(dv.Token('TC123456', .9, 940, 220, 1000, 240))
    return page, boxes, parts


def test_three_distinct_copies_and_four_edges_recover_a_broken_outline():
    page, boxes, parts = drawing()
    assert dv.repeated_part_boxes(page, parts, boxes, 10) == [(897, 197, 1103, 303)]


def test_repeated_label_cannot_invent_an_absent_edge():
    page, boxes, parts = drawing(bottom=False)
    assert dv.repeated_part_boxes(page, parts, boxes, 10) == []


def test_duplicate_readings_of_one_body_do_not_supply_three_independent_copies():
    page, boxes, parts = drawing()
    assert dv.repeated_part_boxes(page, [parts[0]] * 3 + [parts[-1]], boxes[:1], 10) == []


def test_value_orientation_and_confidence_must_match_the_template():
    page, boxes, parts = drawing()
    for field, value in [('text', 'TC123457'), ('vertical', True), ('conf', .3)]:
        original = getattr(parts[-1], field)
        setattr(parts[-1], field, value)
        assert dv.repeated_part_boxes(page, parts, boxes, 10) == []
        setattr(parts[-1], field, original)
    page.soft = None
    assert dv.repeated_part_boxes(page, parts, boxes, 10) == []
