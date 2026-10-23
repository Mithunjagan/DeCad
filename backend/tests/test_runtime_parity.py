from types import SimpleNamespace
import numpy as np

from app import digital_vision as dv,orcad_capture


def test_active_profile_never_drops_observed_pins_through_installed_capture(tmp_path,monkeypatch):
    monkeypatch.setenv('S2SDN_PIPELINE_PROFILE','hybrid_max_accuracy')
    page=SimpleNamespace(gray=np.zeros((100,200),dtype=np.uint8),notes=[])
    monkeypatch.setattr(dv,'prepare',lambda *a,**k:page)
    monkeypatch.setattr(dv,'tokens',lambda page:[])
    monkeypatch.setattr(dv,'recognize',lambda *a:{'components':[{'ref':'U1','value':'UNKNOWN'}],
        'nets':[{'name':'OBSERVED','nodes':[{'ref':'U1','pin':'B12'}]}],'warnings':[],
        'image_metadata':{'width':200,'height':100}})
    monkeypatch.setattr(orcad_capture,'available',lambda:True)
    def drop(*args):raise AssertionError('Recognition must not invoke native library mutation')
    monkeypatch.setattr(orcad_capture,'check',drop)
    result=dv.extract(tmp_path/'source.png',tmp_path)
    assert result.nets[0].nodes[0].pin=='B12'
    assert not any('library check skipped' in w for w in result.warnings)
