import importlib.util,io,json,os,subprocess,time,zipfile
from pathlib import Path
import pytest
from app.engine import Schematic,OperationError
from app.integrations import artifacts,bundle,enqueue,job_result,qucs_files
from app.assistant import apply_circuit,template
from app.simulation import run_ngspice
from test_operations import client,create,command

@pytest.fixture
def divider(tmp_path):
 p=tmp_path/'Integration';Schematic.create(p,p.name);sch=Schematic(p);apply_circuit(sch,template('divider'));sch.save();return p

@pytest.mark.parametrize('tool',['kicad','ngspice','ltspice','qucs-s'])
def test_application_bundles(tool,divider):
 data=bundle(tool,divider)
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  assert z.testzip() is None
  manifest=json.loads(z.read('manifest.json'));assert manifest['tool']==tool
  graph=json.loads(z.read('circuit.json'));assert len(graph['nets'])==3
  if tool in ['ngspice','ltspice']:assert 'R1 n2 n3 10k' in z.read('circuit.cir').decode()
  if tool=='qucs-s':
   assert '<Qucs Schematic' in z.read('circuit.sch').decode()
   assert '.subckt S2SDN n2 n3' in z.read('circuit.lib').decode()
   assert '.ends S2SDN' in z.read('circuit.lib').decode()

def test_integration_authentication_and_output(client):
 create(client);command(client,'create voltage divider')
 assert client.get('/integrations').status_code==200
 assert client.get('/projects/Circuit/integrations/ltspice/bundle').headers['content-type']=='application/zip'
 assert client.get('/projects/Circuit/integrations/unknown/bundle').status_code==422
 assert client.post('/projects/Circuit/integrations/ltspice/open').status_code==422
 client.post('/auth/logout');assert client.get('/integrations').status_code==401

def test_bridge_queue_isolation(divider,tmp_path):
 state=tmp_path/'state';state.mkdir();(state/'bridge-status.json').write_text(json.dumps({'updated_at':time.time(),'applications':{'ltspice':{'installed':True}}}))
 job=enqueue(state,'alice','ltspice',divider)
 assert job_result(state,'alice',job['id'])['status']=='queued'
 with pytest.raises(OperationError):job_result(state,'bob',job['id'])
 with pytest.raises(OperationError):job_result(state,'alice','../escape')
 folder=state/'bridge-jobs'/job['id'];(folder/'response.json').write_text(json.dumps({'id':job['id'],'status':'launched'}))
 assert job_result(state,'alice',job['id'])['status']=='launched'

def test_stale_bridge_rejected(divider,tmp_path):
 (tmp_path/'bridge-status.json').write_text(json.dumps({'updated_at':time.time()-20,'applications':{'ltspice':{'installed':True}}}))
 with pytest.raises(OperationError,match='not running'):enqueue(tmp_path,'alice','ltspice',divider)

def test_source_conflict_preserves_newer_content(client):
 create(client);command(client,'create voltage divider')
 r=client.get('/projects/Circuit/file?name=Circuit.kicad_sch');digest=r.headers['x-content-sha256'];old=r.text
 command(client,'change R1 to 22k')
 r=client.put('/projects/Circuit/file?name=Circuit.kicad_sch',json={'content':old,'expected_sha256':digest})
 assert r.status_code==409
 assert next(c for c in client.get('/projects/Circuit/graph').json()['components'] if c['ref']=='R1')['value']=='22k'

def test_model_plan_does_not_mutate(client,monkeypatch):
 from app import model_runtime
 create(client);before=client.get('/projects/Circuit/graph').json()
 async def mocked(*args,**kw):return {'content':'{"kind":"voltage_divider"}','model':'mock','elapsed_seconds':0}
 monkeypatch.setattr(model_runtime,'call',mocked)
 r=client.post('/ai/plan',json={'project':'Circuit','message':'Create a divider V1 12, R1 10k, R2 22k'})
 assert r.status_code==200 and len(r.json()['proposal']['nets'])==3
 assert client.get('/projects/Circuit/graph').json()==before
 assert client.post('/projects/Circuit/import',json={'circuit':r.json()['proposal']}).status_code==200

def test_model_failure_does_not_mutate(client,monkeypatch):
 from app import model_runtime
 create(client)
 async def mocked(*args,**kw):return {'content':'{"kind":"bad"}','model':'mock'}
 monkeypatch.setattr(model_runtime,'call',mocked)
 assert client.post('/ai/plan',json={'project':'Circuit','message':'make a circuit'}).status_code==422
 assert not client.get('/projects/Circuit/graph').json()['components']

def test_bounded_image_diagnostics(tmp_path):
 from PIL import Image,ImageDraw
 from app.vision_local import analyze
 image=Image.new('RGB',(400,200),'white');d=ImageDraw.Draw(image);d.line((20,100,380,100),fill='black',width=2);path=tmp_path/'lines.png';image.save(path)
 result=analyze(path);assert result['line_segments'] and not result['connectivity_verified']
 bad=tmp_path/'bad.png';bad.write_text('not an image')
 with pytest.raises(OperationError):analyze(bad)

def test_bridge_never_executes_arbitrary_command(tmp_path,monkeypatch):
 path=Path(__file__).parents[2]/'bridge'/'desktop_bridge.py'
 spec=importlib.util.spec_from_file_location('desktop_bridge',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 folder=tmp_path/'job';folder.mkdir();(folder/'request.json').write_text(json.dumps({'action':'shell','tool':'ltspice','file':'arbitrary'}))
 with pytest.raises(ValueError):module.process(folder,{'ltspice':{'installed':True,'path':'/trusted/LTspice'}})

@pytest.mark.skipif(not __import__('shutil').which('qucs-s'),reason='Native Qucs-S is included in Docker')
@pytest.mark.parametrize('kind,expected',[('divider',2.5),('rc',5.0)])
def test_native_qucs_compilation_and_ngspice(tmp_path,kind,expected):
 from app.integrations import simulate_qucs
 p=tmp_path/'QucsNative';Schematic.create(p,p.name);sch=Schematic(p);apply_circuit(sch,template(kind));sch.save()
 result=simulate_qucs(p)
 assert result['solver']=='qucs-s + ngspice'
 assert result['data'][-1]['signals']['VOUT']==pytest.approx(expected,abs=0.02)
