import numpy as np
from app import digital_vision as dv
from app import orcad_capture as oc


def test_pin_numbers_repair_ocr_confusions():
    assert dv.as_number('11') == '11'
    assert dv.as_number('1!') == '11'
    assert dv.as_number('1!1') == '111'          # impossible pins are removed later by the library check
    assert dv.as_number('O7') == '07'
    assert dv.as_number('YD') is None
    assert dv.as_number('0') is None


def test_word_runs_split_on_wide_gaps_only():
    mask = np.zeros((10, 60), np.uint8)
    mask[:, 0:8] = 255; mask[:, 11:19] = 255     # one word: 3 px gap
    mask[:, 40:50] = 255                         # next word: 21 px gap
    assert dv._runs(mask, 0, 10) == [(0, 19), (40, 50)]
    assert dv._runs(mask, 1, 2) == [(0, 10)]


def test_reference_normalization():
    assert dv.normalize_ref('U15') == 'U15'
    assert dv.normalize_ref('UO7') == 'U07'
    assert dv.normalize_ref('NAMUT15') is None
    assert dv.normalize_ref('R5') == 'R5'


def test_segment_distance_and_bridge():
    s = dv.Seg(0, 10, 100, 10, 2.0, True)
    assert s.dist(50, 13) == 3 and s.dist(110, 10) == 10
    page = dv.Page(gray=None, binary=None, hlines=None, vlines=None, text=np.zeros((5, 5), np.uint8))
    merged = dv._bridge([dv.Seg(0, 10, 100, 10, 2, True), dv.Seg(110, 11, 200, 11, 2, True), dv.Seg(400, 10, 500, 10, 2, True)], page)
    assert [(m.x0, m.x1) for m in merged] == [(0, 200), (400, 500)]


def test_connector_pins_map_din96_rows():
    assert oc.connector_package(['B12', 'C5']) == ('Connector.olb', 'DIN96')
    assert oc.connector_package(['22', '40']) == ('Connector.olb', 'CON40A')
    assert oc.connector_pin('DIN96', 'A1') == '1'
    assert oc.connector_pin('DIN96', 'B12') == '44'
    assert oc.connector_pin('DIN96', 'C32') == '96'
    assert oc.connector_pin('CON40A', '7') == '7'


def test_part_number_repair_needs_a_unique_library_match():
    index = {'74F08': [], '74F32': [], '74LS85': [], '74LS86': []}
    assert oc.correct_value('74508', index) == '74F08'
    assert oc.correct_value('74LS8X', index) == '74LS8X'   # two candidates: left for review
    assert oc.correct_value('74F32', index) == '74F32'


def test_tied_wire_labels_use_the_printed_baseline_independent_of_order():
    wire = dv.Seg(0, 100, 300, 100, 2, True)
    above = ('DATA5', dv.Token('DATA5', .85, 120, 80, 160, 102))
    below = ('DATA4', dv.Token('DATA4', .99, 120, 100, 160, 120))
    assert dv.choose_wire_label([above, below], wire) == 'DATA5'
    assert dv.choose_wire_label([below, above], wire) == 'DATA5'
    # A real majority continues to beat a single geometrically better reading.
    assert dv.choose_wire_label([above, below, below], wire) == 'DATA4'


def test_tied_vertical_wire_labels_use_the_right_edge():
    wire = dv.Seg(100, 0, 100, 300, 2, False)
    left = ('BUS7', dv.Token('BUS7', .85, 80, 120, 102, 160, True))
    right = ('BUS6', dv.Token('BUS6', .99, 100, 120, 120, 160, True))
    assert dv.choose_wire_label([right, left], wire) == 'BUS7'


def test_pin_evidence_repairs_a_clipped_bus_header_without_extending_outliers():
    toks = [dv.Token('CC1:16]', .98, 0, 0, 100, 20), dv.Token('BB[1:16]', .98, 0, 30, 100, 50)]
    reads = [f'CC{i}' for i in range(11, 17)] + [f'BB{i}' for i in range(1, 17)] + ['BB97']
    vocab = dv.label_vocabulary(toks, reads)
    assert {'CC1', 'CC16', 'BB16'} <= vocab
    assert 'C16' not in vocab and 'BB96' not in vocab and 'BB97' not in vocab


