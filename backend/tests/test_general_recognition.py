"""General routing, page preservation and graph reconciliation, without model claims."""
import asyncio
import base64
import io
import json
import sys
import types

from PIL import Image
import pytest

from app import ingestion, model_runtime, ocr_runtime
from app.engine import OperationError
from app.recognition import combine_pages, compare_candidates, review_issues
from app.vision_input import model_images


def graph(ref='Q731', value='2N3904'):
    return ingestion.Circuit(components=[{'ref':ref,'value':value}], nets=[
        {'name':'INPUT','nodes':[{'ref':ref,'pin':'1'}]},
        {'name':'OUTPUT','nodes':[{'ref':ref,'pin':'2'}]}])


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv('S2SDN_PIPELINE_PROFILE',raising=False)
    for name in ('VISION_MODEL','VISION_OLLAMA_URL','VISION_API_PROTOCOL','VISION_API_KEY','VISION_IMAGE_SIZE','VISION_DETAIL_IMAGES'):
        monkeypatch.delenv(name,raising=False)
    async def unavailable(*args,**kwargs):return []
    monkeypatch.setattr(model_runtime,'available_models',unavailable)


def test_auto_recovers_general_transistor_without_a_circuit_template(tmp_path,monkeypatch):
    def unsupported(*args):raise ValueError('No printed logic part number.')
    monkeypatch.setattr(ocr_runtime,'extract_digital',unsupported)
    monkeypatch.setenv('VISION_MODEL','general-reader')
    async def available(*args,**kwargs):return [{'name':'general-reader'}]
    monkeypatch.setattr(model_runtime,'available_models',available)
    image=tmp_path/'previously-unseen-transistor.png'
    Image.new('RGB',(300,200),'white').save(image)
    async def model(task,prompt,**kwargs):
        assert 'analog' in prompt and 'physical package pin' in prompt
        assert kwargs['images'] and task=='image_extraction'
        return {'content':graph().model_dump_json()}
    monkeypatch.setattr(model_runtime,'call',model)
    result=asyncio.run(ingestion.extract_image(image,'auto'))
    assert result.components[0].ref=='Q731' and len(result.nets)==2
    assert 'general vision' in result.warnings[0]


def test_auto_uses_general_reader_when_local_dependencies_are_optional(tmp_path,monkeypatch):
    def missing(*args):raise ImportError('reader not installed')
    monkeypatch.setattr(ocr_runtime,'extract_digital',missing)
    monkeypatch.setenv('S2SDN_OCR_DEVICE','auto')
    async def available(*args,**kwargs):return [{'name':model_runtime.DEFAULTS['vision']}]
    monkeypatch.setattr(model_runtime,'available_models',available)
    async def extract(*args,**kwargs):return graph()
    monkeypatch.setattr(ingestion,'_extract_image',extract)
    assert asyncio.run(ingestion._auto_extract(tmp_path/'a.png')).components[0].ref=='Q731'


def test_general_extension_preserves_local_physical_pin_observations(tmp_path,monkeypatch):
    local=graph();general=graph()
    general.components.append(ingestion.Component(ref='D294',value='1N4148'))
    general.nets[0].nodes.append(ingestion.Node(ref='D294',pin='1'))
    assert compare_candidates(local,general)==([],True)
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda _:local)
    monkeypatch.setenv('VISION_MODEL','general-reader')
    async def available(*args,**kwargs):return [{'name':'general-reader'}]
    monkeypatch.setattr(model_runtime,'available_models',available)
    async def extract(*args,**kwargs):return general
    monkeypatch.setattr(ingestion,'_extract_image',extract)
    result=asyncio.run(ingestion._auto_extract(tmp_path/'a.png'))
    assert {c.ref for c in result.components}=={'Q731','D294'}


def test_general_reader_can_resolve_an_explicitly_unknown_part_value(tmp_path,monkeypatch):
    local=graph(ref='U731',value='UNKNOWN');general=graph(ref='U731',value='LM358')
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda _:local)
    monkeypatch.setenv('VISION_MODEL','general-reader')
    async def available(*args,**kwargs):return [{'name':'general-reader'}]
    monkeypatch.setattr(model_runtime,'available_models',available)
    async def extract(*args,**kwargs):return general
    monkeypatch.setattr(ingestion,'_extract_image',extract)
    result=asyncio.run(ingestion._auto_extract(tmp_path/'a.png'))
    assert result.components[0].value=='LM358'


def test_general_reader_cannot_silently_short_local_nets(tmp_path,monkeypatch):
    local=graph();general=graph()
    general.nets=[ingestion.Net(name='SHORT',nodes=[node for net in general.nets for node in net.nodes])]
    conflicts,covers=compare_candidates(local,general)
    assert conflicts and not covers
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda _:local)
    monkeypatch.setenv('VISION_MODEL','general-reader')
    async def available(*args,**kwargs):return [{'name':'general-reader'}]
    monkeypatch.setattr(model_runtime,'available_models',available)
    async def extract(*args,**kwargs):return general
    monkeypatch.setattr(ingestion,'_extract_image',extract)
    result=asyncio.run(ingestion._auto_extract(tmp_path/'a.png'))
    assert len(result.nets)==2 and any('disagreed' in warning for warning in result.warnings)


