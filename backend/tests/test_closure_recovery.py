import cv2
import numpy as np
import pytest

from app.implicit_terminals import complete_amplifier_stubs
from app.provisional_terminals import complete_zero_pin_components,lead_gap_bodies
from app.digital_vision import Token
from app.ingestion import Circuit


def amplifier(missing='4',family=('1','2','3','4','5')):
    binary=np.zeros((320,400),np.uint8)
    polygon=[[150,80],[150,240],[290,160]]
    cv2.polylines(binary,[np.array(polygon)],True,255,2)
    ends=[(150,120),(150,200),(290,160),(185,80),(185,240)]
    for (x,y),(xx,yy) in zip(ends,[(50,120),(50,200),(370,160),(185,20),(185,300)]):
        cv2.line(binary,(x,y),(xx,yy),255,2)
    anchors=[dict(ref='U9',pin=p,x=x,y=y,confidence=.95) for p,(x,y) in zip(family,ends) if p!=missing]
    return binary,polygon,anchors


@pytest.mark.parametrize('family,missing',[(('1','2','3','4','5'),'4'),(('2','3','4','6','7'),'6'),(('1','2','3','4','8'),'4')])
def test_standard_amplifier_completes_only_unique_inventory_on_five_leads(family,missing):
    image,polygon,anchors=amplifier(missing,family)
    found=complete_amplifier_stubs(image,'U9',[150,80,290,240],polygon,anchors,20)
    assert len(found)==1 and found[0]['pin']==missing


def test_standard_amplifier_abstains_on_ambiguous_family_or_missing_wire():
    image,polygon,anchors=amplifier('5')
    assert not complete_amplifier_stubs(image,'U9',[150,80,290,240],polygon,anchors,20)
    image,polygon,anchors=amplifier('4');image[245:,:]=0
    assert not complete_amplifier_stubs(image,'U9',[150,80,290,240],polygon,anchors,20)
    assert not complete_amplifier_stubs(image,'U9',[150,80,290,240],polygon+[[200,160]],anchors,20)


def test_provisional_passive_stubs_remain_isolated_and_typed():
    gray=np.full((500,500),255,np.uint8)
    cv2.rectangle(gray,(180,220),(300,260),0,3)
    cv2.line(gray,(100,240),(180,240),0,2);cv2.line(gray,(300,240),(400,240),0,2)
    graph={'components':[{'ref':'R1','value':'1k','x':.48,'y':.36}], 'nets':[],
           'image_metadata':{'width':500,'height':500,'source_size':[500,500],'pin_anchors':[]}}
    tokens=[Token('R1',.99,220,165,260,195)]
    complete_zero_pin_components(graph,tokens,lambda b:gray[b[1]:b[3],b[0]:b[2]],30)
    result=Circuit.from_image_graph(graph).model_dump()
    assert len(result['nets'])==2 and all(len(n['nodes'])==1 for n in result['nets'])
    assert {p['pin'] for n in result['nets'] for p in n['nodes']}=={'1','2'}
    assert all(p['source']=='provisional_stub' and p['confidence']<=.35 for n in result['nets'] for p in n['nodes'])
    assert result['review_hotspots']


def test_unanchored_caption_is_preserved_in_quarantine_and_a_real_body_is_not():
    gray=np.full((500,500),255,np.uint8)
    token=Token('U4',.99,240,165,270,195)
    def graph():return {'components':[{'ref':'U4','value':'UNKNOWN','x':.5,'y':.36}], 'nets':[],
                        'image_metadata':{'width':500,'height':500,'source_size':[500,500],'pin_anchors':[]}}
    g=graph();original=g['components'][0].copy()
    complete_zero_pin_components(g,[token],lambda b:gray[b[1]:b[3],b[0]:b[2]],30)
    assert not g['components'] and g['image_metadata']['quarantined_components'][0]['component']==original
    cv2.rectangle(gray,(180,220),(340,380),0,3);g=graph()
    complete_zero_pin_components(g,[token],lambda b:gray[b[1]:b[3],b[0]:b[2]],30)
    assert g['components'] and not g['nets']


def test_ambiguous_body_ownership_uses_explicit_stub_identifiers():
    gray=np.full((500,500),255,np.uint8)
    for left in (120,280):cv2.rectangle(gray,(left,220),(left+100,260),0,3)
    for a,b in ((40,120),(220,280),(380,460)):cv2.line(gray,(a,240),(b,240),0,2)
    graph={'components':[{'ref':'R1','value':'1k','x':.5,'y':.36}],'nets':[],
           'image_metadata':{'width':500,'height':500,'source_size':[500,500],'pin_anchors':[]}}
    complete_zero_pin_components(graph,[Token('R1',.99,230,165,270,195)],lambda b:gray[b[1]:b[3],b[0]:b[2]],30)
    assert {p['pin'] for n in graph['nets'] for p in n['nodes']}=={'STUB1','STUB2'}
    assert all(len(n['nodes'])==1 for n in graph['nets'])


def test_scan_dropout_without_a_zigzag_is_not_a_passive_body():
    binary=np.zeros((400,300),np.uint8)
    cv2.line(binary,(150,30),(150,130),255,2);cv2.line(binary,(150,230),(150,370),255,2)
    assert not lead_gap_bodies(binary)


def test_opposing_leads_and_alternating_diagonals_support_a_resistor():
    binary=np.zeros((400,300),np.uint8)
    cv2.line(binary,(150,30),(150,130),255,2)
    cv2.polylines(binary,[np.array([[150,130],[130,140],[170,160],[130,180],[170,200],[150,210]])],False,255,2)
    cv2.line(binary,(150,210),(150,370),255,2)
    assert lead_gap_bodies(binary)