def test_family_repairs_preserve_the_read_index_and_supported_names():
    vocab = {f'{p}{i}' for p in ('CC', 'BB', 'DD', 'AR', 'INADD', 'AAA', 'PRAD') for i in range(17)}
    for text, expected in [('C16', 'CC16'), ('B10', 'BB10'), ('TTTTTD4', 'DD4'), ('ART1', 'AR11')]:
        assert dv.snap_label(text, vocab) == expected
    assert dv.snap_label('C99', vocab) == 'C99'
    assert dv.strip_label_options(['C12', 'CC12'], vocab)[0] == 'CC12'
    assert dv.strip_label_options(['AAAS', 'AAA5'], vocab)[0] == 'AAA5'
    assert dv.strip_label_options(['INADD', '1NADD7'], vocab)[0] == 'INADD7'
    assert dv.strip_label_options(['INADDI0'], vocab)[0] == 'INADD10'
    assert dv.strip_label_options(['PRADS', 'PRAD5'], vocab)[0] == 'PRAD5'


def test_missing_row_index_requires_two_neighbours_and_an_existing_family_member():
    def row(axis, reading, options=None):
        return {'ref': 'U1', 'side': (1, 0), 'edge': 200, 'axis': axis,
                'labels': [reading], 'options': options or [reading], 'fixed': reading}
    vocab = {f'BB{i}' for i in range(1, 17)}
    rows = [row(60, 'BB'), row(100, 'BB7'), row(140, 'BB6')]
    dv.resolve_strip_rows(rows, vocab, 31)
    assert rows[0]['fixed'] == 'BB8'
    rows = [row(60, 'BB'), row(100, 'BB7'), row(140, 'BB6')]
    dv.resolve_strip_rows(rows, vocab - {'BB8'}, 31)
    assert rows[0]['fixed'] == 'BB'
    rows = [row(60, 'BBFLAG'), row(100, 'BB7'), row(140, 'BB6')]
    dv.resolve_strip_rows(rows, vocab, 31)
    assert rows[0]['fixed'] == 'BBFLAG'
    rows = [row(0, 'ADDA15'), row(40, 'ADDA14'), row(80, 'ADDA1', ['ADDA1', 'ADDA13'])]
    dv.resolve_strip_rows(rows, {f'ADDA{i}' for i in range(16)}, 31)
    assert rows[-1]['fixed'] == 'ADDA13'


def test_clipped_prefix_index_correction_requires_three_independent_rows():
    def row(axis, text, options=None):
        return {'ref':'U1','side':(0,1),'edge':200,'axis':axis,
                'labels':[text],'options':options or [text],'fixed':text}
    vocab={f'INST{i}' for i in range(12)} | {'INSI1'}
    rows=[row(0,'INST6'),row(40,'INS1',['INST1','INSI1']),row(80,'INST8'),row(120,'INST9')]
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[1]['fixed']=='INST7'
    rows=[row(0,'INST6'),row(40,'INS1',['INST1','INSI1']),row(80,'INST8')]
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[1]['fixed']=='INS1'
    rows=[row(0,'INST6'),row(40,'INST1'),row(80,'INST8'),row(120,'INST9')]
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[1]['fixed']=='INST1'
    rows=[row(0,'INST6'),row(40,'INS1',['INST1','INSI1']),row(80,'INST8'),row(120,'INST9')]
    rows[-1]['ref']='U2'
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[1]['fixed']=='INS1'
    rows=[row(0,'INST11',['INST11','INSI11']),row(40,'NST10',['INST10','TNST10']),
          row(120,'INST8'),row(160,'INS1',['INST1','INSI1'])]
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[-1]['fixed']=='INST7'
    rows[2]['options']=['INST8','INSI8']
    rows[-1]['fixed']='INS1'
    dv.resolve_strip_rows(rows,vocab,31)
    assert rows[-1]['fixed']=='INS1'


def test_split_pin_digit_requires_agreeing_readers_duplicate_number_and_row_family():
    rows = {'top':[(k,'U1',k*40) for k in range(4)], 'bottom':[(4,'U1',0)]}
    def original():
        return {0:('1',['7DATA6','7DATA6']),1:('12',['DATA3']),2:('14',['DATA4']),
                3:('16',['DATA5']),4:('1',['OUT0'])}
    reads=original()
    assert dv.recover_split_pin_digits(rows,reads)==[('U1','1','17')]
    assert reads[0]==('17',['DATA6']) and reads[4]==('1',['OUT0'])
    for change in ({0:('1',['7DATA6'])}, {0:('1',['7DATA6','2DATA6'])},
                   {0:('1',['8DATA6','8DATA6'])}, {3:('16',['OTHER5'])},
                   {4:('17',['OUT0'])}, {4:('2',['OUT0'])}):
        reads=original();reads.update(change)
        assert dv.recover_split_pin_digits(rows,reads)==[]
