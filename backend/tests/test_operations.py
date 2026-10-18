import asyncio
import json
import math
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import main
from app.engine import OperationError, Schematic
from app.ingestion import Circuit, parse_json, parse_spice, parse_text
from app.sexpr import child, children, parse
from app.simulation import number, simulate

def test_csv_import(tmp_path):
    from app.ingestion import ingest
    path=tmp_path/'parts.csv'
    path.write_text('ref,value,library\nR1,10k,Device:R\nC1,100nF,Device:C\n')
    circuit,_=asyncio.run(ingest(path))
    assert [(c.ref,c.value) for c in circuit.components]==[('R1','10k'),('C1','100nF')]
    assert not circuit.nets and circuit.warnings
    path.write_text('part,resistance\nR1,10k\n')
    with pytest.raises(OperationError):asyncio.run(ingest(path))

def test_vision_busy_rejects_without_loading_model(tmp_path,monkeypatch):
    from app import ingestion
    class Busy:
        def locked(self):return True
    monkeypatch.setattr(ingestion,'VISION_LOCK',Busy())
    with pytest.raises(OperationError,match='already running'):
        asyncio.run(ingestion.extract_image(tmp_path/'not-read.png'))

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'ROOT',tmp_path/'projects');main.ROOT.mkdir()
    monkeypatch.setattr(main,'STATE',tmp_path/'state');main.STATE.mkdir()
    monkeypatch.setattr(main,'DB',main.STATE/'sessions.sqlite3')
    monkeypatch.setattr(main,'ACTIVE',main.STATE/'active-project')
    monkeypatch.setattr(main,'DATASETS',tmp_path/'datasets')
    c=TestClient(main.app);assert c.get('/auth/dev').status_code==200
    return c

def create(c,name='Circuit'):
    assert c.post('/projects',json={'name':name}).status_code==200
    return name

def command(c,text,name='Circuit'):
    return c.post('/ai/chat',json={'project':name,'message':text})

@pytest.mark.parametrize('text,expected',[
 ('add C1 100nF',[('C1','100nF')]),
 ('add U1 74LS244',[('U1','74LS244')]),
 ('add R1 4.7k and R2 10k',[('R1','4.7k'),('R2','10k')]),
 ('add V1 PULSE(0 5 0 1u 1u 1m 2m)',[('V1','PULSE(0 5 0 1u 1u 1m 2m)')]),
])
def test_values(text,expected):
    assert [(c.ref,c.value) for c in parse_text(text).components]==expected

def test_spice_pin_connectivity():
    circuit,_=parse_spice('V1 VIN 0 DC 5\nR1 VIN VOUT 10k\nC1 VOUT 0 100nF\n.tran 1u 1m\n.end')
    assert [c.value for c in circuit.components]==['DC 5','10k','100nF']
    assert [(x.ref,x.pin) for x in next(n for n in circuit.nets if n.name=='VOUT').nodes]==[('R1','2'),('C1','1')]

def test_divider_native_connectivity_and_solver(client):
    create(client)
    r=command(client,'create voltage divider');assert r.status_code==200,r.text
    assert r.json()['validation']['passed'],r.json()['validation']
    graph=client.get('/projects/Circuit/details').json()
    mapping={n['name']:{(p['ref'],p['pin']) for p in n['nodes']} for n in graph['nets']}
    assert mapping=={'VIN':{('V1','1'),('R1','1')},'VOUT':{('R1','2'),('R2','1')},'GND':{('V1','2'),('R2','2')}}
    result=client.get('/projects/Circuit/simulate');assert result.status_code==200,result.text
    assert result.json()['data'][-1]['signals']['VOUT']==pytest.approx(2.5,rel=.001)
    assert client.get('/projects/Circuit/preview.svg').status_code==200
    spice=client.get('/projects/Circuit/export/spice');assert spice.status_code==200 and 'V1' in spice.text

def test_edif_matches_native_graph(client):
    create(client);command(client,'create voltage divider')
    graph=client.get('/projects/Circuit/details').json()
    r=client.get('/projects/Circuit/export/edif');assert r.status_code==200
    tree=parse(r.text);assert tree[0]=='edif'
    work=next(l for l in children(tree,'library') if l[1]=='WORK')
    contents=child(child(child(work,'cell'),'view'),'contents')
    actual=[]
    for net in children(contents,'net'):
        joins=child(net,'joined')
        actual.append({(child(p,'instanceRef')[1].removeprefix('N_'),str(p[1]).removeprefix('N_')) for p in children(joins,'portRef')})
    expected=[{(p['ref'],p['pin']) for p in n['nodes']} for n in graph['nets']]
    assert sorted(map(sorted,actual))==sorted(map(sorted,expected))

