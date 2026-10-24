from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest

from app.digital_vision import Token
from app.implicit_terminals import passive_observations,analog_graph,quarantine_unverified
from app.terminal_equivalence import symmetric_mapping
from app.ingestion import Circuit
from app.symbol_barriers import capacitor_gap,port_label_wire,capacitor_pin_labels
from app import digital_vision as dv
from app.ic_caption import side_captions


@pytest.mark.parametrize('vertical',[False,True])
def test_opposing_passive_leads_require_body_and_both_conductors(vertical):
    gray=np.full((300,300),255,np.uint8)
    cv2.rectangle(gray,(110,140),(190,170),0,3)
    cv2.line(gray,(60,155),(110,155),0,2);cv2.line(gray,(190,155),(240,155),0,2)
    token=Token('R1',.99,125,95,155,125)
    if vertical:
        gray=cv2.rotate(gray,cv2.ROTATE_90_CLOCKWISE)
        token=Token('R1',.99,175,125,205,155)
    found=passive_observations(gray,[token],{'R1'},32)
    assert len(found)==1
    points=found[0]['points'];assert points[0][1]<points[1][1] if vertical else points[0][0]<points[1][0]
    gray[:]=255
    assert not passive_observations(gray,[token],{'R1'},32)


def test_refdes_without_triangle_cannot_replace_digital_graph():
    assert analog_graph(np.full((200,200),255,np.uint8),[Token('U1',.99,10,10,40,30)],
                        {'components':[{'ref':'U1','value':'AD8051'}],'nets':[]}) is None


def test_terminal_swap_is_evaluation_only_and_never_applies_to_diodes():
    truth={'components':[{'ref':'R1','value':'1k'},{'ref':'D1','value':'D'}],
           'nets':[{'name':'A','nodes':[{'ref':'R1','pin':'1'},{'ref':'D1','pin':'1'}]},
                   {'name':'B','nodes':[{'ref':'R1','pin':'2'},{'ref':'D1','pin':'2'}]}]}
    candidate=deepcopy(truth)
    for net in candidate['nets']:
        for node in net['nodes']:
            if node['ref']=='R1':node['pin']=str(3-int(node['pin']))
    saved=deepcopy(candidate);equivalent,receipt=symmetric_mapping(truth,candidate)
    assert equivalent==truth and receipt['swapped_refs']==['R1'] and candidate==saved


def test_synthesized_source_survives_canonical_validation():
    graph={'components':[{'ref':'C1','value':'100n','library':'Device:C'}],
           'nets':[{'name':'N1','nodes':[{'ref':'C1','pin':'1','source':'implicit_passive_terminal'}]}]}
    assert Circuit.model_validate(graph).nets[0].nodes[0].source=='implicit_passive_terminal'


@pytest.mark.parametrize('horizontal',[False,True])
def test_capacitor_plates_are_a_barrier_but_a_scan_gap_is_not(horizontal):
    binary=np.zeros((150,150),np.uint8)
    cv2.line(binary,(20,75),(65,75),255,2);cv2.line(binary,(80,75),(130,75),255,2)
    cv2.line(binary,(65,58),(65,92),255,3);cv2.line(binary,(80,58),(80,92),255,3)
    if not horizontal:binary=binary.T.copy()
    assert capacitor_gap(binary,horizontal,75,65,80,37)
    binary[:]=0
    assert not capacitor_gap(binary,horizontal,75,65,80,37)


def test_side_caption_owns_outline_independently_of_internal_ocr_alias():
    box=(100,100,250,250)
    tokens=[Token('U6',.99,60,145,85,165),Token('ATECC608A',.99,0,175,85,195),
            Token('U504',.99,150,140,200,160)]
    wires=[dv.Seg(70,120,100,120,2,True),dv.Seg(250,145,280,145,2,True),
           dv.Seg(250,185,280,185,2,True),dv.Seg(175,70,175,100,2,False)]
    assert side_captions(tokens,[box],wires,20)==[('U6','ATECC608A',box)]
    assert not side_captions(tokens,[box],wires[:1],20)


def test_port_text_names_centerline_instead_of_its_arrow_outline():
    binary=np.zeros((150,300),np.uint8)
    cv2.polylines(binary,[np.array([[100,50],[240,50],[240,110],[100,110],[75,80]],np.int32)],True,255,3)
    cv2.line(binary,(10,80),(75,80),255,2)
    wires=[dv.Seg(10,80,76,80,2,True),dv.Seg(100,110,240,110,2,True)]
    # OCR boxes can extend a few pixels beyond the visible leftmost glyph.
    assert port_label_wire(binary,Token('VBUS',.99,74,56,220,105),wires,37)==0


