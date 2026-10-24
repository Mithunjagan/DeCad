import io
import json
import zipfile
from copy import deepcopy

import pytest

from app import orcad_capture as oc, orcad_route as rt
from app.orcad_source_wires import candidates,named_nets
from app.orcad_source_symbols import fit


def observed_graph():
    return {'components':[{'ref':'J1','value':'Port'},{'ref':'J2','value':'Port'}],
            'nets':[{'name':'N0001','nodes':[{'ref':'J1','pin':'1'},{'ref':'J2','pin':'1'}]}],
            'image_metadata':{'width':1000,'pin_anchors':[
                {'ref':'J1','pin':'1','x':100,'y':100,'physical_net':7},
                {'ref':'J2','pin':'1','x':400,'y':100,'physical_net':7}],
                'wire_nodes':[{'id':'a','x':100,'y':100,'kind':'endpoint','physical_net':7},
                              {'id':'b','x':400,'y':100,'kind':'endpoint','physical_net':7}],
                'wire_edges':[{'id':'e','a':'a','b':'b','points':[[100,100],[400,100]],'physical_net':7,'confidence':.95}]}}


def test_source_coordinates_use_processed_frame_once_even_with_nonidentity_affine():
    graph=observed_graph();graph['image_metadata']['source_affine']=[[2,0,100],[0,2,200]]
    paths,_=candidates(graph,1000,{'N0001':'N0001'},margin=300)
    assert paths[0]['path']==[(400,400),(700,400)]


def test_reviewed_correction_rejects_stale_source_root_instead_of_reconnecting_it():
    graph=observed_graph()
    graph['nets'][0]['nodes'].pop()
    graph['nets'].append({'name':'OTHER','nodes':[{'ref':'J2','pin':'1'}]})
    paths,report=candidates(graph,1000,{'N0001':'N0001','OTHER':'OTHER'})
    assert not paths and report['ambiguous_roots']==[7]
    assert 'contradicts' in report['rejected_edges'][0]['reason']


def test_synthetic_local_net_names_are_not_exported_as_source_labels():
    graph=observed_graph()
    graph['nets'] += [{'name':'N_ANALOG_8','nodes':[]},{'name':'VDD','nodes':[]},{'name':'CLOCK','nodes':[]}]
    graph['image_metadata']['physical_labels']=[{'labels':['CLOCK']}]
    assert named_nets(graph)=={'VDD','CLOCK'}
    graph['nets'].append({'name':'USER_DEFINED_SENSOR_77','nodes':[]})
    assert 'USER_DEFINED_SENSOR_77' in named_nets(graph)


def test_source_paths_are_retained_and_missing_geometry_is_audited():
    from test_orcad_route import page
    pg=page();pins={('U1','1'):'A',('U2','1'):'A'}
    paths=[{'id':'measured','net':'A','path':[(300,310),(640,310)]}]
    report={'accepted_edges':[],'rejected_edges':[],'source_junctions':[],'inferred_segments':[]}
    wires,summary=rt.route(pg,pins,oc._place,require_wires=True,source_paths=paths,source_report=report,named_aliases=set())
    assert report['retained_source_unit_edges']==0  # image fragments are hints only
    assert report['inferred_segments']  # continuous routes originate at actual pins
    assert all(not w[4] for w in wires)
    pg['wires']=[w[:4] for w in wires]
    assert rt.verify_visible_wires(pg,pins)['passed']


def test_explicit_four_way_junction_is_electrical_and_plain_crossing_is_not():
    from test_orcad_route import box_part
    pg={'parts':[box_part('A',0,0,[('1','R',10)]),box_part('B',0,60,[('1','R',10)])],
        'wires':[[70,10,200,10],[70,70,140,70],[140,70,140,0]]}
    pins={('A','1'):'A',('B','1'):'B'}
    assert rt.verify_visible_wires(pg,pins)['passed']
    pg['junctions']=[[140,10]]
    assert rt.verify_visible_wires(pg,pins)['shorted_nets']==[['A','B']]


