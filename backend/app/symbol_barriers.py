"""Strict DC barriers at pairs of observed capacitor plates."""
import cv2
import numpy as np
import math
import re


def capacitor_gap(binary,horizontal,across,start,end,ch,*,return_box=False):
    if end-start<3:return False
    pad=max(10,round(ch));a=max(0,round(start)-3);b=round(end)+4;c=max(0,round(across)-pad);d=round(across)+pad+1
    crop=binary[c:d,a:b] if horizontal else binary[a:b,c:d].T
    if not crop.size:return False
    length=max(8,round(.55*ch))
    plates=cv2.morphologyEx(crop,cv2.MORPH_OPEN,np.ones((length,1),np.uint8))
    _,_,stats,_=cv2.connectedComponentsWithStats(plates,8)
    strokes=[(x+w/2,y+h/2,h,w) for x,y,w,h,area in stats[1:]
             if length<=h<=2*ch and w<=max(8,.3*ch) and abs(y+h/2-(across-c))<=.3*ch]
    for i,(x,y,h,w) in enumerate(strokes):
        for xx,yy,hh,ww in strokes[i+1:]:
            if not (3<abs(x-xx)<1.2*ch and abs(y-yy)<.2*ch and abs(h-hh)<.3*ch):continue
            if not return_box:return True
            box=[a+min(x-w/2,xx-ww/2)-1,c+min(y-h/2,yy-hh/2)-1,
                 a+max(x+w/2,xx+ww/2)+1,c+max(y+h/2,yy+hh/2)+1]
            return box if horizontal else [box[1],box[0],box[3],box[2]]
    return None if return_box else False


