"""Recover a separately outlined IC hidden by an enclosing wire rectangle."""
from app import digital_vision as dv


def test_remote_anchor_does_not_consume_another_closed_ic():
    outer, body = (0, 0, 400, 2000), (0, 900, 300, 1100)
    part = dv.Token('TC123456', .85, 100, 930, 250, 960)
    anchors = [('U17', 200, 100, outer)]
    assert dv.unclaimed_body(part, outer, [outer, body], anchors, {outer: 20, body: 10}, 30) == body


def test_recovery_requires_a_distinct_unoccupied_body_with_pin_ends():
    outer, body = (0, 0, 400, 2000), (0, 900, 300, 1100)
    part = dv.Token('AM1234', .9, 100, 930, 250, 960)
    anchor = ('U17', 200, 100, outer)
    assert dv.unclaimed_body(part, outer, [outer], [anchor], {outer: 20}, 30) == outer
    assert dv.unclaimed_body(part, outer, [outer, body], [anchor], {outer: 20, body: 1}, 30) == outer
    assert dv.unclaimed_body(part, outer, [outer, body], [anchor, ('U18', 200, 1000, body)],
                             {outer: 20, body: 10}, 30) == outer


def test_nearby_anchor_and_unknown_body_keep_the_original_assignment():
    outer, body = (0, 0, 400, 2000), (0, 900, 300, 1100)
    part = dv.Token('74F123', .9, 100, 930, 250, 960)
    assert dv.unclaimed_body(part, outer, [outer, body], [('U17', 200, 1000, outer)],
                             {outer: 20, body: 10}, 30) == outer
    assert dv.unclaimed_body(part, None, [body], [], {body: 10}, 30) is None