def test_dc_barrier_does_not_change_the_legacy_terminal_coordinate_system():
    binary=np.zeros((150,180),np.uint8)
    cv2.line(binary,(20,75),(65,75),255,2);cv2.line(binary,(80,75),(130,75),255,2)
    cv2.line(binary,(65,58),(65,92),255,3);cv2.line(binary,(80,58),(80,92),255,3)
    page=dv.Page(255-binary,binary,binary,binary,np.zeros_like(binary))
    raw=[dv.Seg(20,75,65,75,2,True),dv.Seg(80,75,130,75,2,True)]
    legacy=dv._bridge(raw,page);page.dc_segments=dv._bridge(raw,page,respect_capacitors=True)
    assert len(legacy)==1 and len(page.dc_segments)==2
    labels=[{'text':'GND','bbox':[20,35,45,65],'wire':0,'confidence':.99},
            {'text':'VBUS','bbox':[95,45,125,70],'wire':0,'confidence':.99}]
    anchors={('U1',str(p)):{'wire':0,'x':130,'y':75,'body':[130,50,165,120]} for p in range(1,5)}
    names,receipt=capacitor_pin_labels(page,legacy,dv.DSU(1),anchors,labels,[],[],[],37)
    assert names['U1','3']=='VBUS' and receipt
    assert legacy[0].ends()==((20,75),(130,75))


@pytest.mark.parametrize('kind',['L','D'])
def test_recognized_inductor_and_diode_need_two_visible_leads(kind):
    gray=np.full((300,300),255,np.uint8)
    if kind=='D':
        cv2.polylines(gray,[np.array([[110,130],[110,180],[180,155]],np.int32)],True,0,3)
        cv2.line(gray,(187,130),(187,180),0,3);right=187
    else:
        cv2.rectangle(gray,(110,140),(190,170),0,3);right=190
    cv2.line(gray,(60,155),(110,155),0,2);cv2.line(gray,(right,155),(240,155),0,2)
    token=Token(kind+'1',.99,125,85,155,115)
    found=passive_observations(gray,[token],{kind+'1'},32)
    assert found and found[0]['points'][0][0]<found[0]['points'][1][0]


def test_zero_pin_alias_quarantine_preserves_real_unreadable_components():
    graph={'components':[{'ref':'R1','value':'1k'},{'ref':'U58','value':'UNKNOWN'},
                         {'ref':'U4','value':'UNKNOWN'}],
           'nets':[{'name':'A','nodes':[{'ref':'R1','pin':'1'}]}],
           'image_metadata':{'verified_component_refs':['U4']}}
    tokens=[Token('U58',.98,10,10,50,30),Token('U4',.4,80,10,110,30)]
    quarantine_unverified(graph,tokens,lambda t:('USB',.99))
    assert {c['ref'] for c in graph['components']}=={'R1','U4'}
    assert graph['image_metadata']['quarantined_components'][0]['component']['ref']=='U58'
    assert graph['image_metadata']['review_hotspots'][0]['ref']=='U58'


@pytest.mark.parametrize('label',['P0.00','P0.31','P0.00/XL1D2','P0.31/AIN7A8','P1.02/SPI_MOSI/TX','P0.08N1','P1.00_PDM_CLK'])
def test_gpio_dot_port_and_alternate_functions_are_not_connectors(label):
    assert dv.GPIO_PORT_RE.fullmatch(label)


@pytest.mark.parametrize('label',['P1-B5','P1','J1','CON1','P0-31','P0.314','P0.31-B5'])
def test_gpio_guard_does_not_change_ordinary_connector_tokens(label):
    assert not dv.GPIO_PORT_RE.fullmatch(label)


def test_observed_pin_label_pair_requires_continuous_outside_ink(monkeypatch):
    from app import observed_terminal_pairs as recovery
    monkeypatch.setattr(recovery,'local_package_numbers',lambda value:set(map(str,range(1,9))))
    gray=np.full((300,300),255,np.uint8)
    cv2.rectangle(gray,(100,50),(200,150),0,2);cv2.line(gray,(197,150),(197,265),0,2)
    def graph():
        return {'components':[{'ref':'U1','value':'Known8Pin'}],
                'nets':[{'name':'OLD'+str(p),'nodes':[{'ref':'U1','pin':str(p)}]} for p in range(1,5)],
                'image_metadata':{'width':300,'height':300,'character_height':20,
                    'pin_anchors':[{'ref':'U1','pin':str(p),'x':100,'y':60+p*10,'body':[100,50,200,150]} for p in range(1,5)]}}
    tokens=[Token('5',.99,177,163,192,181,True),Token('NET5',.99,177,194,192,232,True)]
    crop=lambda b:gray[b[1]:b[3],b[0]:b[2]]
    g=graph();actions=recovery.recover_observed_pairs(g,tokens,crop)
    assert actions and any(n['name']=='NET5' and n['nodes']==[{'ref':'U1','pin':'5'}] for n in g['nets'])
    assert len([p for n in g['nets'] for p in n['nodes'] if p['pin'] in ('1','2','3','4')])==4
    gray[160:270,:]=255
    assert not recovery.recover_observed_pairs(graph(),tokens,crop)
