import numpy as np
import pytest

from app import digital_vision as dv,circuit_vision,orcad_capture
from app.ingestion import Circuit
from app.engine import OperationError


@pytest.fixture
def local_read(monkeypatch):
    monkeypatch.setenv('S2SDN_PIPELINE_PROFILE','hybrid_max_accuracy')
    page=dv.Page(np.full((500,500),255,np.uint8),None,None,None,None)
    monkeypatch.setattr(dv,'prepare',lambda *args,**kwargs:page)
    monkeypatch.setattr(dv,'tokens',lambda page:[dv.Token('R1',.99,10,20,40,35),dv.Token('10k',.99,50,20,80,35)])
    monkeypatch.setattr(orcad_capture,'available',lambda:False)
    monkeypatch.setattr(dv,'recognize',lambda *args:{'components':[{'ref':'R1','value':'10k'}],'nets':[],'warnings':[]})
    return page


def test_discrete_geometry_reuses_cuda_text_without_calling_cpu_ocr(local_read,tmp_path,monkeypatch):
    def prohibited(*args,**kwargs):raise AssertionError('CPU OCR must not be invoked')
    monkeypatch.setattr(circuit_vision.subprocess,'run',prohibited)
    def recover(image,words):
        assert [w['text'] for w in words]==['R1','10k'] and words[0]['conf']==99
        return Circuit(components=[{'ref':'R1','value':'10k'}],nets=[{'name':'VIN','nodes':[{'ref':'R1','pin':'1'}]}])
    monkeypatch.setattr(circuit_vision,'recover',recover)
    found=dv.extract(tmp_path/'schematic.png',tmp_path)
    assert found.nets[0].name=='VIN'


def test_discrete_geometry_cannot_replace_a_conflicting_read_value(local_read,tmp_path,monkeypatch):
    monkeypatch.setattr(circuit_vision,'recover',lambda *args:Circuit(components=[{'ref':'R1','value':'100k'}]))
    assert dv.extract(tmp_path/'schematic.png',tmp_path).components[0].value=='10k'


def test_cuda_runtime_failure_does_not_become_a_geometry_fallback(local_read,tmp_path,monkeypatch):
    def fail(*args):raise OperationError('CUDA unavailable')
    monkeypatch.setattr(dv,'tokens',fail)
    monkeypatch.setattr(circuit_vision,'recover',lambda *args:pytest.fail('Runtime failure was hidden'))
    with pytest.raises(OperationError,match='CUDA unavailable'):dv.extract(tmp_path/'schematic.png',tmp_path)
