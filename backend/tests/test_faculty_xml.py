import asyncio
from collections import Counter
from pathlib import Path

import pytest
from app.engine import OperationError
from app.faculty_xml import parse,serialize,to_circuit,from_circuit,semantic_diff,validate
from app.ingestion import Circuit,ingest

FIXTURE=Path(__file__).resolve().parents[2]/'training/faculty/NetList (1).xml'


def test_exact_faculty_roundtrip_through_canonical_graph():
    original=parse(FIXTURE.read_bytes())
    graph=to_circuit(original)
    exported=from_circuit(Circuit.model_validate_json(graph.model_dump_json()))
    reread=parse(serialize(exported))
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
