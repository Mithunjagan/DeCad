import io, zipfile
import pytest
from app import orcad_capture as oc, orcad_library as ol
from app.engine import OperationError

CATALOG = {'res400': 'OrCAD PCB library', 'cap196': 'OrCAD PCB library', 'dip14_3': 'OrCAD PCB library',
           'dip16_3': 'OrCAD PCB library', 'dip24_6': 'OrCAD PCB library', 'din96abcv': 'OrCAD PCB library',
           'conn50': 'OrCAD PCB library', 'soic16': 'uploaded', 'blkcon100vhtm2oew20040': 'OrCAD PCB library'}


@pytest.fixture
def store(tmp_path):
    ol.activate(tmp_path)
    return ol.active()


def test_csv_part_map_with_header_and_lookup_order(store):
    n = ol.import_csv(store, b'Part Number,PCB Footprint,Symbol\n74F174,soic16,\nU7,dip24_6,MyParts.olb:BIGCHIP\n,ignored,\n')
    assert n == 2
    assert ol.lookup({'ref': 'U7', 'value': '74F174'})['footprint'] == 'dip24_6'      # reference wins
    assert ol.lookup({'ref': 'U9', 'value': '74f174'})['footprint'] == 'soic16'        # then part number, any case
    assert ol.lookup({'ref': 'U9', 'value': 'X'}, package='74F174')['footprint'] == 'soic16'
    assert ol.lookup({'ref': 'U9', 'value': 'X'}) is None


def test_csv_without_header_and_mapping_edits(store):
    assert ol.import_csv(store, b'R5,res400\n') == 1
    ol.set_mapping(store, 'r5', 'res500')
    assert [r['footprint'] for r in ol.part_map(store)] == ['res500']
    with pytest.raises(OperationError):ol.set_mapping(store, 'U1', '', 'not-a-symbol')
    ol.delete_mapping(store, 'R5')
    assert ol.part_map(store) == []


def test_footprint_resolution_order(store):
    ol.set_mapping(store, '74F174', 'soic16')
    assert ol.footprint_for({'ref': 'U1', 'value': '74F174'}, '74F174', 16, 'DIP16', CATALOG) == ('soic16', 'part map')
    assert ol.footprint_for({'ref': 'U2', 'value': '74F08'}, '74F08', 14, 'DIP10014W300L800', CATALOG) == ('DIP10014W300L800', 'symbol library')
    assert ol.footprint_for({'ref': 'U3', 'value': '74F08'}, '74F08', 14, '', CATALOG)[0] == 'dip14_3'
    assert ol.footprint_for({'ref': 'U4', 'value': 'X'}, 'PART_U4', 23, '', CATALOG)[0] == 'dip24_6'  # odd count rounds up; 24 pin 600 mil
    assert ol.footprint_for({'ref': 'R1', 'value': '10k'}, 'R', 2, '', CATALOG)[0] == 'res400'
    assert ol.footprint_for({'ref': 'P1', 'value': 'CONNECTOR'}, 'DIN96', 96, '', CATALOG)[0] == 'din96abcv'
    assert ol.footprint_for({'ref': 'J1', 'value': 'CONNECTOR'}, 'CON40A', 40, '', CATALOG)[0] == 'blkcon100vhtm2oew20040'
    assert ol.footprint_for({'ref': 'J2', 'value': 'CONNECTOR'}, 'CON7', 7, '', CATALOG) == ('', 'none')  # not in the catalog: never invent one


def test_upload_rejects_unknown_files_and_bad_archives(store):
    with pytest.raises(OperationError):ol.add_file(store, 'notes.txt', b'x', oc)
    with pytest.raises(OperationError):ol.add_file(store, 'lib.zip', b'not a zip', oc)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('fp/soic16.psm', b'psm'); z.writestr('fp/soic16.dra', b'dra'); z.writestr('fp/pad60.pad', b'pad')
        z.writestr('__MACOSX/fp/._soic16.psm', b'junk'); z.writestr('readme.txt', b'skip'); z.writestr('map.csv', b'U1,soic16\n')
    added = ol.add_file(store, 'kit.zip', buf.getvalue(), oc)
    kinds = sorted(a['kind'] for a in added)
    assert kinds == ['footprints', 'footprints', 'footprints', 'partmap', 'skipped']
    assert sorted(p.name for p in (store / 'footprints').iterdir()) == ['pad60.pad', 'soic16.dra', 'soic16.psm']
    # the placeable footprint and every padstack ship with a design that uses it
    assert [p.name for p in ol.footprint_files({'SOIC16'})] == ['pad60.pad', 'soic16.dra', 'soic16.psm']
    assert ol.footprint_files({'dip14_3'}) == []  # nothing uploaded is used: ship nothing
    ol.remove(store, 'footprints', 'soic16.dra')
    assert not (store / 'footprints' / 'soic16.dra').exists()


def test_safe_names_cannot_escape_the_store(store):
    assert ol.safe_name('..\\..\\evil.olb') == 'evil.olb'
    assert ol.safe_name('a/b/c d.DSN') == 'c d.DSN'
    with pytest.raises(OperationError):ol.safe_name('..')


def test_verify_reads_placed_footprints():
    dump = 'PART U1 U1A 74F08 dip14_3\nPIN U1 1 X\nPART R1 R1 10k {}\nPIN R1 1 X\nDONE\n'
    mapping = {'U1': {'package': '74F08', 'match': 'part number'}, 'R1': {'package': 'R', 'match': 'generic symbol'}}
    rep = oc.verify(dump, {('U1', '1'): 'X', ('R1', '1'): 'X'}, mapping)
    assert rep['passed'] and rep['placed_footprints'] == {'U1': 'dip14_3'}


def test_project_file_lists_every_library():
    opj = oc.project_file('D.DSN', ['DECAD_GENERATED.OLB', 'libraries\\Mine.olb'])
    assert '.\\DECAD_GENERATED.OLB' in opj and '.\\libraries\\Mine.olb' in opj and '.\\d.dsn' in opj
    assert oc.project_file('D.DSN', 'ONE.OLB').count('Schematic Library') == 1
