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
