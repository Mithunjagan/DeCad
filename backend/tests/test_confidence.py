import io
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app import main
from app.confidence import annotate_image_graph,source_box
from app.ingestion import Circuit,Node
from app.recognition import combine_pages
from test_operations import client,create


def graph():
    return {'components':[{'ref':'R1','value':'10K'}],
            'nets':[{'name':'DATA','nodes':[{'ref':'R1','pin':'1'}]}],
            'image_metadata':{'width':200,'height':100,'source_size':[100,50],'source_affine':[[2,0,0],[0,2,0]],
                'pin_anchors':[{'ref':'R1','pin':'1','x':40,'y':30,'confidence':.6,'source':'wire_trace'}],
                'review_hotspots':[{'ref':'R1','pin':'1','bbox':[20,10,60,50],'reason':'Uncertain junction','confidence':.6}]}}


def test_source_regions_invert_scale_and_rotation_and_reject_stale_frames():
    assert source_box([20,10,60,50],graph()['image_metadata'])==[10,5,30,25]
    frame={'source_size':[100,100],'source_affine':[[0,-1,100],[1,0,0]]}
    assert source_box([60,10,80,30],frame)==[10,20,30,40]
    assert source_box([1,2,float('nan'),4],frame) is None
    frame['source_affine']=[[0,0,0],[0,0,0]]
    assert source_box([1,2,3,4],frame) is None


def test_image_assignments_are_scored_and_manual_graphs_remain_unscored():
    found=Circuit.from_image_graph(graph())
    assert found.nets[0].nodes[0].confidence==.6
    assert found.nets[0].confidence==.6 and found.nets[0].source=='wire_trace'
    assert found.review_hotspots[0].bbox==(10,5,30,25)
    assert Circuit(components=[{'ref':'R1','value':'1K'}],nets=[{'name':'A','nodes':[{'ref':'R1','pin':'1'}]}]).nets[0].confidence is None


@pytest.mark.parametrize('score',[float('nan'),float('inf'),-.01,1.01])
def test_invalid_evidence_scores_cannot_cross_api_schema(score):
    with pytest.raises(ValidationError):Node(ref='R1',pin='1',confidence=score)


def test_out_of_bounds_hotspot_and_unknown_source_are_rejected():
    data=annotate_image_graph(graph());data['review_hotspots'][0]['bbox']=[0,0,101,40]
    with pytest.raises(ValidationError):Circuit.model_validate(data)
    with pytest.raises(ValidationError):Node(ref='R1',pin='1',source='made_up')


def test_multipage_scopes_review_refs_and_preserves_every_evidence_score():
    first=Circuit.from_image_graph(graph());second=first.model_copy(deep=True)
    result=combine_pages([(2,first),(4,second)])
    assert {h.page for h in result.review_hotspots}=={2,4}
    assert {h.ref for h in result.review_hotspots}=={'R_P2_1','R_P4_1'}
    assert [n.confidence for n in result.nets]==[.6,.6]
    assert [f['page'] for f in result.image_metadata['source_frames']]==[2,4]
    assert combine_pages([(3,first)]).review_hotspots[0].page==3
    assert first.review_hotspots[0].page==1


def test_pdf_preview_uses_authenticated_project_path_and_actual_page(client):
    import fitz
    create(client)
    project=next(main.ROOT.glob('*/Circuit'))
    with fitz.open() as document:
        document.new_page(width=200,height=100);document.new_page(width=100,height=200)
        document.save(project/'source.pdf')
    result=client.get('/projects/Circuit/file',params={'name':'source.pdf','preview':'true','page':2})
    assert result.status_code==200,result.text
    with Image.open(io.BytesIO(result.content)) as image:assert image.size==(900,1800)
    assert client.get('/projects/Circuit/file?name=source.pdf&preview=true&page=3').status_code==404
    assert client.get('/projects/Circuit/file?name=../source.pdf&preview=true').status_code==400
    assert client.get('/projects/Circuit/file?name=source.pdf').content.startswith(b'%PDF')
    assert TestClient(main.app).get('/projects/Circuit/file?name=source.pdf&preview=true').status_code==401


def test_attachment_review_preserves_source_frames_hotspots_and_evidence(tmp_path,monkeypatch):
    import asyncio
    from app import assistant
    expected=Circuit.from_image_graph(graph())
    expected.warnings=['Compare with the actual source']
    async def ingest(*args,**kwargs):return expected,[]
    monkeypatch.setattr(assistant,'ingest',ingest)
    response=asyncio.run(assistant.execute('Analyze attached schematic',tmp_path,[tmp_path/'source.png']))
    assert response['route']=='import_review' and response['edits']==[]
    assert response['proposal']==expected.model_dump()


def test_other_attachment_boxes_cannot_overlay_the_first_source(tmp_path,monkeypatch):
    import asyncio
    from app import assistant
    first=Circuit.from_image_graph(graph());first.warnings=['Review source']
    other=deepcopy(graph())
    other['components'][0]['ref']='R2';other['nets'][0]['nodes'][0]['ref']='R2'
    other['nets'][0]['name']='OTHER'
    other['image_metadata']['pin_anchors'][0]['ref']='R2'
    other['image_metadata']['review_hotspots'][0]['ref']='R2'
    second=Circuit.from_image_graph(other)
    async def ingest(path,**kwargs):return (first if path.name=='one.png' else second),[]
    monkeypatch.setattr(assistant,'ingest',ingest)
    proposal=asyncio.run(assistant.execute('Analyze attached sources',tmp_path,[tmp_path/'one.png',tmp_path/'two.png']))['proposal']
    assert {h['ref'] for h in proposal['review_hotspots']}=={'R1'}
    assert proposal['image_metadata']['attachments'][1]['review_hotspots'][0]['ref']=='R2'
    assert 'separately' in proposal['warnings'][-1]
