import json,time
import pytest
from app.file_dispatch import inspect,enqueue_file
from app.engine import OperationError
from test_operations import client,create,command

@pytest.mark.parametrize('name,content,expected',[
 ('c.kicad_sch','(kicad_sch)','kicad'),('b.kicad_pcb','(kicad_pcb)','kicad'),
 ('c.asc','Version 4','ltspice'),('c.cir','* title\nR1 a 0 1k','ngspice'),
 ('q.sch','<Qucs Schematic 24.2.1>','qucs-s'),('legacy.sch','EESchema Schematic File Version 4','kicad'),
 ('unknown.sch','unrecognized',None),('c.dsn','(pcb)',None)])
def test_content_aware_associations(tmp_path,name,content,expected):
 p=tmp_path/name;p.write_text(content);assert inspect(p)['recommended']==expected

def test_original_file_and_companion_are_preserved(tmp_path):
 p=tmp_path/'c.kicad_sch';p.write_text('(kicad_sch)');(tmp_path/'c.kicad_pro').write_text('{}')
 state=tmp_path/'state';state.mkdir();(state/'bridge-status.json').write_text(json.dumps({'updated_at':time.time(),'applications':{'kicad':{'installed':True}}}))
 job=enqueue_file(state,'alice','kicad',p);folder=state/'bridge-jobs'/job['id']
 assert (folder/p.name).read_bytes()==p.read_bytes()
 assert (folder/'c.kicad_pro').exists()
 assert json.loads((folder/'request.json').read_text())['owner']=='alice'
 with pytest.raises(OperationError,match='cannot be opened directly'):enqueue_file(state,'alice','ngspice',p)

def test_uploaded_simulator_control_script_is_rejected(tmp_path):
 p=tmp_path/'bad.cir';p.write_text('* source\nR1 a 0 1k\n.control\nshell touch /tmp/no\n.endc\n.end')
 with pytest.raises(OperationError):enqueue_file(tmp_path,'alice','ngspice',p)

def test_file_routes_and_verification(client):
 create(client);assert command(client,'create voltage divider').status_code==200
 assert client.get('/projects/Circuit/file-association?name=Circuit.kicad_sch').json()['recommended']=='kicad'
 assert client.get('/projects/Circuit/file-association?name=../escape').status_code!=200
 assert client.post('/projects/Circuit/open-file',json={'name':'Circuit.kicad_sch','tool':'ltspice','mode':'original'}).status_code==422
 report=client.get('/projects/Circuit/verification');assert report.status_code==200
 assert report.json()['native_components']==3
 assert report.json()['source_accuracy']=='not_measured'
 assert report.json()['functional_correctness']=='not_proven'

def test_reconnecting_pin_detaches_previous_physical_wire(client):
 create(client);assert command(client,'create voltage divider').status_code==200
 r=command(client,'connect net NEW to R1 pin 2');assert r.status_code==200,r.text
 nets=client.get('/projects/Circuit/graph').json()['nets']
 pinmap={(p['ref'],p['pin']):n['name'] for n in nets for p in n['nodes']}
 assert pinmap[('R1','2')]=='NEW'
 assert pinmap[('R2','1')]=='VOUT'
 assert pinmap[('R1','1')]=='VIN'


def test_reviewed_native_upload_and_added_part_invalidate_match(client,tmp_path):
 from app.ingestion import ingest
 import asyncio
 create(client);command(client,'create voltage divider')
 source=client.get('/projects/Circuit/file?name=Circuit.kicad_sch').text
 path=tmp_path/'native.kicad_sch';path.write_text(source)
 proposal,_=asyncio.run(ingest(path))
 assert len(proposal.components)==3 and len(proposal.nets)==3
 create(client,'Copy')
 r=client.post('/projects/Copy/import',json={'circuit':proposal.model_dump()});assert r.status_code==200,r.text
 assert client.get('/projects/Copy/verification').json()['reviewed_proposal_match'] is True
 assert command(client,'add R9 1k',name='Copy').status_code==200
 assert client.get('/projects/Copy/verification').json()['reviewed_proposal_match'] is False


def test_original_spice_without_title_does_not_drop_first_component(tmp_path):
 p=tmp_path/'no-title.cir';p.write_text('V1 VIN 0 DC 5\nR1 VIN 0 1k\n.op\n.end')
 with pytest.raises(OperationError,match='first line as a title'):enqueue_file(tmp_path,'alice','ngspice',p)