def test_edit_is_executed_in_every_project(client):
    for name in ['A','B']:
        create(client,name);assert command(client,'add R1 10k',name).status_code==200
        assert command(client,'change R1 to 22k',name).status_code==200
        assert client.get(f'/projects/{name}/details').json()['components'][0]['value']=='22k'

def test_remove_undo_redo_and_real_errors(client):
    create(client);r=command(client,'add R1 10k');assert r.status_code==200
    assert not r.json()['validation']['passed']
    assert any(v['severity']=='error' for v in r.json()['validation']['violations'])
    assert command(client,'remove R1').status_code==200
    assert client.get('/projects/Circuit/details').json()['components']==[]
    assert client.post('/projects/Circuit/control?action=undo').status_code==200
    assert client.get('/projects/Circuit/details').json()['components'][0]['value']=='10k'
    assert client.post('/projects/Circuit/control?action=redo').status_code==200
    assert client.get('/projects/Circuit/details').json()['components']==[]

def test_import_failure_rolls_back(client):
    create(client)
    before=client.get('/projects/Circuit/file?name=Circuit.kicad_sch').text
    proposal={'components':[{'ref':'R1','value':'10k'},{'ref':'U1','value':'NonexistentChip'}],'nets':[]}
    r=client.post('/projects/Circuit/import',json={'circuit':proposal});assert r.status_code==422
    assert client.get('/projects/Circuit/file?name=Circuit.kicad_sch').text==before

def test_spice_upload_import(client):
    create(client)
    r=client.post('/projects/Circuit/attachments?name=input.cir',content=b'V1 VIN 0 5\nR1 VIN VOUT 10k\nR2 VOUT 0 10k')
    assert r.status_code==200
    r=client.post('/ai/chat',json={'project':'Circuit','message':'Import reference','attachments':['references/input.cir']})
    assert r.status_code==200,r.text
    assert client.get('/projects/Circuit/simulate').json()['data'][-1]['vout']==pytest.approx(2.5)

def test_conversation_does_not_mutate(client):
    create(client);command(client,'add R1 10k')
    before=client.get('/projects/Circuit/file?name=Circuit.kicad_sch').content
    assert command(client,'Explain R1 10k').status_code==200
    assert client.get('/projects/Circuit/file?name=Circuit.kicad_sch').content==before

