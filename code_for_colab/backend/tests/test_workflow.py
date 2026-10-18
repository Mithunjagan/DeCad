import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
from test_operations import client, create, command

@pytest.mark.parametrize('tool',['kicad','ngspice','ltspice','qucs-s'])
def test_user_divider_selected_output(client,tool):
    create(client)
    response=client.post('/ai/chat',json={'project':'Circuit','message':'create a voltage divider','output_tool':tool,'create_new_on_conflict':True})
    assert response.status_code==200,response.text
    result=response.json();assert result['output']['ready'],result
    graph=client.get('/projects/Circuit/details').json()
    assert len(graph['components'])==3 and len(graph['nets'])==3
    assert client.get('/projects/Circuit/preview.svg').status_code==200
    simulation=client.get('/projects/Circuit/simulate').json()
    assert simulation['data'][-1]['signals']['VOUT']==pytest.approx(2.5,rel=.001)
    bundle=client.get(result['output']['url']);assert bundle.status_code==200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        manifest=json.loads(archive.read('manifest.json'));assert manifest['tool']==tool
        assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest['files'].items())


def test_existing_design_preserved(client):
    create(client);assert command(client,'add R1 4.7k').status_code==200
    response=client.post('/ai/chat',json={'project':'Circuit','message':'create a voltage divider','output_tool':'ltspice','create_new_on_conflict':True})
    assert response.status_code==200,response.text
    result=response.json();assert result['project']!='Circuit' and result['output']['ready']
    assert len(client.get('/projects/'+result['project']+'/details').json()['components'])==3
    original=client.get('/projects/Circuit/details').json()['components']
    assert len(original)==1 and original[0]['value']=='4.7k'

@pytest.mark.parametrize('prompt',['Describe a voltage divider','I need a voltage divider','create divider'])
def test_creation_phrases(client,prompt):
    create(client);response=command(client,prompt)
    assert response.status_code==200,response.text
    assert len(client.get('/projects/Circuit/details').json()['components'])==3


def test_spaced_image_upload_review_and_output(client):
    create(client)
    data=(Path(__file__).parent/'vision_fixtures/divider.png').read_bytes()
    upload=client.post('/projects/Circuit/attachments',params={'name':'Sample 1.jpg.jpeg'},content=data)
    assert upload.status_code==200,upload.text
    path=upload.json()['path'];assert path=='references/Sample 1.jpg.jpeg'
    response=client.post('/ai/chat',json={'project':'Circuit','message':'Analyze the attached schematic and create a design','attachments':[path],'recognition_mode':'circuit','output_tool':'ngspice'})
    assert response.status_code==200,response.text
    result=response.json();assert result['proposal'] and not result.get('edits')
    applied=client.post('/projects/Circuit/import',json={'circuit':result['proposal'],'output_tool':'ngspice'})
    assert applied.status_code==200,applied.text
    assert applied.json()['output']['ready']
    assert len(client.get('/projects/Circuit/details').json()['components'])==3

@pytest.mark.parametrize('name',['../unsafe.png','dir/file.png','CON.png','bad\\name.png'])
def test_upload_unsafe_name_rejected(client,name):
    create(client)
    assert client.post('/projects/Circuit/attachments',params={'name':name},content=b'x').status_code==400


def test_unicode_image_upload_preview(client):
    create(client)
    data=(Path(__file__).parent/'vision_fixtures/divider.png').read_bytes()
    uploaded=client.post('/projects/Circuit/attachments',params={'name':'Circuit e\u0301 test.jpeg'},content=data)
    assert uploaded.status_code==200
    assert uploaded.json()['path']=='references/Circuit é test.jpeg'
    preview=client.get('/projects/Circuit/file',params={'name':uploaded.json()['path']})
    assert preview.status_code==200 and preview.content==data
    assert preview.headers['content-type']=='image/jpeg'
    assert 'filename*=UTF-8' in preview.headers['content-disposition']
