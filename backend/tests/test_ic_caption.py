from app import digital_vision as dv
from app.ic_caption import recover, literal_marking


def test_generic_markings_do_not_require_a_vendor_prefix_list():
    assert literal_marking('Wio-SX1262')
    assert literal_marking('STM32F413RGT6')
    assert literal_marking('LM358')
    assert not literal_marking('U123')
    assert not literal_marking('100nF')


def test_caption_needs_a_unique_literal_value_and_visible_pin_wires():
    ref=dv.Token('U1',.99,144,63,156,76)
    value=dv.Token('NewChip123',.99,123,84,177,96)
    body=(100,100,200,200)
    wires=[dv.Seg(70,130,100,130,2,True),dv.Seg(200,150,230,150,2,True)]
    assert recover([ref,value],[body],wires,10,{},[])==[('U1','NewChip123',body)]
    assert not recover([ref,value],[body],wires[:1],10,{},[])
    assert not recover([ref,value],[body],wires,10,{'U1':'OLD456'},[])
    alternate=dv.Token('Other456',.99,123,84,177,96)
    assert not recover([ref,value,alternate],[body],wires,10,{},[])
    assert not recover([ref,value],[body],wires,10,{'U2':'Old456'},[('U2',150,150,body)])


def test_pin_names_inside_the_outline_cannot_become_external_captions():
    ref=dv.Token('U1',.99,144,63,156,76)
    pin_name=dv.Token('GPIO12',.99,101,129,140,143)
    body=(100,100,200,200)
    wires=[dv.Seg(70,130,100,130,2,True),dv.Seg(200,150,230,150,2,True)]
    assert not recover([ref,pin_name],[body],wires,10,{},[])


def test_port_names_inside_new_ic_cannot_become_phantom_connectors():
    from app.ic_caption import external_connectors
    body=(100,100,200,200)
    port=dv.Token('P0.02',.99,120,120,160,140)
    external=dv.Token('P2-B12',.99,220,120,270,140)
    border=dv.Token('P1-04',.99,90,150,110,170)
    observations=[(port,'P0','02'),(external,'P2','B12'),(border,'P1','04')]
    assert external_connectors(observations,[body],10)==observations[1:]
    assert external_connectors(observations,[],10)==observations
