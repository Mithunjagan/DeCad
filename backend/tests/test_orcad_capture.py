import io, json, zipfile
import pytest
from app import orcad_capture as oc


def test_universal_named_singletons_are_labeled_and_anonymous_pins_stay_bare():
    from app import orcad_route as rt
    from app.orcad_wire_gaps import endpoints
    from test_orcad_route import page
    pg=page();pins={('U1','1'):'SIGNAL',('U2','1'):'SIGNAL',('U1','3'):'VDD',
                   ('U2','3'):'BUS_17',('U3','1'):'N$1'}
    wires,summary=rt.route(pg,pins,oc._place,require_wires=True)
    stubs=[w for w in wires if w[4] in ('VDD','BUS_17')]
    assert len(stubs)==2 and all(abs(w[0]-w[2])+abs(w[1]-w[3])==20 for w in stubs)
    pg.update(wires=[w[:4] for w in wires],aliases=[{'name':w[4],'x':w[5],'y':w[6]} for w in wires if w[4]])
    assert summary['unlabelled_loose_ends']==0 and endpoints(pg)['passed']
    assert rt.verify_visible_wires(pg,pins)['passed']
    assert not any(w[4]=='N$1' for w in wires)


@pytest.mark.parametrize('name',['N$1','NET1','UNCONNECTED','N00027','N_17'])
def test_fallback_names_do_not_legalize_a_dangling_wire(name):
    from app.orcad_wire_gaps import endpoints
    pg={'parts':[{'pins':[{'hx':10,'hy':10}]}],'wires':[[10,10,30,10]],
        'aliases':[{'name':name,'x':30,'y':10}]}
    assert endpoints(pg)['unlabelled_loose_ends']==1


def test_license_checkout_retries_only_before_session_creation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    calls, sleeps = [], []

    def run(*args, **kwargs):
        calls.append(args)
        if len(calls) < 3:
            return SimpleNamespace(returncode=1, stdout='',
                stderr='ERROR(ORDBDLL-1017): License not found: DboTclHelper_sCreateSession')
        return SimpleNamespace(returncode=0, stdout='DONE', stderr='')

    monkeypatch.setattr(oc.subprocess, 'run', run)
    monkeypatch.setattr(oc.time, 'sleep', sleeps.append)
    assert oc._run(tmp_path, 'orcad_dump.tcl', tmp_path / 'sample.DSN') == 'DONE'
    assert len(calls) == 3 and sleeps == [1, 1]
    calls.clear()
    monkeypatch.setattr(oc.subprocess, 'run', lambda *a, **kw:
        calls.append(a) or SimpleNamespace(returncode=1, stdout='', stderr='License not found after a write'))
    with pytest.raises(oc.OperationError):
        oc._run(tmp_path, 'orcad_writer.tcl', 'data.tcl')
    assert len(calls) == 1


def test_net_aliases_are_capture_safe_and_unique():
    g = {'nets': [{'name': 'BB[16]', 'nodes': []}, {'name': 'BB_16_', 'nodes': []}, {'name': '0', 'nodes': []}, {'name': 'A B', 'nodes': []}]}
    a = oc.net_aliases(g)
    assert a == {'BB[16]': 'BB_16_', 'BB_16_': 'BB_16__2', '0': 'N0', 'A B': 'A_B'}


def test_tcl_word_quotes_special_characters():
    assert oc.tcl_word('R1') == 'R1'
    assert oc.tcl_word('') == '{}'
    assert oc.tcl_word('CAP NP') == '"CAP NP"'
    assert oc.tcl_word('D:\\lib\\x.olb') == '"D:\\\\lib\\\\x.olb"'
    assert oc.tcl_word('a[b]$c') == '"a\\[b\\]\\$c"'


def test_verify_detects_wrong_and_missing_pins():
    dump = 'PART R1 R1 10k\nPIN R1 1 VIN\nPIN R1 2 GND\nPART U1 U1A 74F08\nPIN U1 1 X\nPIN U1 14 VCC\nDONE\n'
    mapping = {'R1': {'package': 'R', 'match': 'generic symbol'}, 'U1': {'package': '74F08', 'match': 'part number'}}
    ok = oc.verify(dump, {('R1', '1'): 'VIN', ('R1', '2'): 'GND', ('U1', '1'): 'X'}, mapping)
    assert ok['passed'] and ok['implicit_power_pins'] == ['U1.14=VCC']
    bad = oc.verify(dump, {('R1', '1'): 'VOUT', ('U1', '9'): 'X'}, mapping)
    assert not bad['passed'] and len(bad['errors']) == 2


