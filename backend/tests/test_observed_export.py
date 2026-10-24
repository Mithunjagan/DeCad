import io
import json
import zipfile

import pytest

from app import orcad_capture as oc
from app.observed_export import compare,write_kicad


def test_pcb_readiness_distinguishes_suggestions_and_native_properties():
    from app.observed_export import footprint_readiness
    plan={'IC7':('dip16','standard (by package and pin count)'),
          'R7':('res400','component')}
    summary={'not_in_library':[]}
    missing=footprint_readiness(plan,{'R7':'res400'},summary)
    assert missing['missing']==['IC7'] and not missing['footprint_properties_complete']
    assigned=footprint_readiness(plan,{'IC7':'dip16','R7':'res400'},summary)
    assert assigned['footprint_properties_complete'] and assigned['needs_review']==['IC7']
    assert not assigned['ready'] and not assigned['native_pcb_netlisting_verified']
    wrong=footprint_readiness(plan,{'IC7':'dip14','R7':'res400'},summary)
    assert wrong['readback_mismatches']==['IC7'] and not wrong['ready']


def test_exact_observed_footprint_plan_keeps_explicit_packages(tmp_path,monkeypatch):
    from app.observed_export import footprint_plan
    from app import orcad_library as ol
    monkeypatch.setattr(oc,'library_index',lambda path:{})
    monkeypatch.setattr(ol,'footprint_catalog',lambda root:{'custom_package':'uploaded'})
    source={'components':[{'ref':'IC7','value':'UNLISTED','footprint':'CUSTOM_PACKAGE'}]}
    assert footprint_plan(source,{'IC7':{'3','7'}},tmp_path,tmp_path)=={'IC7':('CUSTOM_PACKAGE','component')}


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
    assert report['footprints']['placed']==report['footprints']['assigned']
    assert not report['pcb_readiness']['readback_mismatches']
    assert all(report['placed_footprints'].get(ref)==info['footprint']
               for ref,info in json.loads(zipfile.ZipFile(io.BytesIO(data)).read('orcad-mapping.json')).items()
               if info['footprint'])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read('observed-edge-cases.DSN')
        saved=json.loads(archive.read('verification.json'))
        assert saved['native_readback'] and saved['wrong_values']==[]
