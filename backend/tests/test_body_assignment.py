"""Claude's staged split/prefix regressions, exercised against the live module."""
from app import digital_vision as dv


def token(text,x,y):
    return dv.Token(text=text,conf=.99,x0=x,y0=y,x1=x+31,y1=y+70,vertical=True)


def horizontal(y,x0,x1):
    return dv.Seg(x0,y,x1,y,3.0,True)


def test_stacked_divider_becomes_outline():
    box=(1057,2097,1533,3063)
    lines=[horizontal(2540,1060,1530),horizontal(2560,1060,1530)]
    pieces=dv._split_stacked([box],lines,[token('U15',1495,2147),token('U14',1493,2889)],31.)
    assert len(pieces)==2
    assert all(dv._is_outline(line,pieces,8) for line in lines)
    assert all(sum(dv._inside(piece,t.cx,t.cy) for t in [token('U15',1495,2147),token('U14',1493,2889)])<=1 for piece in pieces)


def test_single_reference_and_unproven_split_stay_whole():
    box=(1000,2000,1500,3000)
    assert dv._split_stacked([box],[horizontal(2500,1000,1500)],[token('U15',1400,2100)],31.)==[box]
    assert dv._split_stacked([box],[],[token('U15',1400,2100),token('U14',1400,2800)],31.)==[box]


def test_part_prefix_repairs_only_supported_manufacturer_shape():
    for text in ('Idf7210L','1DT7210L','IDT7210L'):
        assert dv.part_prefix(text)=='IDT7210L'
    for text in ('INDA5','IDT','ID07','DD16','74F244','IOT12'):
        assert dv.part_prefix(text)==text
