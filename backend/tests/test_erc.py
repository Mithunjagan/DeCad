from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.erc import erc_self_heal
from app.ingestion import Circuit


def snap_graph():
    return {'components':[{'ref':'R1','value':'10K'},{'ref':'U1','value':'PART'}],
            'nets':[{'name':'N00001','nodes':[{'ref':'R1','pin':'1'}]},
                    {'name':'OUT','nodes':[{'ref':'U1','pin':'4'}]}],
            'image_metadata':{'width':200,'height':100,'mask_complete':False,
                'pin_anchors':[{'ref':'R1','pin':'1','x':10,'y':20,'direction':[1,0]},
                               {'ref':'R1','pin':'2','x':0,'y':20,'direction':[-1,0]},
                               {'ref':'U1','pin':'4','x':60,'y':20,'wire':0,'confidence':.9,'physical_net':2}],
                'wires':[{'id':0,'p0':[16,20],'p1':[60,20],'traced_physical_net':2}]}}


def test_passive_snap_is_local_outward_and_preserves_unrelated_assignments():
    graph=snap_graph();before=deepcopy(graph)
    found=erc_self_heal(graph)
    assert len(found['nets'])==1 and {p['ref'] for p in found['nets'][0]['nodes']}=={'R1','U1'}
    assert before==graph
    assert found['image_metadata']['erc_actions'][0]['kind']=='dangling_passive_snap'


@pytest.mark.parametrize('change',['far','behind','unmasked','uncorroborated'])
def test_passive_snap_rejects_unsupported_local_connection(change):
    graph=snap_graph();m=graph['image_metadata']
    if change=='far':m['wires'][0]['p0']=[19,20]
    if change=='behind':m['pin_anchors'][0]['direction']=[-1,0]
    if change=='unmasked':m['unverified_body_regions']=[[11,10,18,30]]
    if change=='uncorroborated':m['pin_anchors'][2]['physical_net']=None
    assert erc_self_heal(graph)['nets']==graph['nets']


def test_image_duplicates_are_flagged_but_manual_json_stays_strict():
    graph=snap_graph();graph['nets'][1]['nodes'].append({'ref':'R1','pin':'1'})
    with pytest.raises(ValidationError):Circuit.model_validate(graph)
    found=Circuit.from_image_graph(graph)
    assert any('observed more than once' in w for w in found.warnings)
    assert len([(p.ref,p.pin) for n in found.nets for p in n.nodes])==2


def power_graph(confidence=.4):
    return {'components':[{'ref':'U1','value':'PART'}],
            'nets':[{'name':'N00001','nodes':[{'ref':'U1','pin':'1'},{'ref':'U1','pin':'2'}]}],
            'image_metadata':{'width':100,'height':100,
                'pin_anchors':[{'ref':'U1','pin':'1','x':10,'y':20,'graph_node':'A'},
                               {'ref':'U1','pin':'2','x':90,'y':20,'graph_node':'B'}],
                'wire_edges':[{'id':'E0','a':'A','b':'B','confidence':confidence,'source':'wire_trace','points':[[10,20],[90,20]]}],
                'external_labels':[{'text':'VCC'},{'text':'GND'}],
                'label_anchors':[{'index':0,'graph_node':'A'},{'index':1,'graph_node':'B'}]}}


def test_power_ground_split_cuts_only_uncertain_measured_path_and_is_idempotent():
    result=erc_self_heal(power_graph())
    assert {n['name'] for n in result['nets']}=={'VCC','GND'}
    assert result['image_metadata']['erc_disabled_edges']==['E0']
    again=erc_self_heal(result)
    assert again==result


def test_verified_short_is_flagged_and_confident_named_assignments_preserved():
    graph=power_graph(.95)
    assert erc_self_heal(graph)['nets']==graph['nets']
    graph=power_graph();graph['nets'][0]['name']='SOURCE_LABEL'
    result=erc_self_heal(graph)
    assert result['nets']==graph['nets']
    assert result['image_metadata']['erc_actions'][0]['review']


def test_orphan_label_attaches_only_to_unique_parallel_corroborated_wire():
    graph=snap_graph();graph['nets'][1]['name']='N00002';graph['nets']=graph['nets'][1:]
    m=graph['image_metadata'];m['external_labels']=[{'text':'DATA','bbox':[30,6,60,15],
        'vertical':False,'wire':None,'confidence':.99,'role':'external_net_label'}]
    found=erc_self_heal(graph)
    assert found['nets'][0]['name']=='DATA'
    graph['nets'][0]['name']='CONFIDENT'
    assert erc_self_heal(graph)['nets']==graph['nets']
