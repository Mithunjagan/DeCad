import base64
import io
import json

import httpx
import numpy as np
from PIL import Image
import pytest

from app.roi_vision import RoIReader,ComponentCrop,crop_image


def answer():
    return {'ref_des':'U1','part_name':'LM358','pins':[{'pin_number':'1','internal_label':'OUT','side':'left'}]}


def test_crop_margin_is_clipped_and_full_page_requests_are_rejected():
    gray=np.full((1000,1000),255,np.uint8)
    encoded,bounds=crop_image(gray,(5,10,80,100),48)
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as view:assert view.size==(128,148)
    assert bounds==(0,0,128,148)
    with pytest.raises(ValueError,match='most of the page'):crop_image(gray,(0,0,1000,1000))


def test_primary_failure_falls_back_with_exact_served_model_and_crop_only_schema(monkeypatch):
    for name in ('S2SDN_ROI_PRIMARY_URL','S2SDN_ROI_FALLBACK_URL'):monkeypatch.delenv(name,raising=False)
    calls=[]
    def handle(request):
        primary=request.url.port==11437
        model='Qwen/Qwen3-VL-8B-Instruct' if primary else 'schematic2sdn-qwen-vl'
        if request.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':model}]})
        if request.url.path=='/lora-adapters':return httpx.Response(200,json=[])
        body=json.loads(request.content);calls.append(body)
        properties=body['response_format']['json_schema']['schema']['properties']
        assert set(properties)=={'ref_des','part_name','pins'}
        if primary:return httpx.Response(503)
        return httpx.Response(200,json={'model':model,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer())}}]})
    reader=RoIReader(transport=httpx.MockTransport(handle))
    try:result=reader.query(np.full((1000,1000),255,np.uint8),(100,100,200,200),'component',margin=48)
    finally:reader.close()
    assert result.part_name=='LM358' and len(calls)==2
    assert reader.audit[-1]['served_model']=='schematic2sdn-qwen-vl'
    assert reader.audit[-1]['role']=='fallback'


def test_netlists_and_internal_labels_cannot_escape_component_schema():
    with pytest.raises(ValueError):ComponentCrop.model_validate({**answer(),'nets':[{'name':'VCC'}]})
    bad=answer();bad['pins'][0]['net']='POWER'
    with pytest.raises(ValueError):ComponentCrop.model_validate(bad)


def test_offline_helpers_are_probed_once_and_return_no_invented_data():
    calls=[]
    def offline(request):calls.append(request);return httpx.Response(503)
    reader=RoIReader(transport=httpx.MockTransport(offline))
    try:
        for _ in range(4):assert reader.query(np.zeros((1000,1000),np.uint8),(100,100,200,200),'component') is None
    finally:reader.close()
    assert len(calls)==2 and reader.requests==0
    assert all(row['state']=='unavailable' for row in reader.audit)


def test_primary_with_active_adapter_is_rejected():
    def handle(request):
        if request.url.port==11436:return httpx.Response(503)
        if request.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':'Qwen/Qwen3-VL-8B-Instruct'}]})
        return httpx.Response(200,json=[{'path':'rejected-ocr.gguf','scale':1}])
    reader=RoIReader(transport=httpx.MockTransport(handle))
    try:assert reader.available()==[]
    finally:reader.close()


def test_malformed_model_service_responses_are_rejected_without_a_circuit():
    def malformed(request):
        if request.url.path=='/v1/models':
            model='Qwen/Qwen3-VL-8B-Instruct' if request.url.port==11437 else 'schematic2sdn-qwen-vl'
            return httpx.Response(200,json={'data':[{'id':model}]})
        if request.url.path=='/lora-adapters':return httpx.Response(200,json={'unexpected':'object'})
        return httpx.Response(200,json={'choices':[None]})
    reader=RoIReader(transport=httpx.MockTransport(malformed))
    try:assert reader.query(np.zeros((1000,1000),np.uint8),(100,100,200,200),'component') is None
    finally:reader.close()
    assert reader.audit[-1]['state']=='rejected'