def test_different_net_numbering_is_not_a_graph_conflict():
    first=graph();second=graph()
    for index,net in enumerate(second.nets):net.name=f'NET_{index}'
    assert compare_candidates(first,second)==([],True)


def test_disagreeing_source_labels_require_review_even_on_single_pin_nets():
    first=graph();second=graph();second.nets[0].name='WRONG_INPUT'
    conflicts,covers=compare_candidates(first,second)
    assert any('net label' in issue for issue in conflicts) and not covers


def test_optional_model_outage_does_not_discard_local_graph(tmp_path,monkeypatch):
    local=graph()
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda _:local)
    monkeypatch.setenv('VISION_MODEL','unavailable-reader')
    result=asyncio.run(ingestion.extract_image(tmp_path/'a.png','auto'))
    assert result.components[0].ref=='Q731'
    assert any('unavailable' in warning for warning in result.warnings)


def test_blank_physical_pin_is_rejected():
    with pytest.raises(ValueError):ingestion.Node(ref='Q731',pin=' ')


def test_unconnected_parts_and_unknown_values_are_explicit_review_items():
    result=ingestion.Circuit(components=[{'ref':'U_803','value':'UNKNOWN'}])
    issues=review_issues(result)
    assert any('No recovered pin' in issue for issue in issues)
    assert any('Unresolved' in issue for issue in issues)


def test_partial_passive_read_does_not_suppress_the_geometry_reader(tmp_path,monkeypatch):
    partial=graph(ref='R294',value='47K')
    for index,net in enumerate(partial.nets):net.name=f'N{index+1:04d}'
    complete=graph(ref='R294',value='47k')
    complete.components.append(ingestion.Component(ref='C803',value='220nF'))
    complete.nets[1].nodes.append(ingestion.Node(ref='C803',pin='1'))
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda _:partial)
    async def read(*args,**kwargs):return complete
    monkeypatch.setattr(ingestion,'_extract_image',read)
    result=asyncio.run(ingestion._auto_extract(tmp_path/'passives.png'))
    assert {c.ref for c in result.components}=={'R294','C803'}


def test_milli_and_mega_values_are_never_treated_as_matching():
    first=graph(ref='R294',value='1M');second=graph(ref='R294',value='1m')
    assert compare_candidates(first,second)[0]


def test_page_assembly_keeps_duplicate_refs_and_labels_separate():
    first=graph();second=graph(value='BC547')
    result=combine_pages([(1,first),(2,second)])
    assert {c.ref for c in result.components}=={'Q_P1_731','Q_P2_731'}
    assert {net.name for net in result.nets}=={'PAGE1_INPUT','PAGE1_OUTPUT','PAGE2_INPUT','PAGE2_OUTPUT'}
    assert all(len(net.nodes)==1 for net in result.nets)
    assert first.components[0].ref=='Q731'  # No mutation of the source proposal.
    assert any('cross-page' in warning for warning in result.warnings)


@pytest.mark.parametrize('suffix',['pdf','tiff'])
def test_every_document_page_is_processed(tmp_path,monkeypatch,suffix):
    path=tmp_path/f'multiple-circuits.{suffix}'
    images=[Image.new('RGB',(120,80),color) for color in ('red','blue','green')]
    images[0].save(path,save_all=True,append_images=images[1:])
    colors=[]
    async def read(path,mode=None):
        with Image.open(path) as image:colors.append(image.getpixel((20,20)))
        return graph()
    monkeypatch.setattr(ingestion,'_extract_image',read)
    result=asyncio.run(ingestion.extract_image(path,'vision'))
    assert len(colors)==3 and len(result.components)==3 and len(result.nets)==6
    assert len({c.ref for c in result.components})==3


def test_document_failure_never_returns_only_the_successful_first_page(tmp_path,monkeypatch):
    path=tmp_path/'two-pages.pdf'
    first=Image.new('RGB',(120,80),'red');second=Image.new('RGB',(120,80),'blue')
    first.save(path,save_all=True,append_images=[second])
    calls=[]
    async def read(*args):
        calls.append(1)
        if len(calls)==2:raise OperationError('unreadable symbols')
        return graph()
    monkeypatch.setattr(ingestion,'_extract_image',read)
    with pytest.raises(OperationError,match='Page 2.*No partial document'):
        asyncio.run(ingestion.extract_image(path,'vision'))


def test_blank_document_pages_are_reported(tmp_path,monkeypatch):
    path=tmp_path/'blank-plus-circuit.tiff'
    first=Image.new('RGB',(120,80),'white');second=Image.new('RGB',(120,80),'red')
    first.save(path,save_all=True,append_images=[second])
    async def read(*args):return graph()
    monkeypatch.setattr(ingestion,'_extract_image',read)
    result=asyncio.run(ingestion.extract_image(path,'vision'))
    assert len(result.components)==1 and any('blank document pages: 1' in w for w in result.warnings)


