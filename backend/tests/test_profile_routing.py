import asyncio
from pathlib import Path

import fitz
import pytest

from app import ingestion, ocr_runtime
from app.engine import OperationError


def result():
    return ingestion.Circuit(components=[{'ref':'U1','value':'LM358'}])


def test_profile_auto_never_invokes_full_page_general_reader(tmp_path,monkeypatch):
    monkeypatch.setenv('S2SDN_PIPELINE_PROFILE','hybrid_max_accuracy')
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda path:result())
    async def prohibited(*args):raise AssertionError('Full-page model route was used')
    monkeypatch.setattr(ingestion,'_auto_extract',prohibited)
    assert asyncio.run(ingestion.extract_image(tmp_path/'image.png','auto')).components[0].ref=='U1'


def test_profile_document_keeps_native_primitives_for_every_page(tmp_path,monkeypatch):
    path=tmp_path/'two-native-pages.pdf'
    with fitz.open() as doc:
        for i in range(2):
            page=doc.new_page(width=200,height=300)
            page.draw_line((10,20+i),(100,20+i))
            page.insert_text((20,50),'U1 LM358')
        doc.save(path)
    observations=[]
    def recognize(source):
        assert Path(source).suffix=='.pdf'
        with fitz.open(source) as doc:
            assert len(doc)==1
            observations.append((len(doc[0].get_drawings()),doc[0].get_text().strip()))
        return result()
    monkeypatch.setattr(ocr_runtime,'extract_digital',recognize)
    recovered=asyncio.run(ingestion.extract_image(path,'hybrid_max_accuracy'))
    assert len(observations)==2 and all(n==1 for n,_ in observations)
    assert len(recovered.components)==2


def test_profile_second_page_failure_does_not_return_a_partial_graph(tmp_path,monkeypatch):
    path=tmp_path/'two.pdf'
    with fitz.open() as doc:
        for i in range(2):doc.new_page().insert_text((20,50),'U1 LM358')
        doc.save(path)
    calls=[]
    def recognize(source):
        calls.append(source)
        if len(calls)==2:raise OperationError('No readable pins')
        return result()
    monkeypatch.setattr(ocr_runtime,'extract_digital',recognize)
    with pytest.raises(OperationError,match='Page 2.*No partial document'):
        asyncio.run(ingestion.extract_image(path,'hybrid_max_accuracy'))


def test_qwen3_8b_cannot_be_called_as_a_full_page_netlist_generator(monkeypatch):
    from app import model_runtime
    monkeypatch.setenv('VISION_MODEL','Qwen/Qwen3-VL-8B-Instruct')
    with pytest.raises(OperationError,match='restricted to component and junction crops'):
        asyncio.run(model_runtime.call('image_extraction','entire circuit',images=['encoded']))


def test_profile_skips_a_white_pdf_page_with_a_content_stream(tmp_path,monkeypatch):
    path=tmp_path/'white-and-circuit.pdf'
    with fitz.open() as doc:
        doc.new_page().draw_rect((10,10,100,100),color=(1,1,1),fill=(1,1,1))
        doc.new_page().insert_text((20,50),'U1 LM358')
        doc.save(path)
    calls=[]
    monkeypatch.setattr(ocr_runtime,'extract_digital',lambda source:calls.append(source) or result())
    recovered=asyncio.run(ingestion.extract_image(path,'hybrid_max_accuracy'))
    assert len(calls)==1 and any('blank document pages: 1' in w for w in recovered.warnings)