def test_tcl_list_parser():
    assert oc._tcl_list('PART R1 {R1} {CAP NP}') == ['PART', 'R1', 'R1', 'CAP NP']
    assert oc._tcl_list('PIN U1 1 {}') == ['PIN', 'U1', '1', '']


@pytest.mark.skipif(not oc.available(), reason='OrCAD Capture is not installed')
def test_native_dsn_round_trip(tmp_path):
    g = {'components': [{'ref': 'V1', 'value': '5', 'library': 'Simulation_SPICE:VDC'},
                        {'ref': 'R1', 'value': '10k', 'library': 'Device:R'}, {'ref': 'R2', 'value': '10k', 'library': 'Device:R'},
                        {'ref': 'U1', 'value': '74F08', 'library': ''}],
         'nets': [{'name': 'VIN', 'nodes': [{'ref': 'V1', 'pin': '1'}, {'ref': 'R1', 'pin': '1'}]},
                  {'name': 'VOUT', 'nodes': [{'ref': 'R1', 'pin': '2'}, {'ref': 'R2', 'pin': '1'}, {'ref': 'U1', 'pin': '12'}]},
                  {'name': 'GND', 'nodes': [{'ref': 'V1', 'pin': '2'}, {'ref': 'R2', 'pin': '2'}, {'ref': 'U1', 'pin': '1'}]}]}
    data, report = oc.export('t', g, tmp_path)
    assert report['passed'] and report['checked_pins'] == 8
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert 't.DSN' in names and 'verification.json' in names


def test_generated_symbol_names_and_pins():
    assert oc.generated_name({'ref': 'U7', 'value': 'xyz-9000'}) == 'XYZ-9000'
    assert oc.generated_name({'ref': 'U7', 'value': 'UNKNOWN'}) == 'PART_U7'
    assert oc.generated_pins(['3', '14']) == [str(i) for i in range(1, 15)]
    assert oc.generated_pins(['5']) == ['1', '2', '3', '4', '5', '6']
    assert oc.generated_pins(['Q', 'CLK']) == ['CLK', 'Q']


def test_svg_draws_parts_wires_and_aliases():
    pages = [{'name': 'PAGE1', 'width': 1000, 'height': 800, 'globals': [],
              'parts': [{'ref': 'R1', 'value': '10k', 'x': 100, 'y': 100, 'rotation': 0, 'mirror': 0,
                         'vectors': [['BOX', 0, 0, 20, 40]],
                         'pins': [{'number': '1', 'name': '1', 'hx': 110, 'hy': 90, 'sx': 110, 'sy': 100, 'dot': False, 'clock': False}]}],
              'wires': [[110, 90, 110, 60]], 'aliases': [{'name': 'VIN', 'x': 110, 'y': 60}]}]
    out = oc.svg(pages, 'T')
    assert out.startswith('<svg') and 'R1' in out and '10k' in out and 'VIN' in out and '<rect x="100" y="100" width="20" height="40"' in out


@pytest.mark.skipif(not oc.available(), reason='OrCAD Capture is not installed')
def test_unknown_parts_get_generated_symbols(tmp_path):
    g = {'components': [{'ref': 'U1', 'value': 'NOTAREALPART1'}, {'ref': 'R1', 'value': '1k', 'library': 'Device:R'}],
         'nets': [{'name': 'A', 'nodes': [{'ref': 'U1', 'pin': '3'}, {'ref': 'R1', 'pin': '1'}]},
                  {'name': 'B', 'nodes': [{'ref': 'U1', 'pin': '8'}, {'ref': 'R1', 'pin': '2'}]}]}
    data, status = oc.save_to_project(tmp_path, 'g', g, tmp_path)
    assert status['passed'] and status['generated_symbols'] == ['NOTAREALPART1'] and status['rendered_parts'] == 2
    assert (tmp_path / 'orcad' / 'preview.svg').is_file() and (tmp_path / 'orcad' / oc.GENERATED_LIB).is_file()
    assert not list((tmp_path / 'orcad').glob('*.DSNlck'))
    assert oc.project_status(tmp_path)['design'] == 'g.DSN'
    # Capture opens the project straight into the design instead of asking for a project type.
    opj = (tmp_path / 'orcad' / 'g.opj').read_text()
    assert '(File ".\\g.dsn"' in opj and f'(File ".\\{oc.GENERATED_LIB}"' in opj