def test_library_fit_cannot_remap_pin_numbers_or_reverse_terminal_directions():
    definition={'pins':[['1',-10,0,-20,0],['2',10,0,20,0]],'vectors':[]}
    section={'section':0,'vectors':[['BOX',0,0,20,20]],'pins':{
        '1':{'hotspot':[-10,10],'start':[0,10]},'3':{'hotspot':[30,10],'start':[20,10]}}}
    assert fit(section,definition) is None
    section['pins']['2']=section['pins'].pop('3')
    match=fit(section,definition)
    assert match and {p[0] for p in match['pins']}=={'1','2'}


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('scale',[.5,2])
def test_library_geometry_fit_generalizes_across_rotations_scales_and_non_numeric_ids(rotation,scale):
    section={'section':0,'vectors':[['BOX',0,0,20,20]],'pins':{
        'B12':{'hotspot':[-10,10],'start':[0,10]},
        'OUT':{'hotspot':[30,10],'start':[20,10]},
        'V+':{'hotspot':[10,-10],'start':[10,0]}}}
    def transform(point):
        x,y=point
        for _ in range(rotation):x,y=y,-x
        return [scale*x+37,scale*y-19]
    definition={'pins':[[key,*transform(p['start']),*transform(p['hotspot'])] for key,p in section['pins'].items()]}
    match=fit(section,definition)
    assert match and match['error']<1e-6
    assert {p[0] for p in match['pins']}=={'B12','OUT','V+'}


@pytest.mark.parametrize('scale',[1000,2000,4000])
@pytest.mark.parametrize('offset',[0,70])
def test_observed_conductor_transform_has_no_sample_specific_coordinates(scale,offset):
    graph=observed_graph()
    for node in graph['image_metadata']['wire_nodes']:node['x']+=offset
    for anchor in graph['image_metadata']['pin_anchors']:anchor['x']+=offset
    for point in graph['image_metadata']['wire_edges'][0]['points']:point[0]+=offset
    paths,_=candidates(graph,scale,{'N0001':'N0001'},margin=300)
    assert len(paths)==1
    assert abs(paths[0]['path'][0][0]-(300+(100+offset)*scale/1000))<=5
    assert abs(paths[0]['path'][-1][0]-(300+(400+offset)*scale/1000))<=5


@pytest.mark.skipif(not oc.available(),reason='Actual Capture database required')
def test_native_source_export_has_unaliased_local_wires_and_preserves_exact_groups(tmp_path):
    from app.observed_export import orcad_bundle
    graph=observed_graph()
    data,report=orcad_bundle('physical-source',graph,tmp_path)
    assert report['passed'] and report['native_readback']
    assert report['electrical_group_errors']==[]
    assert report['routing']['visible_wire_verification']['passed']
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():(tmp_path/name).write_bytes(archive.read(name))
    pg=oc.drawing(tmp_path/'physical-source.DSN')[0]
    assert not pg['aliases']
    assert all(p['display_properties']['Value']=='Port' for p in pg['parts'])
    assert len(report['native_pin_memberships'])==2
    assert len({p['native_net'] for p in report['native_pin_memberships']})==1


def test_visual_comparison_refuses_a_singular_source_transform(tmp_path):
    from PIL import Image
    from app.orcad_visual_audit import comparison_svg
    image=tmp_path/'source.png';Image.new('RGB',(50,50),'white').save(image)
    graph=observed_graph();graph['image_metadata']['source_affine']=[[1,2,0],[2,4,0]]
    assert comparison_svg(graph,image,'<svg></svg>','Unknown',1000) is None
    graph['image_metadata']['source_affine']=[[2,0,0],[0,2,0]]
    assert 'matrix(' in comparison_svg(graph,image,'<svg></svg>','Unknown',1000)
