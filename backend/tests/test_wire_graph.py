import cv2
import numpy as np

from app.digital_vision import Page,Seg,Token
from app.wire_graph import trace,heal_gaps,mask_canvas,skeletonize,dot_score


def cross(dot=False,t=False):
    ink=np.zeros((100,100),np.uint8)
    cv2.line(ink,(10,50),(90,50),255,1)
    cv2.line(ink,(50,10),(50,50 if t else 90),255,1)
    if dot:cv2.circle(ink,(50,50),4,255,-1)
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    lines=[Seg(10,50,90,50,1,True),Seg(50,10,50,50 if t else 90,1,False)]
    points=[(10,50),(90,50),(50,10)]+([] if t else [(50,90)])
    pins={(f'R{i+1}','1'):{'x':x,'y':y,'direction':[1,0],'wire':0} for i,(x,y) in enumerate(points)}
    return page,lines,pins


def roots(graph):return {(p['ref'],p['pin']):p['physical_net'] for p in graph['pin_anchors']}


def test_plain_crossing_keeps_opposite_conductors_separate():
    page,lines,pins=cross()
    graph=trace(page,[],[],lines,pins)
    r=roots(graph)
    assert r['R1','1']==r['R2','1']
    assert r['R3','1']==r['R4','1']
    assert r['R1','1']!=r['R3','1']


def test_filled_dot_and_t_junction_connect_all_branches():
    for dot,t in ((True,False),(False,True)):
        page,lines,pins=cross(dot,t)
        graph=trace(page,[],[],lines,pins)
        assert len(set(roots(graph).values()))==1
    page,_,_=cross(True)
    assert dot_score(page.binary,50,50,1)>.7


def test_directional_closing_heals_scan_gaps_without_shorting_parallel_wires():
    ink=np.zeros((80,100),np.uint8)
    ink[20,10:40]=255;ink[20,42:90]=255
    ink[22,10:90]=255
    repaired,healed=heal_gaps(ink)
    assert repaired[20,40:42].all() and healed[20,40:42].all()
    assert not repaired[21].any()


def test_masked_body_outline_cannot_short_its_pin_terminals():
    ink=np.zeros((100,100),np.uint8)
    cv2.rectangle(ink,(40,30),(60,70),255,1)
    cv2.line(ink,(10,50),(40,50),255,1);cv2.line(ink,(60,50),(90,50),255,1)
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    lines=[Seg(10,50,40,50,1,True),Seg(60,50,90,50,1,True)]
    anchors={('U1','1'):{'x':40,'y':50,'direction':[-1,0],'wire':0},
             ('U1','2'):{'x':60,'y':50,'direction':[1,0],'wire':1}}
    graph=trace(page,[(40,30,60,70)],[],lines,anchors)
    r=roots(graph)
    assert None not in r.values() and r['U1','1']!=r['U1','2']


def test_text_erasure_preserves_a_verified_wire_through_the_box():
    ink=np.zeros((60,100),np.uint8)
    ink[30,5:95]=255;ink[20:30,30:35]=255
    masked=mask_canvas(ink,[],[Token('TEXT',.99,20,18,60,32)],[Seg(5,30,94,30,1,True)])
    assert masked[30,5:95].all() and not masked[20:29,20:60].any()


def test_banded_skeleton_keeps_long_wire_continuity_across_seams():
    ink=np.zeros((1300,90),np.uint8)
    cv2.line(ink,(40,10),(40,1290),255,3)
    thin=skeletonize(ink)
    assert all((thin[y]>0).sum()==1 for y in range(20,1280))


def test_curved_bridge_does_not_connect_the_crossed_wire():
    ink=np.zeros((100,100),np.uint8)
    cv2.line(ink,(10,50),(40,50),255,1)
    cv2.ellipse(ink,(50,50),(10,10),0,0,180,255,1)
    cv2.line(ink,(60,50),(90,50),255,1)
    cv2.line(ink,(55,10),(55,90),255,1)
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    segments=[Seg(10,50,40,50,1,True),Seg(60,50,90,50,1,True),Seg(55,10,55,90,1,False)]
    pins={(f'R{i+1}','1'):{'x':x,'y':y,'wire':0,'direction':[1,0]} for i,(x,y) in enumerate([(10,50),(90,50),(55,10),(55,90)])}
    graph=trace(page,[],[],segments,pins);r=roots(graph)
    assert r['R1','1']==r['R2','1'] and r['R3','1']==r['R4','1'] and r['R1','1']!=r['R3','1']


def test_bus_container_does_not_short_unlabelled_tap_members():
    ink=np.zeros((120,120),np.uint8)
    cv2.line(ink,(70,10),(70,110),255,5)
    cv2.line(ink,(10,30),(70,30),255,1);cv2.line(ink,(10,80),(70,80),255,1)
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    segments=[Seg(70,10,70,110,5,False,True),Seg(10,30,70,30,1,True),Seg(10,80,70,80,1,True)]
    pins={('U1','1'):{'x':10,'y':30,'wire':1},('U1','2'):{'x':10,'y':80,'wire':2}}
    r=roots(trace(page,[],[],segments,pins))
    assert r['U1','1']!=r['U1','2']


def test_preserving_pin_leads_does_not_fill_an_intentional_five_pixel_gap():
    ink=np.zeros((80,100),np.uint8);ink[30,10:40]=255;ink[30,45:90]=255
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    segments=[Seg(10,30,89,30,1,True)]  # legacy long-run bridge spans the gap
    pins={('R1','1'):{'x':10,'y':30,'wire':0},('R2','1'):{'x':89,'y':30,'wire':0}}
    r=roots(trace(page,[],[],segments,pins))
    assert r['R1','1']!=r['R2','1']


