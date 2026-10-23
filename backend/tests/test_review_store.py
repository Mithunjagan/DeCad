import pytest
from fastapi.testclient import TestClient

from app import main
from app.faculty_xml import parse,to_circuit,semantic_diff
from test_faculty_xml import FIXTURE
from test_operations import client,create


def test_authenticated_save_edit_reopen_download_and_undo(client):
    create(client);graph=to_circuit(parse(FIXTURE.read_bytes())).model_dump()
    endpoint='/projects/Circuit/review'
    assert TestClient(main.app).get(endpoint).status_code==401
    first=client.put(endpoint,json={'circuit':graph});assert first.status_code==200,first.text
    revision=first.json()['revision']
    for net in graph['nets']:
        if net['name']=='QD0':net['name']='REVIEWED_QD0'
    second=client.put(endpoint,json={'circuit':graph,'expected_revision':revision})
    assert second.status_code==200,second.text
    assert client.put(endpoint,json={'circuit':graph,'expected_revision':revision}).status_code==422
    reopened=client.get(endpoint).json()
    assert any(n['name']=='REVIEWED_QD0' for n in reopened['circuit']['nets'])
    output=client.get('/projects/Circuit/export/faculty-xml')
    assert output.status_code==200,output.text
    assert output.headers['x-xml-fidelity']=='semantic-equal' and output.headers['x-td9-import']=='NOT VERIFIED'
    doc=parse(output.content)
    assert len(doc.nodes)==129 and len(doc.nets)==41
    assert sum(n.attributes.get('NodeNetName')=='REVIEWED_QD0' for n in doc.nodes)==4
    assert client.post(endpoint+'/undo',json={'expected_revision':revision}).status_code==422
    undone=client.post(endpoint+'/undo',json={'expected_revision':reopened['revision']})
    assert undone.status_code==200,undone.text
    output=client.get('/projects/Circuit/export/faculty-xml')
    assert semantic_diff(parse(FIXTURE.read_bytes()),parse(output.content))['equal']


def test_duplicate_assignment_rejected_without_overwriting_saved_graph(client):
    create(client);graph=to_circuit(parse(FIXTURE.read_bytes())).model_dump()
    assert client.put('/projects/Circuit/review',json={'circuit':graph}).status_code==200
    graph['nets'][1]['nodes'].append(graph['nets'][0]['nodes'][0])
    assert client.put('/projects/Circuit/review',json={'circuit':graph}).status_code==422
    assert client.post('/projects/Circuit/export/faculty-xml',json={'circuit':graph}).status_code==422
    assert client.get('/projects/Circuit/export/faculty-xml').status_code==200