def port_label_wire(binary,token,segments,ch):
    """A five-sided closed port outline names its entering centerline wire."""
    if token.vertical:return None
    pad=round(2*ch);x0=max(0,round(token.x0)-pad);y0=max(0,round(token.y0)-pad)
    crop=binary[y0:round(token.y1)+pad,x0:round(token.x1)+pad]
    contours,_=cv2.findContours(crop,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        poly=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
        if len(poly)!=5 or not cv2.isContourConvex(poly):continue
        x,y,w,h=cv2.boundingRect(poly);x+=x0;y+=y0
        margin=.2*ch
        if not (x-margin<=token.x0 and token.x1<=x+w+margin and y-margin<=token.y0 and token.y1<=y+h+margin):continue
        cy=y+h/2
        if not 1.1*ch<h<3*ch or w<2*ch:continue
        choices=[]
        for i,s in enumerate(segments):
            if s.bus or not s.horizontal or abs(s.y0-cy)>.25*ch:continue
            for px,py in s.ends():
                if min(abs(px-x),abs(px-x-w))<.5*ch and (s.x0<x-ch or s.x1>x+w+ch):choices.append(i)
        if len(set(choices))==1:return choices[0]
    return None


def capacitor_pin_labels(page,wires,legacy,anchors,labels,tokens,boxes,dots,ch):
    """Separate DC connectivity without changing OCR terminal discovery.

    Legacy wire joining remains the observation coordinate system. A second
    segment graph vetoes capacitor gaps only for well-observed IC terminals on
    the opposite side of an explicit ground label. Physical IDs never change.
    """
    from . import digital_vision as dv
    dc=[s for s in getattr(page,'dc_segments',[]) if not dv._is_outline(s,boxes,max(4,ch*.25)*2)]
    if not dc:return {},[]
    shape=lambda s:(s.x0,s.y0,s.x1,s.y1)
    exact={shape(s) for s in dc};parts={};affected=set()
    for i,wire in enumerate(wires):
        axis=0 if wire.horizontal else 1;cross=1-axis
        lo=wire.x0 if wire.horizontal else wire.y0;hi=wire.x1 if wire.horizontal else wire.y1
        across=wire.y0 if wire.horizontal else wire.x0
        found=[j for j,s in enumerate(dc) if s.horizontal==wire.horizontal and
               abs((s.y0 if s.horizontal else s.x0)-across)<=max(3,.18*ch) and
               min(hi,s.x1 if s.horizontal else s.y1)-max(lo,s.x0 if s.horizontal else s.y0)>0]
        parts[i]=found
        for j in found:dc[j].bus|=wire.bus
        if shape(wire) in exact or len(found)<2:continue
        ordered=sorted((dc[j] for j in found),key=lambda s:s.x0 if s.horizontal else s.y0)
        if any(capacitor_gap(page.binary,wire.horizontal,across,
                            a.x1 if a.horizontal else a.y1,b.x0 if b.horizontal else b.y0,ch)
               for a,b in zip(ordered,ordered[1:])):affected.add(legacy.find(i))
    if not affected:return {},[]
    connected=dv.connect(dc,dots,max(4,ch*.25))
    def root_at(i,x,y):
        options=parts.get(i,[])
        if not options:return None
        j=min(options,key=lambda j:dc[j].dist(x,y))
        if dc[j].dist(x,y)>max(10,ch*.5):return None
        return connected.find(j)
    observations=[]
    for label in labels:
        observations.append((dv.Token(label['text'],label.get('confidence',0),*label['bbox'],label.get('vertical',False)),label.get('wire')))
    for token in tokens:
        name=token.text.upper();box=[token.x0,token.y0,token.x1,token.y1]
        fused=re.fullmatch(r'\d+(?:\.\d+)?[PNUΜM]F([A-Z][A-Z0-9_+/-]{1,})',name)
        if fused:
            fraction=len(fused[1])/len(name);name=fused[1]
            if token.vertical:box[1]=box[3]-(box[3]-box[1])*fraction
            else:box[0]=box[2]-(box[2]-box[0])*fraction
        elif not re.fullmatch(r'[A-Z][A-Z0-9_+/-]{1,20}',name):continue
        if re.fullmatch(r'(?:U|IC|R|C|L|D|Q|J|P|SW|TP|Y|X)\d+[A-H]?',name):continue
        if token.conf<.85 or any(dv._inside(b,(box[0]+box[2])/2,(box[1]+box[3])/2) for b in boxes):continue
        observations.append((dv.Token(name,token.conf,*box,token.vertical),None))
    named={};grounds={}
    for token,old_wire in observations:
        if token.conf<.85:continue
        port=port_label_wire(page.binary,token,wires,ch)
        if port is not None:old_wire=port
        if old_wire is None:
            choices=[]
            for i,s in enumerate(wires):
                if legacy.find(i) not in affected or s.bus or s.horizontal==token.vertical:continue
                along=min(s.x1,token.x1)-max(s.x0,token.x0) if s.horizontal else min(s.y1,token.y1)-max(s.y0,token.y0)
                span=token.x1-token.x0 if s.horizontal else token.y1-token.y0
                distance=min(abs(s.y0-token.y0),abs(s.y0-token.y1)) if s.horizontal else min(abs(s.x0-token.x0),abs(s.x0-token.x1))
                if along>=.5*span and distance<.8*ch:choices.append((distance,i))
            if choices:old_wire=min(choices)[1]
        if old_wire is None or legacy.find(old_wire) not in affected:continue
        wire=wires[old_wire]
        x=min(wire.x1,max(wire.x0,token.cx)) if wire.horizontal else wire.x0
        y=wire.y0 if wire.horizontal else min(wire.y1,max(wire.y0,token.cy))
        root=root_at(old_wire,x,y)
        if root is None:continue
        named.setdefault(root,set()).add(token.text.upper())
        if token.text.upper() in ('GND','AGND','DGND'):grounds.setdefault(legacy.find(old_wire),set()).add(root)
    well_observed={r for r,_ in anchors if r.startswith(('U','IC')) and
                   sum(ref==r and bool(a.get('body')) for (ref,pin),a in anchors.items())>=4}
    result={};audit=[]
    for key,anchor in anchors.items():
        if key[0] not in well_observed:continue
        wire=anchor['wire'];old=legacy.find(wire)
        if old not in grounds:continue
        root=root_at(wire,anchor['x'],anchor['y'])
        if root is None or root in grounds[old]:continue
        names=named.get(root,set())-{'NC','N/C','UNKNOWN'}
        name=next(iter(names)) if len(names)==1 else f'N_DC_{key[0]}_{key[1]}'
        result[key]=name
        audit.append({'ref':key[0],'pin':key[1],'net':name,'kind':'capacitor_dc_barrier',
                      'reason':'Observed capacitor plates separate this terminal from the ground-label conductor',
                      'source':'wire_trace','confidence':.8})
    return result,audit