@pytest.mark.skipif(not oc.available(), reason='OrCAD Capture is not installed')
def test_export_drops_recognition_noise_instead_of_failing(tmp_path):
    # 74F08 pin 7 is its fixed GND pin; pin 1 is listed on two nets; pin 99 does not exist.
    g = {'components': [{'ref': 'U1', 'value': '74F08'}, {'ref': 'R1', 'value': '1k', 'library': 'Device:R'}],
         'nets': [{'name': 'A', 'nodes': [{'ref': 'U1', 'pin': '1'}, {'ref': 'R1', 'pin': '1'}, {'ref': 'U1', 'pin': '7'}]},
                  {'name': 'B', 'nodes': [{'ref': 'U1', 'pin': '1'}, {'ref': 'R1', 'pin': '2'}, {'ref': 'U1', 'pin': '99'}]}]}
    data, report = oc.export('n', g, tmp_path)
    assert report['passed']
    text = ' '.join(report['corrections'])
    assert 'U1 pin 1 was on A and B' in text and 'U1 pin 7 removed' in text and 'U1 pin 99 removed' in text



@pytest.mark.skipif(not oc.available(), reason='OrCAD Capture is not installed')
def test_positioned_dsn_centres_orientation_overlap_and_bottom_strip(tmp_path, monkeypatch):
    from app import orcad_route as rt
    monkeypatch.setenv('DSN_LAYOUT', 'source')          # exact source positions (compaction is the default)
    graph = {'sheet_aspect': 1.5,
             'components': [{'ref': 'R1', 'value': '1k', 'x': .2, 'y': .1},
                            {'ref': 'R2', 'value': '1k', 'x': .8, 'y': .5},
                            {'ref': 'R3', 'value': '1k', 'x': .2, 'y': .1},
                            {'ref': 'R4', 'value': '1k'}],
             'nets': [{'name': 'A', 'nodes': [{'ref': 'R1', 'pin': '1'}, {'ref': 'R2', 'pin': '1'}]}]}
    _, status = oc.save_to_project(tmp_path, 'positions', graph, tmp_path)
    assert status['passed']
    page = oc.drawing(tmp_path / 'orcad/positions.DSN')[0]
    assert page['width'] > page['height']
    assert abs(page['width'] / page['height'] - 1.5) < .03
    preview = (tmp_path / 'orcad/preview.svg').read_text(encoding='utf-8')
    assert f'viewBox="0 0 {page["width"]} {page["height"]}"' in preview
    boxes = {p['ref']: rt._body_box(p, oc._place) for p in page['parts']}
    centres = {r: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for r, b in boxes.items()}
    assert abs(centres['R1'][0] - 1500) <= 10 and abs(centres['R1'][1] - 900) <= 10
    assert abs(centres['R2'][0] - 5100) <= 10 and abs(centres['R2'][1] - 3300) <= 10
    assert centres['R3'] != centres['R1']
    assert boxes['R4'][1] > max(boxes[r][3] for r in ('R1', 'R2', 'R3'))
    for i, a in enumerate(boxes.values()):
        for b in list(boxes.values())[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


def test_compact_dsn_keeps_arrangement_without_overlap(tmp_path):
    """Default layout: the source arrangement packed together, never overlapping."""
    from app import orcad_route as rt
    graph = {'sheet_aspect': 1.5,
             'components': [{'ref': 'R1', 'value': '1k', 'x': .2, 'y': .1},
                            {'ref': 'R2', 'value': '1k', 'x': .8, 'y': .5},
                            {'ref': 'R3', 'value': '1k', 'x': .2, 'y': .1},
                            {'ref': 'R5', 'value': '1k', 'x': .8, 'y': .1},
                            {'ref': 'R4', 'value': '1k'}],
             'nets': [{'name': 'A', 'nodes': [{'ref': 'R1', 'pin': '1'}, {'ref': 'R2', 'pin': '1'}]}]}
    _, status = oc.save_to_project(tmp_path, 'compact', graph, tmp_path)
    assert status['passed']
    page = oc.drawing(tmp_path / 'orcad/compact.DSN')[0]
    assert page['width'] < oc.SOURCE_SCALE and page['height'] < oc.SOURCE_SCALE / 1.5
    boxes = {p['ref']: rt._body_box(p, oc._place) for p in page['parts']}
    assert set(boxes) == {'R1', 'R2', 'R3', 'R4', 'R5'}
    centre = lambda r: ((boxes[r][0] + boxes[r][2]) / 2, (boxes[r][1] + boxes[r][3]) / 2)
    assert centre('R1')[0] < centre('R5')[0] and centre('R5')[1] < centre('R2')[1]   # left/right, above/below kept
    for i, a in enumerate(boxes.values()):
        for b in list(boxes.values())[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])