def test_path_auth_and_csrf(client):
    create(client)
    with pytest.raises(Exception):main.pdir({'login':'local'},'..')
    assert client.get('/projects/Circuit/file?name=../secrets').status_code==400
    assert client.get('/projects/Circuit/file?name=.git/config').status_code==400
    assert client.post('/ai/chat',json={'project':'Circuit','message':'import','attachments':['../../secrets']}).status_code==400
    assert client.post('/projects',json={'name':'..'}).status_code==400
    assert client.post('/projects',json={'name':'Cross'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/auth/callback?code=bad&state=bad').status_code==400
    assert client.post('/auth/logout').status_code==200
    assert client.get('/projects').status_code==401

def test_no_fake_empty_simulation(client):
    create(client)
    assert client.get('/projects/Circuit/simulate').status_code==422

def test_source_save_rollback(client):
    create(client)
    path='/projects/Circuit/file?name=Circuit.kicad_sch';before=client.get(path).text
    assert client.put(path,json={'content':'(broken'}).status_code==422
    assert client.get(path).text==before

def test_no_fake_bom(client):
    create(client);command(client,'add R1 10k')
    c=client.get('/projects/Circuit/details').json()['components'][0]
    assert c['unitPrice']=='Not queried' and c['stock']=='Not queried' and c['lcsc']=='Not specified'
    assert c['footprint']==''

def test_failures_are_visible(client,monkeypatch):
    create(client)
    monkeypatch.setenv('KICAD_EMBEDDED','false')
    assert client.post('/projects/Circuit/activate').status_code==422
    assert client.post('/projects/Circuit/control?action=unknown').status_code==400
    assert client.post('/projects/Circuit/git/push',json={'message':'test'}).status_code==400
    assert client.get('/projects/Circuit/export/orcad-tcl').status_code==409

def test_device_model_rejected_not_substituted(client):
    create(client)
    r=command(client,'add U1 TotallyUnknownChip');assert r.status_code==422
    assert client.get('/projects/Circuit/details').json()['components']==[]

def test_rc_step_matches_analytic_solution():
    graph={'components':[{'ref':'V1','value':'PULSE(0 5 10u 1n 1n 10m 20m)'},{'ref':'R1','value':'10k'},{'ref':'C1','value':'100nF'}], 'nets':[{'name':'VIN','nodes':[{'ref':'V1','pin':'1'},{'ref':'R1','pin':'1'}]},{'name':'VOUT','nodes':[{'ref':'R1','pin':'2'},{'ref':'C1','pin':'1'}]},{'name':'GND','nodes':[{'ref':'V1','pin':'2'},{'ref':'C1','pin':'2'}]}]}
    from app.simulation import mna
    data=mna(graph,1e-6,1.01e-3)['data'][-1]
    assert data['vout']==pytest.approx(5*(1-math.exp(-1)),abs=.01)

def test_native_ic_has_real_twenty_pin_symbol(client):
    create(client)
    r=command(client,'add U1 74LS244');assert r.status_code==200,r.text
    text=client.get('/projects/Circuit/file?name=Circuit.kicad_sch').text
    tree=parse(text);lib=child(tree,'lib_symbols');definition=next(s for s in children(lib,'symbol') if s[1]=='74xx:74LS244')
    numbers={child(pin,'number')[1] for block in children(definition,'symbol') for pin in children(block,'pin')}
    assert numbers=={str(i) for i in range(1,21)}
    assert 'DIP8' not in text

def test_session_token_is_server_side(client):
    import base64
    # Only a random session id is readable from the signed cookie.
    raw=client.cookies.get('s2sdn_session').split('.')[0]
    data=json.loads(base64.b64decode(raw))
    assert list(data)==['sid']
    assert 'user' not in data and 'token' not in data

def test_generation_outputs_real_graph_and_exports(client):
    r=client.post('/datasets/synthetic/generate?count=2');assert r.status_code==200,r.text
    assert len(r.json()['samples'])==2
    for sample in r.json()['samples']:
        assert sample['validated']
        folder=main.DATASETS/'synthetic'/sample['sample_id']
        assert {p.suffix for p in folder.iterdir()} >= {'.json','.kicad_sch','.svg','.edf','.cir'}
        graph=json.loads((folder/'circuit.json').read_text())
        assert len(graph['nets'])==3 and all(len(n['nodes'])==2 for n in graph['nets'])

def test_json_duplicate_pin_is_rejected():
    with pytest.raises(OperationError):
        parse_json(json.dumps({'components':[{'ref':'R1','value':'10k'}],'nets':[{'name':'A','nodes':[{'ref':'R1','pin':'1'}]},{'name':'B','nodes':[{'ref':'R1','pin':'1'}]}]}))

def test_diode_spice_pin_mapping():
    circuit,models=parse_spice('D1 OUT 0 DTEST\n.model DTEST D(IS=1e-14)')
    mapping={n.name:[(x.ref,x.pin) for x in n.nodes] for n in circuit.nets}
    assert mapping=={'OUT':[('D1','2')],'GND':[('D1','1')]}
    assert models==['.model DTEST D(IS=1e-14)']

def test_oauth_roundtrip_and_push_without_network(client,monkeypatch):
    import httpx,subprocess,urllib.parse
    monkeypatch.setattr(main,'GH_ID','test-client-id');monkeypatch.setattr(main,'GH_SECRET','test-client-secret')
    class FakeGitHub:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,**kwargs):
            if url.endswith('/user'):return httpx.Response(200,json={'login':'testuser','name':'Test User'})
            return httpx.Response(404,json={})
        async def post(self,url,**kwargs):
            if url.endswith('/access_token'):return httpx.Response(200,json={'access_token':'fake-test-token'})
            return httpx.Response(201,json={'name':'test-repo'})
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:FakeGitHub())
    r=client.get('/auth/login',follow_redirects=False)
    state=urllib.parse.parse_qs(urllib.parse.urlparse(r.headers['location']).query)['state'][0]
    assert client.get('/auth/callback',params={'code':'fake-code','state':state},follow_redirects=False).status_code==307
    assert client.get('/auth/me').json()['git_linked']
    assert client.get('/auth/callback',params={'code':'fake-code','state':state}).status_code==400
    create(client)
    original_git=main.git;pushes=[]
    def fake_push(p,*args,**kwargs):
        if args[0]=='push':
            assert 'fake-test-token' not in ' '.join(args)
            assert kwargs['env']['S2SDN_GIT_TOKEN']=='fake-test-token'
            pushes.append(args);return subprocess.CompletedProcess(args,0,'','')
        return original_git(p,*args,**kwargs)
    monkeypatch.setattr(main,'git',fake_push)
    r=client.post('/projects/Circuit/git/push',json={'message':'Verified mock push'})
    assert r.status_code==200 and r.json()['repo']=='https://github.com/testuser/s2sdn-Circuit'
    assert pushes
