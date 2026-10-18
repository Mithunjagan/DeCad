"""OCR recovery and wiring inference in digital_vision: synthetic checks (no image, no OCR)."""
from app import digital_vision as dv


def test_misread_u_references():
    for text, ref in [('!84', 'U84'), ('L61', 'U61'), ('US8', 'U58'), ('089', 'U89'), ('C17', 'U17'), ('|59', 'U59'), ('u4', 'U4')]:
        assert dv.lost_u(text) == ref, text


def test_not_references():
    for text in ['U', 'Us', 'LO', 'ILL', 'IC', '0', 'D100', '0103', '89', '12', 'BB4']:
        assert dv.lost_u(text) is None, text
    assert dv.lost_u('89', bare=True) == 'U89'
    assert dv.lost_u('BB4', bare=True) is None        # a label inside a body is never U884


def test_blurred_s_has_both_readings():
    assert dv.lost_u_options('US5') == ['U55', 'U85']
    assert dv.lost_u_options('!84') == ['U84']


def test_family_repair_from_the_sheet():
    printed = {'74F174', '74F161', '74F240'}
    assert dv.same_family('74F!61', printed) == '74F161'
    assert dv.same_family('74F24U', printed) == '74F240'
    assert dv.same_family('745174', printed) == '74F174'
    assert dv.same_family('74S174', printed) == '74S174'       # a real family is kept
    assert dv.same_family('745999', printed) == '745999'       # no sheet evidence: unchanged
    assert dv.same_family('74F174', {'74F174', '74LS174'}) == '74F174'


def test_manufacturer_prefix_still_repaired():
    assert dv.part_prefix('Idf7210L') == 'IDT7210L'
    assert dv.part_prefix('74F244') == '74F244'


def test_pin_sequence_fills_unread_and_duplicated_pins():
    # one body edge at a 44 px pitch: 55 57 57 581 59 60 62 62 -> 55 56 57 58 59 60 61 62
    reads = {k: (n, None) for k, n in enumerate(['55', '57', '57', '581', '59', '60', '62', '62'])}
    rows = {'r': [(k, 'U43', 4112 + 44 * k) for k in range(8)]}
    dv.pin_sequences(rows, reads, 30.0)
    assert [reads[k][0] for k in range(8)] == ['55', '56', '57', '58', '59', '60', '61', '62']


def test_pin_sequence_keeps_unique_plausible_reads():
    # AM2910 top edge: 34 36 38 40 then 2 4 -- two runs, every reading unique: nothing changes
    nums = ['34', '36', '38', '40', '2', '4']
    reads = {k: (n, None) for k, n in enumerate(nums)}
    dv.pin_sequences({'r': [(k, 'U31', 2628 + 44 * k) for k in range(6)]}, reads, 30.0)
    assert [reads[k][0] for k in range(6)] == nums


def test_symbol_consensus_needs_agreeing_copies():
    ch = 30.0
    boxes = [(0, 0, 300, 600), (1000, 0, 1300, 600), (2000, 0, 2300, 600)]
    ends, reads, values = [], {}, {}
    pins = [('6', 60), ('5', 120), ('4', 180), ('3', 240)]
    for b, box in enumerate(boxes):
        values[box] = '74F194'
        for j, (n, dy) in enumerate(pins):
            k = (b, j); ends.append((k, box, box[0], box[1] + dy))
            reads[k] = (None if (b, j) == (2, 0) else n, None)
    dv.symbol_consensus(ends, reads, values, ch)
    assert reads[(2, 0)][0] == '6'
    # a different section with the same outline (74F244 halves) is never renumbered
    other = (3000, 0, 3300, 600); values[other] = '74F194'
    for j, n in enumerate(['17', '15', '13', '11']):
        ends.append(((3, j), other, other[0], other[1] + pins[j][1])); reads[(3, j)] = (n, None)
    dv.symbol_consensus(ends, reads, values, ch)
    assert [reads[(3, j)][0] for j in range(4)] == ['17', '15', '13', '11']


def test_outline_sliver_is_not_a_digit():
    import numpy as np
    strip = np.zeros((40, 200), np.uint8)
    strip[5:35, 100:118] = 255          # a digit glyph
    strip[5:35, 196:200] = 255          # a 4 px sliver of the body edge at the pin end (right)
    words = dv._strip_words(strip, 0, 40.0, reverse=True)
    assert words and words[0][1] <= 120


def test_lost_leading_i_joins_its_family():
    vocab = {f'INBU{k}' for k in range(16)}
    assert dv.snap_label('NBUI4', vocab) == 'INBU14'
    assert dv.snap_label('INBUO', vocab) == 'INBU0'
