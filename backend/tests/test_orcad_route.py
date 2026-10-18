from app import orcad_capture as oc, orcad_route as rt


def box_part(ref, x, y, pins):
    """A 40x60 box part at (x, y) with pins (number, side, offset): left pins point -x, right pins +x."""
    out = []
    for num, side, off in pins:
        sx = x if side == 'L' else x + 40
        hx = sx - 30 if side == 'L' else sx + 30
        out.append({'number': num, 'name': num, 'hx': hx, 'hy': y + off, 'sx': sx, 'sy': y + off, 'dot': False, 'clock': False})
    return {'ref': ref, 'base': ref, 'value': 'X', 'x': x, 'y': y, 'rotation': 0, 'mirror': 0,
            'vectors': [['BOX', 0, 0, 40, 60]], 'pins': out}


def page():
    return {'name': 'PAGE1', 'width': 1200, 'height': 900, 'aliases': [], 'globals': [], 'wires': [],
            'parts': [box_part('U1', 200, 300, [('1', 'R', 10), ('2', 'R', 30), ('3', 'R', 50)]),
                      box_part('U2', 700, 300, [('1', 'L', 10), ('2', 'L', 30), ('3', 'L', 50)]),
                      box_part('U3', 450, 600, [('1', 'L', 20)])]}


def test_router_wires_nets_without_touching_other_nets():
    pin_net = {('U1', '1'): 'A', ('U2', '3'): 'A', ('U1', '3'): 'B', ('U2', '1'): 'B',
               ('U1', '2'): 'C', ('U2', '2'): 'C', ('U3', '1'): 'D'}
    wires, summary = rt.route(page(), pin_net, oc._place)
    assert summary['wired_nets'] == 3 and summary['labelled_nets'] == 1   # D has one pin: labelled stub

    for x1, y1, x2, y2, alias, ax, ay in wires:
        assert x1 == x2 or y1 == y2                                        # orthogonal only
    # endpoints of one net never lie on another net's wire
    r = rt.Router(page(), pin_net, oc._place)
    r.route()
    segs = {n: r.segments(n) for n in r.edges}
    def on(seg, p):
        (ax, ay), (bx, by) = seg
        return min(ax, bx) <= p[0] <= max(ax, bx) and min(ay, by) <= p[1] <= max(ay, by) and (ax == bx == p[0] or ay == by == p[1])
    for n, ss in segs.items():
        ends = {p for s in ss for p in s}
        for m, other in segs.items():
            if m != n:
                assert not any(on(s, p) for s in other for p in ends), (n, m)
    # every wired net reaches the hotspots of both of its pins (U1 right pins at x=270, U2 left pins at x=670)
    pins = {'A': [(27, 31), (67, 35)], 'B': [(27, 35), (67, 31)], 'C': [(27, 33), (67, 33)]}
    for n, hot in pins.items():
        ends = {p for s in segs[n] for p in s}
        assert set(hot) <= ends, (n, segs[n])


def test_source_placement_preserves_distances_and_missing_coordinates():
    comps = [{'ref': 'U1', 'x': 0.8, 'y': 0.10}, {'ref': 'U2', 'x': 0.2, 'y': 0.12},
             {'ref': 'U3', 'x': 0.5, 'y': 0.50}, {'ref': 'P1'}]
    positions = oc.placement(comps)
    assert positions['U1'][0] - positions['U2'][0] == 3600
    assert positions['U2'][1] - positions['U1'][1] == 120
    assert positions['U3'][1] - positions['U1'][1] == 2400
    assert 'P1' not in positions
    assert oc.placement([{'ref': 'U1'}, {'ref': 'U2'}, comps[0]]) == {'U1': positions['U1']}