def test_large_sources_send_overview_and_full_coverage_details(tmp_path,monkeypatch):
    monkeypatch.setenv('VISION_IMAGE_SIZE','512')
    image=Image.new('RGB',(2400,1600),'white')
    # Four distant pieces of source evidence, including both outer page edges.
    for x,y,color in [(0,0,'red'),(2399,0,'blue'),(0,1599,'green'),(2399,1599,'black')]:
        image.paste(color,(x,y,x+8 if x==0 else x+1,y+8 if y==0 else y+1))
    path=tmp_path/'large.png';image.save(path)
    views,description=model_images(path)
    assert len(views)==5 and 'complete page overview' in description
    assert '[0.00000, 0.00000,' in description and '1.00000, 1.00000]' in description
    for encoded in views:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as view:
            assert max(view.size)<=512


def test_small_sources_do_not_get_redundant_detail_images(tmp_path):
    path=tmp_path/'small.png';Image.new('RGB',(300,200),'white').save(path)
    assert len(model_images(path)[0])==1


def test_unknown_mode_does_not_silently_dispatch_to_a_model(tmp_path):
    with pytest.raises(OperationError,match='Recognition mode'):
        asyncio.run(ingestion.extract_image(tmp_path/'a.png','typo'))


def test_ollama_vision_uses_vision_limits_and_rejects_truncation(monkeypatch):
    import httpx
    monkeypatch.setenv('VISION_CONTEXT_TOKENS','16384')
    monkeypatch.setenv('VISION_MAX_TOKENS','6000')
    def handle(request):
        payload=json.loads(request.content)
        assert payload['options']['num_ctx']==16384 and payload['options']['num_predict']==6000
        assert payload['keep_alive']==0
        return httpx.Response(200,json={'done_reason':'length','message':{'content':'{"components":['}})
    constructor=httpx.AsyncClient
    monkeypatch.setattr(model_runtime.httpx,'AsyncClient',lambda **kw:constructor(transport=httpx.MockTransport(handle),**kw))
    with pytest.raises(OperationError,match='token limit'):
        asyncio.run(model_runtime.call_local('image_extraction','read',images=['AA==']))


def test_corpus_metrics_detect_a_false_short_without_pair_expansion():
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/eval'))
    from corpus_metrics import score
    expected=graph().model_dump();predicted=graph().model_dump()
    predicted['nets']=[{'name':'SHORT','nodes':[node for net in predicted['nets'] for node in net['nodes']]}]
    result=score(expected,predicted)
    assert result['false_connections']==1 and result['connections']['precision']==0
    assert not result['sheet_exact']


def test_corpus_metrics_preserve_source_labels_and_ignore_automatic_net_numbering():
    from corpus_metrics import score
    expected=graph().model_dump();predicted=graph().model_dump()
    predicted['nets'][0]['name']='WRONG_INPUT'
    result=score(expected,predicted)
    assert result['net_labels']['recall']==.5 and not result['sheet_exact']
    for index,net in enumerate(expected['nets']):net['name']=f'N{index+1:04d}'
    for index,net in enumerate(predicted['nets']):net['name']=f'NET_{index+80}'
    assert score(expected,predicted)['sheet_exact']


def test_large_power_net_metrics_count_connections_without_materializing_pairs():
    from corpus_metrics import score
    nodes=[{'ref':'J731','pin':str(i)} for i in range(5000)]
    expected={'components':[{'ref':'J731','value':'HEADER'}], 'nets':[{'name':'GND','nodes':nodes}]}
    result=score(expected,expected)
    assert result['connections']['correct']==12_497_500 and result['sheet_exact']


def test_generic_corpus_runner_scores_new_netlists_and_reports_incomplete_truth(tmp_path):
    from run_corpus import evaluate
    # Actual ingestion of a distinct mixed transistor/diode circuit, without a
    # recognizer mock. This verifies netlist evaluation, not image recognition.
    source=tmp_path/'transistor-diode.cir'
    source.write_text('R731 VCC BASE 33k\nQ294 COLLECTOR BASE 0 2N3904\nD803 COLLECTOR 0 1N4148\n.end\n')
    reference,_=ingestion.parse_spice(source.read_text())
    (tmp_path/'reference.json').write_text(reference.model_dump_json())
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'cases':[
        {'id':'transistor-diode-unseen','source':source.name,'reference':'reference.json','reference_complete':True},
        {'id':'partial-reference','source':source.name,'reference':'reference.json','reference_complete':False},
        {'id':'unreadable-source','source':'absent.png','reference':'absent.json','reference_complete':True}]}))
    result=asyncio.run(evaluate(manifest,tmp_path/'report'))
    assert result['cases'][0]['sheet_exact'] and result['cases'][0]['meets_target']
    assert not result['cases'][1]['meets_target']
    assert 'error' in result['cases'][2] and not result['all_cases_meet_target']
    assert (tmp_path/'report/report.json').is_file()
