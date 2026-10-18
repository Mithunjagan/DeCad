import asyncio,json
import httpx
from app import model_runtime

def test_separate_vision_and_chat_model_servers(monkeypatch):
 monkeypatch.setenv('OLLAMA_URL','http://chat.local')
 monkeypatch.setenv('VISION_OLLAMA_URL','http://vision.local')
 monkeypatch.setenv('CHAT_MODEL','local-chat')
 monkeypatch.setenv('VISION_MODEL','circuit-adapter')
 calls=[]
 def handle(request):
  calls.append(str(request.url))
  if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local-chat' if request.url.host=='chat.local' else 'circuit-adapter'}]})
  body=json.loads(request.content)
  return httpx.Response(200,json={'model':body['model'],'message':{'content':'{}'}})
 constructor=httpx.AsyncClient
 monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kwargs:constructor(transport=httpx.MockTransport(handle),**kwargs))
 status=asyncio.run(model_runtime.status())
 assert all(task['ready'] for task in status['tasks'])
 asyncio.run(model_runtime.call('image_extraction','circuit',images=['AA==']))
 assert calls[-1]=='http://vision.local/api/chat'
 asyncio.run(model_runtime.call('explanation','circuit'))
 assert calls[-1]=='http://chat.local/api/chat'

def test_openai_vision_uses_supplied_model_schema_and_authorization(monkeypatch):
 monkeypatch.setenv('VISION_API_PROTOCOL','openai')
 monkeypatch.setenv('VISION_API_KEY','test-local-key')
 monkeypatch.setenv('VISION_MODEL','supplied-adapter')
 monkeypatch.setenv('VISION_OLLAMA_URL','http://vision.local')
 monkeypatch.setenv('VISION_MAX_TOKENS','4096')
 calls=[]
 def handle(request):
  calls.append(request)
  assert request.headers['Authorization']=='Bearer test-local-key'
  if request.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':'supplied-adapter'}]})
  body=json.loads(request.content)
  assert body['model']=='supplied-adapter'
  assert body['messages'][1]['content'][0]['image_url']['url']=='data:image/png;base64,AA=='
  assert body['messages'][1]['content'][1]=={'type':'text','text':'read schematic'}
  assert body['response_format']['json_schema']['schema']=={'type':'object'}
  assert body['max_tokens']==4096
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"components":[]}'}}],'usage':{'prompt_tokens':10,'completion_tokens':5}})
 constructor=httpx.AsyncClient
 monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kwargs:constructor(transport=httpx.MockTransport(handle),**kwargs))
 models=asyncio.run(model_runtime.available_models('http://vision.local',vision=True))
 assert models[0]['name']=='supplied-adapter'
 result=asyncio.run(model_runtime.call('image_extraction','read schematic',images=['AA=='],schema={'type':'object'}))
 assert result['content']=='{"components":[]}' and result['output_tokens']==5
 assert calls[-1].url.path=='/v1/chat/completions'

def test_truncated_vision_output_is_never_returned_as_a_circuit(monkeypatch):
 import pytest
 from app.engine import OperationError
 monkeypatch.setenv('VISION_API_PROTOCOL','openai')
 def handle(request):return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"components":['}}]})
 constructor=httpx.AsyncClient
 monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kwargs:constructor(transport=httpx.MockTransport(handle),**kwargs))
 with pytest.raises(OperationError,match='token limit'):
  asyncio.run(model_runtime.call('image_extraction','read',images=['AA==']))

def test_native_grammar_does_not_expand_large_bounds_and_full_output_is_still_validated():
 import copy,pytest
 from app.ingestion import Circuit,parse_json
 from app.engine import OperationError
 original=Circuit.model_json_schema();saved=copy.deepcopy(original)
 grammar=model_runtime.generation_schema(original)
 assert original==saved
 assert 'maxItems' not in json.dumps(grammar) and 'maxLength' not in json.dumps(grammar)
 assert grammar['$defs']['Component']['properties']['ref']['pattern']=='^[A-Z][A-Z0-9_]*[0-9]+$'
 with pytest.raises(OperationError,match='Invalid circuit JSON'):
  parse_json(json.dumps({'components':[{'ref':'R1','value':'x'*201}]}))

def test_total_inference_deadline_releases_lock(monkeypatch):
 import pytest
 from app.engine import OperationError
 monkeypatch.setenv('VISION_API_PROTOCOL','openai')
 monkeypatch.setenv('VISION_TIMEOUT_SECONDS','0.01')
 async def handle(request):
  await asyncio.sleep(1)
  return httpx.Response(200,json={'choices':[]})
 constructor=httpx.AsyncClient
 monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kwargs:constructor(transport=httpx.MockTransport(handle),**kwargs))
 with pytest.raises(OperationError,match='time limit'):
  asyncio.run(model_runtime.call('image_extraction','read',images=['AA==']))
 assert not model_runtime.LOCK.locked()
