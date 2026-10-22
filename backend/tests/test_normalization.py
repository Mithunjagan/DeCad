import cv2
import numpy as np

from app.normalization import normalize,orient,stroke_width,tiles


def test_overlapping_tiles_cover_extreme_edges_without_tiny_last_tiles():
    boxes=tiles(4001,3001)
    assert len(boxes)>1 and all(x1-x0==1024 and y1-y0==1024 for x0,y0,x1,y1 in boxes)
    coverage=np.zeros((3001,4001),np.uint8)
    for x0,y0,x1,y1 in boxes:coverage[y0:y1,x0:x1]=1
    assert coverage.all()
    assert tiles(300,200)==[(0,0,300,200)]


def test_stroke_measurement_and_extreme_scale_preserve_text_minimum():
    binary=np.zeros((400,800),np.uint8)
    for y in (50,100,150):cv2.line(binary,(10,y),(780,y),255,9)
    assert 7<=stroke_width(binary)<=13
    gray=255-binary
    normalized,matrix,notes,measurements=normalize(gray,binary,96)
    assert normalized.shape[0]<400 and matrix[0,0]*96>=24
    assert notes and measurements['source_wire_width']>=7


def test_accepted_text_scale_is_not_resampled():
    gray=np.full((400,800),255,np.uint8)
    normalized,matrix,notes,_=normalize(gray,255-gray,40)
    assert normalized is gray and not notes
    assert np.array_equal(matrix,[[1,0,0],[0,1,0]])


def test_quarter_turn_requires_multiple_additional_confident_references():
    gray=np.arange(80*120,dtype=np.uint8).reshape(80,120)
    calls=[]
    def reader(image,**kwargs):
        index=len(calls);calls.append(image)
        return ([[None,'U1',.99],[None,'U2',.99],[None,'R3',.99]] if index==2 else []),None
    rotated,matrix,degrees=orient(gray,reader)
    assert degrees==180 and np.array_equal(rotated,np.rot90(gray,2))
    assert np.array_equal(matrix, [[-1,0,119],[0,-1,79]])
    undecided=lambda *args,**kwargs:([[None,'U1',.99]],None)
    assert orient(gray,undecided)[2]==0
