import shutil
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from app.circuit_vision import extract
from app.engine import OperationError
from app.simulation import number

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Native Tesseract required')
@pytest.mark.parametrize('family,scale',[('divider',1),('divider',1.25),('rc',.5),('rc',1),('rc',1.25)])
def test_real_pixel_component_value_and_pin_net_recognition(tmp_path,family,scale):
 source=Path(__file__).parent/'vision_fixtures'/(family+'.png')
 with Image.open(source) as im:
  im.resize((round(im.width*scale),round(im.height*scale))).save(tmp_path/'circuit.png')
 c=extract(tmp_path/'circuit.png');last='R2' if family=='divider' else 'C1'
 assert {x.ref:number(x.value) for x in c.components}==pytest.approx({'V1':5,'R1':10000,last:10000 if family=='divider' else 100e-9})
 assert {n.name:{(x.ref,x.pin) for x in n.nodes} for n in c.nets}=={'VIN':{('V1','1'),('R1','1')},'VOUT':{('R1','2'),(last,'1')},'GND':{('V1','2'),(last,'2')}}
 assert c.warnings

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Native Tesseract required')
def test_unmarked_crossing_is_rejected(tmp_path):
 with Image.open(Path(__file__).parent/'vision_fixtures/divider.png') as im:
  d=ImageDraw.Draw(im);d.line([(400,50),(400,150)],fill='black',width=2);im.save(tmp_path/'crossing.png')
 with pytest.raises(OperationError,match='crossing'):extract(tmp_path/'crossing.png')

@pytest.mark.skipif(not shutil.which('tesseract') or not shutil.which('kicad-cli') or not shutil.which('ngspice'),reason='Native OCR, KiCad and ngspice required')
def test_recognized_pixels_generate_editable_native_design_and_simulate(tmp_path):
 from app.engine import Schematic
 from app.assistant import apply_circuit
 from app.simulation import simulate
 circuit=extract(Path(__file__).parent/'vision_fixtures/divider.png')
 project=tmp_path/'Recognized';Schematic.create(project,project.name);sch=Schematic(project)
 apply_circuit(sch,circuit);sch.save()
 assert len(sch.graph()['components'])==3
 result=simulate(sch.graph())
 assert result['data'][-1]['signals']['VOUT']==pytest.approx(2.5,abs=.01)

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Native Tesseract required')
def test_schematic_pdf_recovers_component_pin_connections(tmp_path):
 import asyncio
 from app.ingestion import extract_image
 with Image.open(Path(__file__).parent/'vision_fixtures/divider.png') as im:im.save(tmp_path/'schematic.pdf','PDF',resolution=96)
 circuit=asyncio.run(extract_image(tmp_path/'schematic.pdf',mode='circuit'))
 assert {n.name:{(x.ref,x.pin) for x in n.nodes} for n in circuit.nets}=={'VIN':{('V1','1'),('R1','1')},'VOUT':{('R1','2'),('R2','1')},'GND':{('V1','2'),('R2','2')}}

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Native Tesseract required')
def test_unreadable_reference_does_not_silently_omit_component(tmp_path):
 with Image.open(Path(__file__).parent/'vision_fixtures/divider.png') as im:im.resize((400,400)).save(tmp_path/'small.png')
 with pytest.raises(OperationError,match='reference/value'):extract(tmp_path/'small.png')

from test_operations import client,create

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Native Tesseract required')
def test_attachment_api_proposes_graph_then_applies_reviewed_import(client):
 create(client)
 data=(Path(__file__).parent/'vision_fixtures/divider.png').read_bytes()
 upload=client.post('/projects/Circuit/attachments?name=divider.png',content=data)
 assert upload.status_code==200,upload.text
 response=client.post('/ai/chat',json={'project':'Circuit','message':'Analyze uploaded circuit file and generate schematic','attachments':[upload.json()['path']],'recognition_mode':'circuit'})
 assert response.status_code==200,response.text
 proposal=response.json()['proposal']
 assert len(proposal['components'])==3 and len(proposal['nets'])==3
 assert not client.get('/projects/Circuit/graph').json()['components']
 applied=client.post('/projects/Circuit/import',json={'circuit':proposal})
 assert applied.status_code==200,applied.text
 assert client.get('/projects/Circuit/simulate').json()['data'][-1]['signals']['VOUT']==pytest.approx(2.5,abs=.01)
