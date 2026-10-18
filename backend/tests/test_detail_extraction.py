import asyncio,base64,io,json
from PIL import Image
from app import ingestion,model_runtime

def test_large_sheet_preserves_detail(tmp_path,monkeypatch):
    path=tmp_path/'sheet.png';Image.new('RGB',(4500,3000),'white').save(path)
    seen={}
    async def call(task,prompt,images,schema):
        seen.update(prompt=prompt,images=images)
        return {'content':json.dumps({'components':[{'ref':'C1','value':'100n','library':'Device:C'}],'nets':[],'warnings':[]})}
    monkeypatch.setattr(model_runtime,'call',call)
    result=asyncio.run(ingestion.extract_image(path,mode='vision'))
    sizes=[Image.open(io.BytesIO(base64.b64decode(v))).size for v in seen['images']]
    assert max(sizes[0])<=2048
    assert 1<len(sizes)<=13
    assert sizes[1][0]>=1536
    assert 'include each component once' in seen['prompt']
    assert result.components[0].ref=='C1'
    assert any('requires review' in w for w in result.warnings)

def test_small_sheet_uses_single_image(tmp_path,monkeypatch):
    path=tmp_path/'sheet.png';Image.new('RGB',(800,600),'white').save(path)
    async def call(task,prompt,images,schema):
        assert len(images)==1
        return {'content':'{"components":[{"ref":"R1","value":"10k"}],"nets":[],"warnings":[]}'}
    monkeypatch.setattr(model_runtime,'call',call)
    assert len(asyncio.run(ingestion.extract_image(path,mode='vision')).components)==1
