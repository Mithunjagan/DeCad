import asyncio,json,re
import pytest
from app import assistant,model_runtime,ingestion
from app.engine import Schematic,OperationError
from app.circuit_layout import verify_graph
from app.sexpr import children


def test_native_divider_has_visible_routing_and_exact_nets(tmp_path):
    p=tmp_path/'Wired';Schematic.create(p,p.name);sch=Schematic(p)
    circuit=assistant.template('divider');assistant.apply_circuit(sch,circuit);sch.save()
    actual=sch.graph();verify_graph(circuit,actual)
    assert len(actual['nets'])==3
    assert len(children(sch.tree,'wire'))>6 # physical connections beyond individual stubs
    assert 'viewBox="0.0000 0.0000 297' not in sch.content_preview()


def test_native_partition_check_rejects_a_short():
    circuit=assistant.template('divider')
    actual={'components':[c.model_dump() for c in circuit.components], 'nets':[{'name':'GND','nodes':[p.model_dump() for n in circuit.nets for p in n.nodes]}]}
    with pytest.raises(OperationError,match='connectivity mismatch'):verify_graph(circuit,actual)


def test_detailed_prompt_uses_complete_graph_not_keyword_template(tmp_path,monkeypatch):
    p=tmp_path/'Complex';Schematic.create(p,p.name)
    circuit=ingestion.Circuit(components=[{'ref':'R1','value':'1k','library':'Device:R'},{'ref':'C1','value':'10n','library':'Device:C'},{'ref':'R2','value':'22k','library':'Device:R'},{'ref':'C2','value':'47n','library':'Device:C'}],nets=[{'name':'STAGE1','nodes':[{'ref':'R1','pin':'2'},{'ref':'C1','pin':'1'},{'ref':'R2','pin':'1'}]},{'name':'OUT','nodes':[{'ref':'R2','pin':'2'},{'ref':'C2','pin':'1'}]},{'name':'GND','nodes':[{'ref':'C1','pin':'2'},{'ref':'C2','pin':'2'}]}])
    seen={}
    async def mocked(task,prompt,**kwargs):
        seen.update(schema=kwargs['schema'],prompt=prompt)
        return {'content':circuit.model_dump_json(),'model':'test'}
    monkeypatch.setattr(model_runtime,'call',mocked)
    result=asyncio.run(assistant.execute('Create a two stage RC lowpass with R1 1k C1 10n R2 22k C2 47n',p))
    assert len(result['proposal']['components'])==4
    assert result['proposal']['components'][2]['value']=='22k'
    assert 'components' in seen['schema']['properties']
    assert Schematic(p).graph()['components']==[]


def test_model_cannot_return_unwired_component_list(monkeypatch):
    async def mocked(*args,**kwargs):return {'content':'{"components":[{"ref":"R1","value":"10k","library":"Device:R"}],"nets":[]}'}
    monkeypatch.setattr(model_runtime,'call',mocked)
    with pytest.raises(OperationError,match='no wiring'):asyncio.run(model_runtime.synthesize('create a network',{'components':[]}))


def test_vision_failure_does_not_substitute_partial_geometric_circuit(tmp_path,monkeypatch):
    from PIL import Image
    p=tmp_path/'sheet.png';Image.new('RGB',(300,200),'white').save(p)
    async def fail(*args,**kwargs):raise OperationError('model offline')
    monkeypatch.setattr(model_runtime,'call',fail)
    with pytest.raises(OperationError,match='No partial circuit was substituted'):asyncio.run(ingestion.extract_image(p,mode='vision'))


def test_all_pdf_pages_are_extracted(tmp_path,monkeypatch):
    import fitz
    p=tmp_path/'multipage.pdf'
    with fitz.open() as doc:
        doc.new_page();doc.new_page();doc.save(p)
    calls=[]
    async def mocked(*args,**kwargs):
        calls.append(1);i=len(calls)
        return {'content':json.dumps({'components':[{'ref':f'R{i}','value':'10k','library':'Device:R'}],'nets':[{'name':'OUT','nodes':[{'ref':f'R{i}','pin':'1'}]}]})}
    monkeypatch.setattr(model_runtime,'call',mocked)
    result=asyncio.run(ingestion.extract_image(p,mode='vision'))
    assert len(calls)==2 and len(result.components)==2
    assert {n.name for n in result.nets}=={'P1_OUT','P2_OUT'}


def test_multiunit_gate_keeps_power_pins_and_one_package_reference(tmp_path):
    p=tmp_path/'Gates';Schematic.create(p,p.name);sch=Schematic(p)
    circuit=ingestion.Circuit(components=[{'ref':'U1','value':'74LS00','library':'74xx:74LS00'}],nets=[{'name':'VCC','nodes':[{'ref':'U1','pin':'14'}]},{'name':'GND','nodes':[{'ref':'U1','pin':'7'}]},{'name':'A','nodes':[{'ref':'U1','pin':'1'}]},{'name':'B','nodes':[{'ref':'U1','pin':'2'}]},{'name':'Y','nodes':[{'ref':'U1','pin':'3'}]}])
    assistant.apply_circuit(sch,circuit);sch.save();actual=sch.graph();verify_graph(circuit,actual)
    assert len(actual['components'])==1
    assert len(sch.symbols())==5
    sch.set_value('U1','74LS00 revised')
    assert all(sch.property(s,'Value')=='74LS00 revised' for s in sch.symbols())
    sch.remove('U1');assert not sch.symbols()


def test_blank_image_never_invents_an_ic_or_bus():
    from PIL import Image
    from app.circuit_vision import recover
    with pytest.raises(OperationError,match='No reliable reference/value'):
        recover(Image.new('RGB',(800,600),'white'),[])


def test_geometric_mode_rejects_unknown_active_pinouts():
    from PIL import Image
    from app.circuit_vision import recover
    with pytest.raises(OperationError,match='active-device pinouts'):
        recover(Image.new('RGB',(800,600),'white'),[{'text':'U1','x':20,'y':20,'w':20,'h':20,'conf':95}])


def test_reviewed_spice_import_preserves_diode_model(client):
    from test_operations import create
    create(client)
    source='V1 IN 0 5\nR1 IN OUT 1k\nD1 OUT 0 DTEST\n.model DTEST D(Is=1e-14)\n.end'
    circuit,_=ingestion.parse_spice(source)
    assert circuit.models==['.model DTEST D(Is=1e-14)']
    result=client.post('/projects/Circuit/import',json={'circuit':circuit.model_dump(),'output_tool':'ngspice'})
    assert result.status_code==200,result.text
    assert result.json()['output']['ready'],result.json()


from test_operations import client
