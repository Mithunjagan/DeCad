"""Read literal chip markings beside conventional U/IC captions.

This supplements component identification only. It never invents a part name,
changes a recognized value, or supplies pin connections from a caption.
"""
import math
import re


def literal_marking(text):
    upper = text.upper()
    return (bool(re.fullmatch(r'[A-Z0-9][A-Z0-9_.+/:~\-]{2,39}', upper))
            and sum(c.isalpha() for c in upper) >= 2 and any(c.isdigit() for c in upper)
            and not re.fullmatch(r'(?:U|IC|R|C|L|D|Q|J|P|S|Y|X|TP)\d{1,5}[A-H]?', upper)
            and not re.fullmatch(r'[\d.]+[KMRUNPFTGHV]+', upper))


def inside(box, x, y, inset=0):
    return box[0] + inset <= x <= box[2] - inset and box[1] + inset <= y <= box[3] - inset


def visible_pin_ends(box, segments, tolerance):
    """Distinct wire ends at this outline whose other ends lie outside it."""
    ends = []
    for segment in segments:
        a, b = segment.ends()
        for (x, y), other in ((a, b), (b, a)):
            if not inside(box, x, y, -tolerance) or inside(box, *other, -tolerance):
                continue
            if min(abs(x-box[0]), abs(x-box[2]), abs(y-box[1]), abs(y-box[3])) > tolerance:
                continue
            if not any(math.hypot(x-px, y-py) <= tolerance for px, py in ends):
                ends.append((x, y))
    return ends


def external_connectors(observations, recovered_bodies, char_height):
    """A port name inside an identified IC is not another connector.

    P0.02 and P1.04 are common MCU pin-function labels. They resemble the
    external P1-04 references read elsewhere on a drawing. Only confidently
    recovered bodies supply this exclusion; border and external text remain.
    """
    return [(token, ref, pin) for token, ref, pin in observations
            if not any(inside(body, token.cx, token.cy, .4*char_height)
                       for body in recovered_bodies)]


def recover(tokens, boxes, segments, char_height, components, anchors):
    """Return (reference, original literal marking, body box) with unique evidence.

    A caption above a visible body has a reference followed by one aligned value
    line; an interior caption must be inset from the pin-name columns. At least
    two external pin wires corroborate the outline. Existing nonempty values
    and ambiguous captions remain untouched.
    """
    ch = char_height
    references = [token for token in tokens if token.conf >= .9 and not token.vertical
                  and re.fullmatch(r'(?:U|IC)\d{1,3}[A-H]?', token.text.upper())]
    markings = [token for token in tokens if token.conf >= .9 and not token.vertical and literal_marking(token.text)]
    supported = [box for box in boxes if min(box[2]-box[0], box[3]-box[1]) >= 3*ch
                 and len(visible_pin_ends(box, segments, .55*ch)) >= 2]
    results = {}
    for ref_token in references:
        ref = ref_token.text.upper()
        if components.get(ref, 'UNKNOWN') not in ('', 'UNKNOWN'):
            continue
        choices = []
        for box in supported:
            if any(other != ref and inside(box, x, y) for other, x, y, _ in anchors):
                continue
            interior = inside(box, ref_token.cx, ref_token.cy)
            above = (0 < box[1] - ref_token.cy <= 4*ch and
                     abs(ref_token.cx-(box[0]+box[2])/2) <= max(ch, .25*(box[2]-box[0])))
            if not (interior or above):
                continue
            for marking in markings:
                if marking is ref_token or abs(marking.cx-ref_token.cx) > 1.1*ch:
                    continue
                if any(other != ref and components.get(other, '').upper() == marking.text.upper()
                       and math.hypot(x-marking.cx, y-marking.cy) < 3*ch for other, x, y, _ in anchors):
                    continue
                if not .4*ch <= marking.cy-ref_token.cy <= 2.2*ch:
                    continue
                if interior:
                    if not (inside(box, marking.x0, marking.y0, ch) and inside(box, marking.x1, marking.y1, ch)):
                        continue
                elif marking.y1 > box[1] + .2*ch or box[1]-marking.y1 > 2*ch:
                    continue
                choices.append((marking.text, box))
        if len({value for value, _ in choices}) == 1:
            value, box = min(choices, key=lambda pair:(pair[1][2]-pair[1][0])*(pair[1][3]-pair[1][1]))
            results.setdefault(ref, []).append((value, box))
    return [(ref, options[0][0], options[0][1]) for ref, options in sorted(results.items())
            if len({value for value, _ in options}) == 1]


def side_captions(tokens,boxes,segments,ch):
    """Recognize a unique literal caption left of a verified IC outline.

    Some ICs print their reference and marking at the left, rather than above.
    An internal OCR alias cannot own that same body or an imaginary sub-body.
    """
    result=[]
    for box in boxes:
        if len(visible_pin_ends(box,segments,.55*ch))<4:continue
        refs=[t for t in tokens if t.conf>=.95 and re.fullmatch(r'(?:U|IC)\d{1,3}[A-H]?',t.text.upper())
              and 0<box[0]-t.x1<2*ch and box[1]+ch<t.cy<box[3]-ch]
        choices=[]
        for ref in refs:
            values=[t for t in tokens if t.conf>=.95 and literal_marking(t.text) and not t.vertical
                    and abs(t.x1-ref.x1)<ch and .4*ch<t.cy-ref.cy<2.2*ch and t.x1<box[0]]
            if len(values)==1:choices.append((ref.text.upper(),values[0].text.upper(),box))
        if len(choices)==1:result.append(choices[0])
    return result
