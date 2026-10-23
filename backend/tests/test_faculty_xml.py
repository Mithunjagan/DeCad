import asyncio
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest
from app.engine import OperationError
from app.faculty_xml import parse,serialize,to_circuit,from_circuit,semantic_diff,validate,graph_fidelity
from app.ingestion import Circuit,ingest

FIXTURE=Path(__file__).resolve().parents[2]/'training/faculty/NetList (1).xml'


def test_exact_faculty_roundtrip_through_canonical_graph():
    original=parse(FIXTURE.read_bytes())
    graph=to_circuit(original)
    exported=from_circuit(Circuit.model_validate_json(graph.model_dump_json()))
    reread=parse(serialize(exported))
    # Independent XML reader compares every source attribute, outside the codec's
    # own semantic-diff implementation, including all unused and empty records.
    source_tree=ET.fromstring(FIXTURE.read_bytes());output_tree=ET.fromstring(serialize(exported))
    for path,key in [('./NetList/Nodes/Node','NodeName'),('./NetList/PowerNets/Net','NetName'),('./NetList/UserNets/Net','NetName')]:
        assert {e.get(key):e.attrib for e in source_tree.findall(path)}=={e.get(key):e.attrib for e in output_tree.findall(path)}
    for tag in ('Application','Board','Version','Date'):assert source_tree.find(tag).attrib==output_tree.find(tag).attrib
    assert semantic_diff(original,reread)=={
        'equal':True,'nodes_before':129,'nodes_after':129,'nets_before':41,'nets_after':41,
        'nodes_missing':[],'nodes_extra':[],'nodes_changed':[],
        'nets_missing':[],'nets_extra':[],'nets_changed':[]}
    assert Counter(p.used for p in graph.physical_pins)=={True:114,False:15}
    qd0=next(n for n in graph.nets if n.name=='QD0')
    assert {(p.ref,p.pin) for p in qd0.nodes}=={('U1','18'),('U2','18'),('U3','1'),('U5','1')}
    p=next(p for p in graph.physical_pins if (p.ref,p.pin)==('J2','15'))
    assert p.used is True and not any(p.ref==q.ref and p.pin==q.pin for n in graph.nets for q in n.nodes)
    assert next(n for n in reread.nets if n.attributes['NetName']=='P5V').attributes['PowerLevel']=='1'
    assert any(p.attributes.get('NodeNetName')=='P5V' and p.attributes['PowerLevel']=='5' for p in reread.nodes)


def test_unknown_attributes_elements_empty_and_absent_survive():
    text=FIXTURE.read_text().replace('<FileDescription>','<FileDescription Future="x"><Extension A=""/>',1)
    text=text.replace('NodeName="U1_1"','FutureNode="" NodeName="U1_1"',1).replace(' LabelName="EABAR"','',1)
    original=parse(text)
    assert semantic_diff(original,parse(serialize(from_circuit(to_circuit(original)))))['equal']


def test_aliases_and_scope_metadata_do_not_short_different_declared_nets():
    text=FIXTURE.read_text().replace('AliaseNetName=""','AliaseNetName="SAME_ALIAS" Scope="sheet-A"',1)
    text=text.replace('AliaseNetName=""','AliaseNetName="SAME_ALIAS" Scope="sheet-B"',1)
    original=parse(text);graph=to_circuit(original)
    assignments={(p.ref,p.pin):n.name for n in graph.nets for p in n.nodes}
    assert assignments['U1','1']=='OE' and assignments['U1','2']=='BD1'
    assert semantic_diff(original,parse(serialize(from_circuit(graph))))['equal']


def test_edits_are_exported_instead_of_replaying_original():
    original=parse(FIXTURE.read_bytes());graph=to_circuit(original)
    net=next(n for n in graph.nets if n.name=='QD0');net.name='REVIEWED_QD0'
    result=parse(serialize(from_circuit(graph)))
    assert sum(n.attributes.get('NodeNetName')=='REVIEWED_QD0' for n in result.nodes)==4
    assert 'QD0' not in {n.attributes['NetName'] for n in result.nets}
    assert not semantic_diff(original,result)['equal']
    graph.components=[c for c in graph.components if c.ref!='U1']
    graph.physical_pins=[p for p in graph.physical_pins if p.ref!='U1']
    for n in graph.nets:n.nodes=[p for p in n.nodes if p.ref!='U1']
    graph.nets=[n for n in graph.nets if n.nodes]
    result=from_circuit(Circuit.model_validate(graph.model_dump()))
    assert not any(n.identity[0]=='U1' for n in result.nodes)


def test_new_graph_unknown_types_never_infer_power_from_pin_function():
    graph=Circuit(components=[{'ref':'U1','value':'Unknown'}],
                  physical_pins=[{'ref':'U1','pin':'2','pin_function':'GND'}],
                  nets=[{'name':'AGND','nodes':[{'ref':'U1','pin':'1'}]}])
    result=parse(serialize(from_circuit(graph)))
    assert len(result.nodes)==2 and not validate(result)
    assert all(n.attributes['NodeType']=='Unknown' and n.attributes['IsPowerPin']=='FALSE' for n in result.nodes)
    assert next(n for n in result.nodes if n.identity==('U1','2')).attributes['NodeNetName']==''
    assert to_circuit(result).nets[0].name=='AGND'


@pytest.mark.parametrize('text',[
    '<wrong/>','<!DOCTYPE a [<!ENTITY x "x">]><FileDescription/>',
    FIXTURE.read_text().replace('NodeName="U1_2"','NodeName="U1_1"',1),
    FIXTURE.read_text().replace('NodeNetName="OE"','NodeNetName="UNDECLARED"',1),
],ids=['root','entity','duplicate','undeclared'])
def test_invalid_xml_rejected(text):
    with pytest.raises(OperationError):parse(text)


def test_diff_includes_extra_records_and_metadata_changes():
    original=parse(FIXTURE.read_bytes());changed=original.model_copy(deep=True)
    changed.root.attributes['Extra']='yes'
    assert not semantic_diff(original,changed)['equal']


def test_actual_ingestion_uses_xml_parser():
    graph,_=asyncio.run(ingest(FIXTURE))
    assert len(graph.physical_pins)==129


def test_pin_metadata_value_edits_and_zero_pin_component_are_reported():
    graph=to_circuit(parse(FIXTURE.read_bytes()))
    graph.components[0].value='REVIEWED PART'
    graph.physical_pins[0].pin_function='ENABLE'
    graph.physical_pins[0].electrical_type='Output'
    graph.physical_pins[0].power=True
    result=parse(serialize(from_circuit(graph)))
    assert result.nodes[0].attributes['Marking']=='REVIEWED PART'
    assert result.nodes[0].attributes['LabelName']=='ENABLE'
    assert result.nodes[0].attributes['NodeType']=='Output'
    assert result.nodes[0].attributes['IsPowerPin']=='TRUE'
    assert graph_fidelity(graph,result)['passed']
    graph.components.append({'ref':'U999','value':'NO OBSERVED PINS'})
    graph=Circuit.model_validate(graph.model_dump())
    assert graph_fidelity(graph,from_circuit(graph))['missing_components']==['U999']
