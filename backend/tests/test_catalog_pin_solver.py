from app.catalog_pin_solver import recover_sequences


def test_stacked_partition_is_literal_monotonic_and_unambiguous():
    from app.catalog_pin_solver import split_stacked_digits
    assert split_stacked_digits('789',3,16)==('7','8','9')
    assert split_stacked_digits('987',3,16)==('9','8','7')
    assert split_stacked_digits('1213',2,24)==('12','13')
    assert split_stacked_digits('797',3,16) is None


def test_row_grammar_needs_consensus_and_resolves_only_active_rows():
    from app.catalog_pin_solver import row_grammar
    assert row_grammar({'B2','B7','B13','813'})=={'813':'B13'}
    assert row_grammar({'B2','B7','813'})=={}
    assert row_grammar({'D2','O7','D13','013'})=={}
    assert row_grammar({'B2','B7','B13','819'})=={}


def test_parallel_stub_label_token_has_only_one_owner():
    from types import SimpleNamespace
    from app.catalog_pin_solver import exclusive_strip_labels
    token=SimpleNamespace(text='CONTROL',x0=0,y0=8,x1=30,y1=18)
    edges=[(0,0,40,20,1,0,'IC7'),(1,1,40,40,1,0,'IC7')]
    reads={0:('2',['CONTROL']),1:('3',['CONTROL'])}
    exclusive_strip_labels(edges,reads,[token],10)
    assert reads=={0:('2',['CONTROL']),1:('3',None)}


def test_catalog_ceiling_preserves_real_large_packages(monkeypatch):
    from app import catalog_pin_solver as solver
    monkeypatch.setattr(solver,'pin_tables',lambda value:[{'pins':{str(i):[] for i in range(1,145)}}])
    assert solver.pin_ceiling('large-package',['2','3','4'],3)==144


def test_export_normalization_is_private_idempotent_and_catalog_bounded(monkeypatch):
    from copy import deepcopy
    from app import catalog_pin_solver as solver
    monkeypatch.setattr(solver,'pin_tables',lambda value:[{'pins':{str(i):[] for i in range(1,17)}}])
    graph={'components':[{'ref':'IC4','value':'PART'}],
           'nets':[{'name':'LINE','nodes':[{'ref':'IC4','pin':'123'}]}]}
    original=deepcopy(graph);normalized=solver.normalize_graph(graph)
    assert graph==original and [p['pin'] for p in normalized['nets'][0]['nodes']]==['1','2','3']
    assert solver.normalize_graph(normalized)==normalized


def test_saved_graph_label_theft_requires_disconnected_physical_trees():
    from app.catalog_pin_solver import normalize_graph
    graph={'components':[{'ref':'IC4','value':'UNKNOWN'}],
           'nets':[{'name':'CONTROL','nodes':[{'ref':'IC4','pin':'2'},{'ref':'IC4','pin':'3'}]}],
           'image_metadata':{'pin_anchors':[
               {'ref':'IC4','pin':'2','x':30,'y':20,'direction':[1,0],'physical_net':2,'wire':2},
               {'ref':'IC4','pin':'3','x':30,'y':40,'direction':[1,0],'physical_net':3,'wire':3}],
               'external_labels':[{'text':'CONTROL','bbox':[40,32,80,40],'wire':3}]}}
    normalized=normalize_graph(graph)
    assert normalized['nets'][0]['nodes']==[{'ref':'IC4','pin':'3'}]
    graph['image_metadata']['pin_anchors'][1]['physical_net']=2
    assert normalize_graph(graph)['nets'][0]['nodes']==graph['nets'][0]['nodes']


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
