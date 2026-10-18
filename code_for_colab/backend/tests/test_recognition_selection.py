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
