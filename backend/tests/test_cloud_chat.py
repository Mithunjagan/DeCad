"""Opt-in OpenAI-compatible cloud chat for the design assistant: off by default, deterministic requests,
local fallback, and no substituted circuit when the model reply is unusable."""
import asyncio,json
import httpx,pytest
from app import model_runtime
from app.engine import OperationError

def mock(monkeypatch,handle):
 constructor=httpx.AsyncClient
 monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kw:constructor(transport=httpx.MockTransport(handle),**kw))

def test_cloud_is_off_without_url_and_key(monkeypatch):
 for name in ('CHAT_API_URL','CHAT_API_KEY','NVIDIA_API_KEY'):monkeypatch.delenv(name,raising=False)
 assert model_runtime.chat_provider() is None
 monkeypatch.setenv('CHAT_API_URL','https://integrate.api.nvidia.com/v1')
 assert model_runtime.chat_provider() is None                 # a URL without a key never sends anything

def test_cloud_request_is_deterministic_and_authorized(monkeypatch):
 monkeypatch.setenv('CHAT_API_URL','https://cloud.example/v1');monkeypatch.setenv('NVIDIA_API_KEY','k-test')
 seen=[]
 def handle(request):
  seen.append(request)
  return httpx.Response(200,json={'choices':[{'message':{'content':'{"kind":"timer_555"}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':9,'completion_tokens':4}})
 mock(monkeypatch,handle)
 result=asyncio.run(model_runtime.call('circuit_planning','blink an LED',schema=model_runtime.DesignSpec.model_json_schema()))
 body=json.loads(seen[0].content)
 assert str(seen[0].url)=='https://cloud.example/v1/chat/completions' and seen[0].headers['authorization']=='Bearer k-test'
 assert body['model']==model_runtime.CLOUD_DEFAULT_MODEL and body['temperature']==0
 assert body['chat_template_kwargs']=={'enable_thinking':False} and body['response_format']['type']=='json_schema'
 assert result['provider']=='cloud' and result['content']=='{"kind":"timer_555"}'

def test_cloud_failure_falls_back_to_the_local_model(monkeypatch):
 monkeypatch.setenv('CHAT_API_URL','https://cloud.example');monkeypatch.setenv('CHAT_API_KEY','k')
 monkeypatch.setenv('OLLAMA_URL','http://local.test');monkeypatch.setenv('CHAT_MODEL','local-chat')
 def handle(request):
  if request.url.host=='cloud.example':return httpx.Response(429,json={'error':'rate limited'})
  return httpx.Response(200,json={'message':{'content':'Ohm says V = IR.'}})
 mock(monkeypatch,handle)
 result=asyncio.run(model_runtime.call('explanation','what is ohms law'))
 assert result['provider']=='local' and 'Cloud model unavailable' in result['notice']

def test_status_reports_cloud_and_that_data_leaves_the_device(monkeypatch):
 monkeypatch.setenv('CHAT_API_URL','https://cloud.example/v1');monkeypatch.setenv('CHAT_API_KEY','k')
 monkeypatch.setenv('OLLAMA_URL','http://local.test')
 def handle(request):
  if request.url.host=='cloud.example':return httpx.Response(200,json={'data':[{'id':model_runtime.CLOUD_DEFAULT_MODEL}]})
  return httpx.Response(200,json={'models':[]})
 mock(monkeypatch,handle)
 status=asyncio.run(model_runtime.status())
 assert status['cloud']['ready'] and status['cloud']['data_leaves_device']
 planning=next(t for t in status['tasks'] if t['task']=='circuit_planning')
 assert planning['provider']=='cloud' and planning['ready']

def test_unusable_model_reply_is_an_error_not_a_divider(monkeypatch):
 async def mocked(*args,**kw):return {'content':'{"kind":"bad"}','model':'mock'}
 monkeypatch.setattr(model_runtime,'call',mocked)
 with pytest.raises(OperationError):asyncio.run(model_runtime.plan('make a circuit',{'components':[]}))
