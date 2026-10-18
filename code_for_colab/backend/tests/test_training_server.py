import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient
spec=importlib.util.spec_from_file_location('adapter_server',Path(__file__).resolve().parents[2]/'training/serve.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

def test_unconfigured_adapter_fails_before_gpu_loading(tmp_path,monkeypatch):
 monkeypatch.setattr(server,'ADAPTER',tmp_path)
 with TestClient(server.app) as client:
  assert client.get('/api/tags').json()['models']==[]
  response=client.post('/api/chat',json={'model':server.TAG,'messages':[{'role':'user','content':'Extract circuit','images':['AA==']}]})
  assert response.status_code==422
  assert 'No trained adapter' in response.json()['detail']

def test_unknown_models_and_streaming_rejected():
 with TestClient(server.app) as client:
  body={'model':'arbitrary-model','messages':[{'role':'user','content':'test'}]}
  assert client.post('/api/chat',json=body).status_code==404
  body.update(model=server.TAG,stream=True)
  assert client.post('/api/chat',json=body).status_code==400

def test_bounded_adapter_protocol_with_inference_double(monkeypatch):
 monkeypatch.setattr(server,'infer',lambda body:{'model':server.TAG,'message':{'role':'assistant','content':'{"components":[],"nets":[]}'},'done':True})
 with TestClient(server.app) as client:
  response=client.post('/api/chat',json={'model':server.TAG,'messages':[{'role':'user','content':'test','images':['AA==']}]})
  assert response.status_code==200
  assert response.json()['message']['content']=='{"components":[],"nets":[]}'

def test_adapter_profiles_and_missing_weights_are_not_advertised(tmp_path,monkeypatch):
 import json
 monkeypatch.setattr(server,'ADAPTER',tmp_path)
 (tmp_path/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':'Qwen/Qwen2.5-VL-3B-Instruct'}))
 assert server.adapter_profile()['rank']==4
 assert not server.configured()
 (tmp_path/'adapter_model.safetensors').write_bytes(b'protocol-test-only')
 assert server.configured()  # Configuration readiness only; no GPU/weight-validity claim.
 (tmp_path/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':'unregistered/model'}))
 assert not server.configured()

def test_smoke_report_cannot_approve_another_gpu_or_dataset():
 spec=importlib.util.spec_from_file_location('bounded_trainer',Path(__file__).resolve().parents[2]/'training/finetune.py')
 trainer=importlib.util.module_from_spec(spec);spec.loader.exec_module(trainer)
 report={'status':'smoke_passed','profile':'3b-8gb','dataset_sha256':'abc','gpu':'GPU A','headroom_bytes':1024**3}
 assert trainer.smoke_matches(report,'3b-8gb','abc','GPU A')
 assert not trainer.smoke_matches(report,'3b-8gb','changed','GPU A')
 assert not trainer.smoke_matches(report,'3b-8gb','abc','GPU B')
 assert not trainer.smoke_matches({**report,'headroom_bytes':1},'3b-8gb','abc','GPU A')
