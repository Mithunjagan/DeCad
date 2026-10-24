import io
import json
import zipfile

import pytest

from app import orcad_capture as oc
from app.observed_export import compare,write_kicad


def graph():
    return {'components':[{'ref':'J1','value':'Header'},{'ref':'U1','value':'UNKNOWN'},
                           {'ref':'R1','value':'unconnected'}],
            'nets':[{'name':'/RESET','nodes':[{'ref':'J1','pin':'B12'},{'ref':'U1','pin':'0'}]},
                    {'name':'a','nodes':[{'ref':'J1','pin':'00'}]},
                    {'name':'A','nodes':[{'ref':'U1','pin':'01'}]}]}


def test_complete_comparison_rejects_extra_connections_and_changed_values():
    source=graph()
    from app.observed_export import facts
    parts,pins=facts(source)
    assert compare(source,parts,pins)['passed']
    assert not compare(source,parts,{**pins,('U1','99'):'a'})['passed']
    assert not compare(source,{**parts,'R1':'changed'},pins)['passed']


def test_actual_kicad_preserves_literal_pins_and_zero_pin_component(tmp_path):
    report=write_kicad(graph(),tmp_path/'native')
    assert report['passed'] and report['components']==3 and report['matched_pins']==4
    assert report['native_readback'] and not report['extra_pins']


@pytest.mark.skipif(not oc.available(),reason='Actual Capture is required')
def test_actual_dsn_preserves_literal_pins_and_reversible_case_aliases(tmp_path):
    data,report=oc.export('observed-edge-cases',graph(),tmp_path,preserve_connections=True)
    assert report['passed'] and report['matched_pins']==4 and not report['extra_pins']
    assert report['net_aliases']['a']!=report['net_aliases']['A']
    assert report['routing']['all_connections_wired']
    assert report['routing']['visible_wire_verification']['passed']
    assert report['routing']['wired_nets']==1
    assert report['routing']['singleton_pins']==2
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read('observed-edge-cases.DSN')
        saved=json.loads(archive.read('verification.json'))
        assert saved['native_readback'] and saved['wrong_values']==[]
