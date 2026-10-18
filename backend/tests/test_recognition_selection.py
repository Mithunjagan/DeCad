import asyncio
import pytest
from app import ingestion,assistant
from app.engine import OperationError

def test_explicit_vision_override_does_not_change_default(tmp_path,monkeypatch):
 p=tmp_path/'image.png';p.write_bytes(b'fixture');monkeypatch.setenv('IMAGE_MODE','ocr');calls=[]
 async def extract(path,mode=None):
  calls.append(mode);return ingestion.Circuit(components=[{'ref':'R1','value':'10k'}])
 monkeypatch.setattr(ingestion,'extract_image',extract)
 asyncio.run(ingestion.ingest(p,recognition_mode='vision'));asyncio.run(ingestion.ingest(p))
 assert calls==['vision',None]

def test_low_pass_spelling_constructs_connected_filter(tmp_path,monkeypatch):
 def capture(text,lower,project,circuit,directives,before_mutation):return circuit
 monkeypatch.setattr(assistant,'_execute_local',capture)
 result=asyncio.run(assistant.execute('Create a low pass filter',tmp_path))
 assert {c.ref for c in result.components}=={'V1','R1','C1'}
 assert {n.name for n in result.nets}=={'VIN','VOUT','GND'}

def test_file_analysis_requires_an_actual_attachment(tmp_path):
 with pytest.raises(OperationError,match='No file was attached'):
  asyncio.run(assistant.execute('Analyze uploaded circuit file and generate schematic',tmp_path))

def test_requested_vision_error_does_not_fall_back_to_cpu(tmp_path,monkeypatch):
 from PIL import Image
 import sys,types
 from app import model_runtime
 image=tmp_path/'ic-schematic.png';Image.new('RGB',(64,64),'white').save(image)
 async def unavailable(*args,**kwargs):raise OperationError('Vision model is unavailable; no circuit was applied.')
 def forbidden_fallback(*args,**kwargs):raise AssertionError('Explicit vision must not silently use the R/C/V recognizer.')
 monkeypatch.setattr(model_runtime,'call',unavailable)
 monkeypatch.setitem(sys.modules,'app.circuit_vision',types.SimpleNamespace(extract=forbidden_fallback))
 with pytest.raises(OperationError,match='Vision model is unavailable'):
  asyncio.run(ingestion.extract_image(image,mode='vision'))

def test_vision_can_report_unreadable_image_without_forcing_a_dummy_component(tmp_path,monkeypatch):
 from PIL import Image
 from app import model_runtime
 image=tmp_path/'unreadable.png';Image.new('RGB',(64,64),'white').save(image)
 async def unreadable(task,prompt,**kwargs):
  assert kwargs['schema']['properties']['components']['minItems']==0
  assert '"ref":"R1"' not in prompt and '10k' not in prompt
  return {'content':'{"components":[],"nets":[],"warnings":["Pin labels are unreadable."]}'}
 monkeypatch.setattr(model_runtime,'call',unreadable)
 with pytest.raises(OperationError,match='Pin labels are unreadable'):
  asyncio.run(ingestion.extract_image(image,mode='vision'))
