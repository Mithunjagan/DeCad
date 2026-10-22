"""Bounded source normalization and exhaustive overlapping tile coordinates."""
import math
import re

import cv2
import numpy as np


def tiles(width,height,size=1024,overlap=.2):
    if size<32 or not 0<=overlap<.75:raise ValueError('Invalid tile geometry')
    def starts(length):
        if length<=size:return [0]
        step=max(1,round(size*(1-overlap)))
        return sorted(set([*range(0,length-size+1,step),length-size]))
    return [(x,y,min(width,x+size),min(height,y+size)) for y in starts(height) for x in starts(width)]


def stroke_width(binary):
    """Distance-transform ridges of long straight strokes, in bounded bands."""
    widths=[]
    for y in np.linspace(0,max(0,binary.shape[0]-256),min(8,max(1,binary.shape[0]//256)),dtype=int):
        patch=binary[y:y+256]
        line=cv2.morphologyEx(patch,cv2.MORPH_OPEN,np.ones((1,31),np.uint8))
        if not line.any():continue
        dist=cv2.distanceTransform(line,cv2.DIST_L2,5)
        ridges=(dist>0)&(dist>=cv2.dilate(dist,np.ones((3,1),np.uint8)))
        samples=dist[ridges]
        if samples.size:widths.append(float(np.median(2*samples-1)))
    return max(1.,float(np.median(widths))) if widths else 0.


def normalize(gray,binary,char_height):
    """Keep the verified 16-64px text operating range; normalize extreme scans.

    Existing small-text enhancement runs afterwards. A second resize of those
    inputs would erase thin bus lines. The returned affine covers every change.
    """
    affine=np.array([[1.,0.,0.],[0.,1.,0.]])
    width=stroke_width(binary)
    notes=[]
    corners=np.array([gray[0,0],gray[-1,0],gray[0,-1],gray[-1,-1]])
    if np.median(corners)<64 and np.mean(gray<128)>.65:
        gray=255-gray
        notes.append('Dark-background source inverted before OCR and wire tracing.')
    # Uneven paper illumination is distinct from soft ink ramps. Enhance the
    # former; preserve the established grayscale treatment of blurred scans.
    paper=[]
    for y in np.linspace(0,max(0,gray.shape[0]-128),5,dtype=int):
        for x in np.linspace(0,max(0,gray.shape[1]-128),5,dtype=int):
            paper.append(float(np.percentile(gray[y:y+128,x:x+128],90)))
    if max(paper)-min(paper)>35:
        gray=cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(gray)
        gray=cv2.bilateralFilter(gray,5,20,20)
        notes.append('Uneven paper contrast normalized with CLAHE and edge-preserving bilateral filtering.')
    factor=1.
    if char_height>64:
        factor=max(24/char_height,2.5/max(width,1.))
        factor=min(1.,factor)
    elif width>8 and char_height>40:
        factor=max(24/char_height,2.5/width)
    if factor<.9:
        gray=cv2.resize(gray,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
        affine[:2,:2]*=factor
        notes.append(f'Source scale normalized by {factor:.4f}; measured text {char_height:.1f}px, wire strokes {width:.1f}px.')
    return gray,affine,notes,{'source_character_height':char_height,'source_wire_width':width}


def orient(gray,reader):
    """Choose quarter turns using confidently read references, not page aspect.

    Missing/ambiguous orientation evidence preserves the source orientation.
    No circuit/netlist is requested from an image model.
    """
    factor=min(1.,1800/max(gray.shape))
    probe=cv2.resize(gray,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA) if factor<1 else gray
    scores=[]
    for turn in range(4):
        image=np.ascontiguousarray(np.rot90(probe,turn))
        reads,_=reader(cv2.cvtColor(image,cv2.COLOR_GRAY2BGR),use_cls=False)
        refs=[float(row[2]) for row in reads or [] if len(row)>=3 and float(row[2])>=.92
              and re.fullmatch(r'(?:U|IC|R|C|L|D|Q|J|P|SW|RN|TP)\d{1,4}',str(row[1]).strip(),re.I)]
        scores.append((len(refs),sum(refs)))
    winner=max(range(4),key=lambda turn:scores[turn])
    if winner and scores[winner][0]>=3 and scores[winner][0]>=scores[0][0]+3 and scores[winner][1]>1.4*max(1.,scores[0][1]):
        h,w=gray.shape
        matrices=[[[1,0,0],[0,1,0]],[[0,1,0],[-1,0,w-1]],
                  [[-1,0,w-1],[0,-1,h-1]],[[0,-1,h-1],[1,0,0]]]
        return np.ascontiguousarray(np.rot90(gray,winner)),np.array(matrices[winner],dtype=float),winner*90
    return gray,np.array([[1.,0.,0.],[0.,1.,0.]]),0
