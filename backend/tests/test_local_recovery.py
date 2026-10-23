from copy import deepcopy
import pytest

from app.local_recovery import recover_locally,repair_impossible_numbers


def fixture():
    return {'components':[{'ref':'R1','value':'10K'}],
            'nets':[{'name':'N00001','nodes':[{'ref':'R1','pin':'1'}]}],
            'image_metadata':{'mask_complete':False,'unmasked_components':['U9'],
                'pin_anchors':[{'ref':'R1','pin':'1','x':10,'y':20,'direction':[1,0],'wire':0}],
                'wires':[{'id':0,'p0':[10,20],'p1':[100,20],'bus':False}],
                'external_labels':[{'text':'SIGNAL','bbox':[60,8,90,20],'confidence':.99,
                                    'role':'external_net_label','vertical':False,'wire':0}],
                'wire_edges':[{'points':[[10,20],[100,20]],'confidence':.9}]}}


def test_an_unrelated_unresolved_terminal_does_not_disable_local_recovery():
    graph=fixture();original=deepcopy(graph)
    graph['image_metadata']['pin_anchors'].append({'ref':'U9','pin':'5','x':400,'y':400,'physical_net':None})
    result=recover_locally(graph)
    assert result['nets'][0]['name']=='SIGNAL'
    assert original['nets'][0]['name']=='N00001'
    assert result['image_metadata']['local_recovery_actions'][0]['pin']=='1'


def test_named_baseline_assignments_are_preserved():
    graph=fixture();graph['nets'][0]['name']='CONFIDENT'
    assert recover_locally(graph)['nets']==graph['nets']


def test_explicit_passive_rejects_impossible_observation_without_inventing_a_pin():
    graph=fixture();graph['components'][0]['library']='Device:R'
    graph['nets'][0]['name']='SIGNAL'
    graph['nets'][0]['nodes'] += [{'ref':'R1','pin':'4'}]
    graph['nets'].append({'name':'SUPPLY','nodes':[{'ref':'R1','pin':'2'}]})
    graph['image_metadata']['pin_anchors'] += [{'ref':'R1','pin':'4','x':90,'y':20},
        {'ref':'R1','pin':'2','x':0,'y':20,'direction':[-1,0]}]
    result=recover_locally(graph)
    assert result['nets']==[{'name':'SIGNAL','nodes':[{'ref':'R1','pin':'1'}]},
                            {'name':'SUPPLY','nodes':[{'ref':'R1','pin':'2'}]}]
    rejected=result['image_metadata']['rejected_pin_observations']
    assert rejected[0]['node']=={'ref':'R1','pin':'4'} and rejected[0]['net']=='SIGNAL'
    assert len(result['image_metadata']['pin_anchors'])==2
    assert 'R1.4' in result['warnings'][0]
    assert recover_locally(result)['image_metadata']['rejected_pin_observations']==rejected
    assert len(graph['nets'][0]['nodes'])==2


def test_unconfirmed_passive_identity_keeps_observations_for_review():
    graph=fixture();graph['components'][0]['library']='Device:R'
    graph['nets'][0]['nodes'][0]['pin']='63'
    graph['image_metadata']['pin_anchors'][0]['pin']='63'
    assert recover_locally(graph)['nets'][0]['nodes']==graph['nets'][0]['nodes']


@pytest.mark.parametrize('position,direction',[
    ((0,40),[-1,0]),  # parallel rows are not one resistor
    ((0,20),[1,0]),   # same-side terminals do not corroborate its body
    ((40,20),[-1,0]), # both arrows point into the supposed body
])
def test_passive_constraint_requires_opposed_collinear_outward_anchors(position,direction):
    graph=fixture();graph['components'][0]['library']='Device:R'
    graph['nets'][0]['nodes'] += [{'ref':'R1','pin':'4'},{'ref':'R1','pin':'2'}]
    graph['image_metadata']['pin_anchors'] += [
        {'ref':'R1','pin':'4','x':90,'y':20},
        {'ref':'R1','pin':'2','x':position[0],'y':position[1],'direction':direction}]
    result=recover_locally(graph)
    assert result['nets'][0]['nodes']==graph['nets'][0]['nodes']
    assert not result['image_metadata'].get('rejected_pin_observations')


def test_reference_prefix_alone_cannot_reject_multiterminal_device_pins():
    graph=fixture();graph['nets'][0]['nodes'][0]['pin']='4'
    graph['image_metadata']['pin_anchors'][0]['pin']='4'
    assert recover_locally(graph)['nets'][0]['nodes']==graph['nets'][0]['nodes']
    graph['components'][0]['library']='Device:R_Pack04'
    assert recover_locally(graph)['nets'][0]['nodes']==graph['nets'][0]['nodes']


def test_local_path_crossing_unmasked_body_is_rejected():
    graph=fixture();graph['image_metadata']['unverified_body_regions']=[[40,10,55,30]]
    assert recover_locally(graph)['nets']==graph['nets']


def test_missing_local_skeleton_cannot_be_bridged_by_long_hough_segment():
    graph=fixture();graph['image_metadata']['wire_edges'][0]['points']=[[60,20],[100,20]]
    assert recover_locally(graph)['nets']==graph['nets']


def test_existing_multi_pin_connections_are_not_split_by_one_pin_proposal():
    graph=fixture();graph['nets'][0]['nodes'].append({'ref':'R1','pin':'2'})
    assert recover_locally(graph)['nets']==graph['nets']


def test_competing_labels_and_bus_trunks_do_not_create_connections():
    graph=fixture();label=deepcopy(graph['image_metadata']['external_labels'][0]);label['text']='OTHER'
    graph['image_metadata']['external_labels'].append(label)
    assert recover_locally(graph)['nets']==graph['nets']
    graph=fixture();graph['image_metadata']['wires'][0]['bus']=True
    assert recover_locally(graph)['nets']==graph['nets']


def numbered():
    pins=['12','113','14','15']
    graph={'components':[{'ref':'U1','value':'PACKAGE'}],
           'nets':[{'name':f'LINE{i}','nodes':[{'ref':'U1','pin':p}]} for i,p in enumerate(pins)]}
    metadata={'pin_anchors':[{'ref':'U1','pin':p,'x':20,'y':20+10*i,'direction':[1,0],
                              'body':[0,0,20,80]} for i,p in enumerate(pins)]}
    return graph,metadata


def test_fused_digit_requires_package_and_three_ordered_observations():
    graph,metadata=numbered()
    actions=repair_impossible_numbers(graph,metadata,numbers=lambda v:{str(i) for i in range(1,17)})
    assert [(a['old_pin'],a['pin']) for a in actions]==[('113','13')]
    assert graph['nets'][1]['nodes'][0]['pin']=='13'


def test_legitimate_large_package_pin_and_conflicting_order_are_preserved():
    graph,metadata=numbered()
    assert not repair_impossible_numbers(graph,metadata,numbers=lambda v:{str(i) for i in range(1,145)})
    graph,metadata=numbered();metadata['pin_anchors'][2]['pin']='10'
    assert not repair_impossible_numbers(graph,metadata,numbers=lambda v:{str(i) for i in range(1,17)})
