import cv2
import numpy as np

from app.terminal_recovery import perimeter_stubs


def test_visible_body_edge_stubs_are_found_even_when_their_far_ends_are_joined():
    image=np.zeros((180,200),np.uint8)
    cv2.rectangle(image,(70,50),(140,130),255,2)
    cv2.line(image,(20,75),(70,75),255,2)
    cv2.line(image,(100,10),(100,50),255,2)
    cv2.line(image,(20,20),(20,140),255,2)
    stubs=perimeter_stubs(image,[70,50,140,130],20)
    assert any(s['side']=='left' and abs(s['y']-75)<=1 for s in stubs)
    assert any(s['side']=='top' and abs(s['x']-100)<=1 for s in stubs)


def test_glyph_specks_and_disconnected_short_marks_do_not_make_terminals():
    image=np.zeros((180,200),np.uint8)
    cv2.rectangle(image,(70,50),(140,130),255,2)
    cv2.line(image,(55,80),(60,80),255,2)
    assert not perimeter_stubs(image,[70,50,140,130],20)
