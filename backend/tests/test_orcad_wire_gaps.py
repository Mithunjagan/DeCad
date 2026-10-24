from app import orcad_capture as oc, orcad_route as rt
from app.orcad_wire_gaps import endpoints,repair,source_support


def test_pin_membership_check_cannot_certify_a_dangling_branch():
    from test_orcad_route import page
    pg=page();pins={('U1','1'):'A',('U2','1'):'A'}
    pg['wires']=[[270,310,670,310],[450,310,450,400]]
    assert rt.verify_visible_wires(pg,pins)['passed']
    result=endpoints(pg)
    assert not result['passed'] and result['free_end_count']==1
    assert result['unterminated_wires']==[{'at':[450,400],'kind':'unterminated_wire'}]


def router_with_gap(second_net='A'):
    pg={'width':1000,'height':1000,'parts':[]}
    router=rt.Router(pg,{},oc._place)
    router.hotspots=set()
    router._commit('A',[(x,20) for x in range(20,24)])
    router._commit(second_net,[(x,20) for x in range(25,29)])
    return router


def test_short_collinear_source_supported_gap_is_physically_closed():
    router=router_with_gap();report={'accepted_edges':[]}
    added=repair(router,lambda a,b:1.0,report)
    assert len(added['A'])==2
    assert (25,20) in router.connected_cells('A',{(20,20)})
    assert len(report['source_supported_gap_repairs'])==1


def test_nearby_different_nets_are_never_joined_even_on_dark_pixels():
    router=router_with_gap('B');report={'accepted_edges':[]}
    assert not repair(router,lambda a,b:1.0,report)
    assert (25,20) not in router.connected_cells('A',{(20,20)})


def test_same_named_nearby_ends_do_not_override_blank_source_pixels():
    router=router_with_gap();report={'accepted_edges':[]}
    assert not repair(router,lambda a,b:.4,report)
    assert (25,20) not in router.connected_cells('A',{(20,20)})


def test_a_symbol_body_in_the_gap_is_not_overwritten():
    router=router_with_gap();router.blocked.add((24,20))
    assert not repair(router,lambda a,b:1.0,{'accepted_edges':[]})


def test_source_pixel_evidence_uses_inverse_affine_and_rejects_blank_gap(tmp_path):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(200,100),'white')
    ImageDraw.Draw(image).line((20,30,80,30),fill='black',width=2)
    path=tmp_path/'source.png';image.save(path)
    graph={'image_metadata':{'width':400,'source_affine':[[2,0,10],[0,2,0]]}}
    supported=source_support(graph,path,400)
    assert supported((350,360),(470,360))==1
    assert supported((350,400),(470,400))==0


def test_reviewed_singletons_are_reported_as_open_ends_not_closed_wires():
    pg={'parts':[{'pins':[{'hx':10,'hy':10}]}],'wires':[[10,10,40,10]]}
    result=endpoints(pg,[{'a':[10,10],'b':[40,10],'source':'isolated_terminal_stub'}])
    assert not result['passed'] and result['isolated_reviewed_terminals']==1