def test_text_mask_restoration_keeps_large_wire_gaps_open():
    ink=np.zeros((80,100),np.uint8);ink[30,10:40]=255;ink[30,45:90]=255
    masked=mask_canvas(ink,[],[Token('TEXT',.99,25,20,65,40)],[Seg(10,30,89,30,1,True)])
    repaired,_=heal_gaps(masked)
    assert not repaired[30,40:45].any()


def test_passive_symbol_ink_is_not_a_conductor_between_opposing_terminals():
    ink=np.zeros((100,120),np.uint8)
    cv2.line(ink,(10,50),(110,50),255,1)
    cv2.rectangle(ink,(45,43),(75,57),255,1)
    page=Page(255-ink,ink,None,None,np.zeros_like(ink))
    segments=[Seg(10,50,45,50,1,True),Seg(75,50,110,50,1,True)]
    anchors={('R1','1'):{'x':45,'y':50,'direction':[-1,0],'wire':0},
             ('R1','2'):{'x':75,'y':50,'direction':[1,0],'wire':1}}
    r=roots(trace(page,[],[],segments,anchors))
    assert None not in r.values() and r['R1','1']!=r['R1','2']


def test_unverified_body_does_not_move_an_observed_terminal():
    page,lines,pins=cross()
    pins['R1','1']['body']=[40,30,60,70]
    graph=trace(page,[],[],lines,pins)
    pin=next(p for p in graph['pin_anchors'] if p['ref']=='R1')
    assert pin['x']==10 and pin['y']==50


def test_pin_groups_can_split_a_legacy_segment_but_preserve_unmapped_groups():
    from app.digital_vision import DSU
    from app.wire_graph import reconcile_pin_groups
    old=DSU(2)
    wires={('R1','1'):0,('R2','1'):0,('R3','1'):1}
    anchors=[{'ref':'R1','pin':'1','physical_net':0},{'ref':'R2','pin':'1','physical_net':1},
             {'ref':'R3','pin':'1','physical_net':2}]
    groups,_,blocked=reconcile_pin_groups(old,wires,anchors)
    assert groups['R1','1']!=groups['R2','1'] and not blocked
    anchors[1]['physical_net']=None
    groups,_,blocked=reconcile_pin_groups(old,wires,anchors)
    assert groups['R1','1']==groups['R2','1']==0 and blocked=={0}


def test_production_reconciliation_requires_complete_terminal_anchoring():
    from app.digital_vision import DSU
    from app.wire_graph import reconcile_pin_groups
    old=DSU(3)
    wires={('U1','1'):0,('U1','2'):1,('U1','3'):2}
    anchors=[{'ref':'U1','pin':'1','physical_net':4},{'ref':'U1','pin':'2','physical_net':4},
             {'ref':'U1','pin':'3','physical_net':None}]
    groups,mapping,blocked=reconcile_pin_groups(old,wires,anchors,require_complete=True)
    assert groups==wires and not mapping and blocked=={0,1,2}


def test_fully_anchored_pins_cannot_certify_an_unmasked_unknown_symbol():
    from app.digital_vision import DSU
    from app.wire_graph import reconcile_pin_groups,unmasked_components
    locations={('U1','1'):{'x':20,'y':20,'wire':0},('U1','2'):{'x':40,'y':20,'wire':1}}
    missing=unmasked_components({'U1':'UNKNOWN'},locations,[])
    assert missing==['U1']
    anchors=[{'ref':'U1','pin':str(n),'physical_net':4} for n in (1,2)]
    groups,mapping,blocked=reconcile_pin_groups(DSU(2),{k:p['wire'] for k,p in locations.items()},anchors,
                                                require_complete=True,mask_complete=not missing)
    assert groups[('U1','1')]!=groups[('U1','2')] and not mapping and blocked=={0,1}


def test_observed_opposing_passive_terminals_certify_only_their_own_mask():
    from app.wire_graph import unmasked_components
    locations={('R1','1'):{'x':20,'y':20,'direction':[-1,0]},
               ('R1','2'):{'x':40,'y':20,'direction':[1,0]}}
    assert not unmasked_components({'R1':'10K'},locations,[])
    assert unmasked_components({'R1':'10K','C1':'1u'},locations,[])==['C1']


def test_numeric_power_labels_require_literal_unambiguous_package_pins():
    from app.wire_graph import power_pin_numbers
    def tables(value):
        if value=='EXACT':return [{'pins':{'1':{},'2':{},'3':{}}}]
        if value=='AMBIGUOUS':return [{'pins':{'1':{}}},{'pins':{'2':{}}}]
        return []
    allowed=power_pin_numbers({'R1':'10K','U1':'UNKNOWN','U2':'EXACT','U3':'AMBIGUOUS','U4':'MISSPELLED'},tables)
    assert allowed=={'R1':{'1','2'},'U2':{'1','2','3'}}


def test_resistor_network_is_not_masked_or_certified_as_a_two_pin_resistor():
    from app.wire_graph import unmasked_components,power_pin_numbers
    locations={('RN1','1'):{'x':20,'y':20,'direction':[-1,0]},
               ('RN1','2'):{'x':40,'y':20,'direction':[1,0]}}
    assert unmasked_components({'RN1':'10K'},locations,[])==['RN1']
    assert power_pin_numbers({'RN1':'10K'},lambda value:[])=={}
