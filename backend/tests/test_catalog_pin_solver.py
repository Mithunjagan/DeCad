from app.catalog_pin_solver import recover_sequences


def fixture(values):
    rows={('U1',1,0,100):[(i,'U1',i*20) for i in range(len(values))]}
    reads={i:(pin,['DATA'+str(i)]) for i,pin in enumerate(values)}
    return rows,reads


def test_missing_and_impossible_numbers_require_catalog_and_three_anchors():
    for missing in (None,'0'):
        rows,reads=fixture(['1','2',missing,'4','5'])
        result=recover_sequences(rows,reads,{'U1':'test-part'},20,numbers=lambda value:set('12345'))
        assert result==[('U1',missing,'3')]
        assert reads[2]==('3',['DATA2'])


def test_functionally_reordered_symbol_is_not_forced_into_package_order():
    rows,reads=fixture(['1','5',None,'3','2'])
    assert not recover_sequences(rows,reads,{'U1':'test-part'},20,numbers=lambda value:set('12345'))
    assert reads[2][0] is None


def test_ambiguous_package_and_two_anchor_rows_are_left_unresolved():
    rows,reads=fixture(['1',None,None,'4',None])
    assert not recover_sequences(rows,reads,{'U1':'test-part'},20,numbers=lambda value:set('12345'))
    assert not recover_sequences(rows,reads,{'U1':'test-part'},20,numbers=lambda value:None)


def test_catalog_bounds_prevent_sequential_but_impossible_pin():
    rows,reads=fixture(['2','3','4',None,'6'])
    assert not recover_sequences(rows,reads,{'U1':'test-part'},20,numbers=lambda value:set('1234'))
    assert reads[3][0] is None


def test_crop_observation_needs_two_local_anchors_and_keeps_function_labels_internal(monkeypatch):
    from types import SimpleNamespace
    from app import catalog_pin_solver as solver
    from app.roi_vision import ComponentCrop
    from app.digital_vision import Page
    import numpy as np
    page=Page(np.zeros((500,500),np.uint8),None,None,None,None)
    rows=[(i,0,100,120+20*i,1,0,'U1') for i in range(3)]
    reads={0:('1',None),1:(None,['DATA']),2:('3',None)}
    proposal=ComponentCrop.model_validate({'ref_des':'U1','part_name':'Example123','pins':[
        {'pin_number':str(i),'internal_label':'P0.02','side':'left'} for i in (1,2,3)]})
    reader=SimpleNamespace(query=lambda *args,**kwargs:proposal)
    monkeypatch.setattr(solver,'pin_tables',lambda value:[{'pins':{str(i):['P0.02'] for i in (1,2,3)}}])
    changed=solver.component_crop_pins(reader,page,[('U1',150,150,(100,100,200,200))],{'U1':'Example123'},rows,reads,20)
    assert changed==[('U1',None,'2')] and reads[1]==('2',['DATA'])
    assert all(row['role']=='internal_pin_label' for row in page.internal_pin_labels)
    reads={0:('1',None),1:(None,None),2:(None,None)}
    assert not solver.component_crop_pins(reader,page,[('U1',150,150,(100,100,200,200))],{'U1':'Example123'},rows,reads,20)
