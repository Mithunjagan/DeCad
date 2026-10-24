"""Review-only terminals for zero-pin, geometrically corroborated symbols.

New terminals remain isolated. Unread IC numbers use explicit STUB identifiers,
never a guessed package sequence. Full component records survive quarantine.
"""
import math
import re

import cv2
import numpy as np

from .circuit_vision import bodies
from .implicit_terminals import graphic_token,opposing_leads
from .terminal_recovery import perimeter_stubs,local_package_numbers


def lead_gap_bodies(binary,maximum_lead_width=12):
    """Zig-zag bodies bounded by collinear, independently visible leads."""
    result=[]
    for vertical in (True,False):
        view=binary if vertical else binary.T.copy()
        lines=cv2.morphologyEx(view,cv2.MORPH_OPEN,np.ones((24,1),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(lines,8)
        leads=[(x+w/2,y,y+h,w) for x,y,w,h,area in stats[1:] if h>=24 and w<=maximum_lead_width]
        for x,y,end,w in leads:
            for xx,start,yy,ww in leads:
                if abs(x-xx)>6 or not 12<start-end<170:continue
                center=round((x+xx)/2);left=max(0,center-36);right=min(view.shape[1],center+37)
                crop=view[end:start+1,left:right]
                segments=cv2.HoughLinesP(crop,1,np.pi/180,threshold=6,minLineLength=7,maxLineGap=2)
                slopes=[]
                for row in ([] if segments is None else segments):
                    a,b,c,d=map(int,row[0]);dx=c-a;dy=d-b
                    if 4<=abs(dx)<=60 and 3<=abs(dy)<=60 and .15<abs(dx)/abs(dy)<6:slopes.append(dx*dy)
                if len(slopes)<4 or not any(s<0 for s in slopes) or not any(s>0 for s in slopes):continue
                ys,xs=np.where(crop>0)
                if not len(xs) or xs.max()-xs.min()<12:continue
                box=dict(kind='R',x=left+int(xs.min()),y=end,w=int(xs.max()-xs.min()+1),h=start-end+1,vertical=True)
                if not vertical:box=dict(kind='R',x=end,y=left+int(xs.min()),w=start-end+1,h=int(xs.max()-xs.min()+1),vertical=False)
                result.append(box)
    return result


def complete_zero_pin_components(graph,tokens,cropper,ch):
    meta=graph.setdefault('image_metadata',{});anchors=meta.setdefault('pin_anchors',[])
    occupied={p['ref'] for n in graph['nets'] for p in n['nodes']}|{a['ref'] for a in anchors}
    width,height=meta.get('width',0),meta.get('height',0)
    if not width or not height:return graph
    actions=[];rejected=[]
    for component in graph['components']:
        ref=component['ref']
        if ref in occupied:continue
        readings=[t for t in tokens if t.text.upper()==ref]
        if not readings:continue
        location=((component.get('x') if component.get('x') is not None else readings[0].cx/width)*width,
                  (component.get('y') if component.get('y') is not None else readings[0].cy/width)*width)
        token=min(readings,key=lambda t:math.dist((t.cx,t.cy),location))
        passive=bool(re.fullmatch(r'[RCLD]\d+',ref))
        radius=(12 if passive else 24)*ch;x0=max(0,math.floor(token.cx-radius));y0=max(0,math.floor(token.cy-radius))
        x1=min(width,math.ceil(token.cx+radius));y1=min(height,math.ceil(token.cy+radius))
        scale=32/max(ch,1);gray=cv2.resize(cropper((x0,y0,x1,y1)),None,fx=scale,fy=scale)
        binary=(gray<180).astype('uint8')*255;clean=binary.copy()
        for t in tokens:
            if t.x1<x0 or t.x0>x1 or t.y1<y0 or t.y0>y1 or graphic_token(t):continue
            a,b,c,d=[round(v*scale) for v in (t.x0-x0,t.y0-y0,t.x1-x0,t.y1-y0)]
            if re.search('[A-Za-z0-9]',t.text):clean[max(0,b-1):d+2,max(0,a-1):c+2]=0
        center=((token.cx-x0)*scale,(token.cy-y0)*scale)
        candidates=[];seen=[]
        shapes=(lead_gap_bodies(clean)+bodies(binary)+bodies(clean)+
                [dict(s,raw_lead_gap=True) for s in lead_gap_bodies(binary,48)]) if passive else []
        if not passive:
            contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x,y,w,h=cv2.boundingRect(contour)
                poly=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
                if len(poly)==4 and min(w,h)>96 and max(w,h)<1400 and cv2.contourArea(contour)>.8*w*h:
                    shapes.append(dict(x=x,y=y,w=w,h=h,kind='IC',closed=True))
        body_seen=False
        for shape in shapes:
            if passive and shape['kind']!=ref[0] and not (ref.startswith('L') and shape['kind']=='R'):continue
            x,y,w,h=[shape[k] for k in ('x','y','w','h')];box=[x,y,x+w,y+h]
            if x<3 or y<3 or x+w>binary.shape[1]-3 or y+h>binary.shape[0]-3:continue
            distance=math.dist(center,(x+w/2,y+h/2))
            gap=math.hypot(max(x-center[0],0,center[0]-x-w),max(y-center[1],0,center[1]-y-h))
            if (distance>6*32 if passive else gap>4*32):continue
            if any(math.dist((x+w/2,y+h/2),c)<24 for c in seen):continue
            world=[x0+box[0]/scale,y0+box[1]/scale,x0+box[2]/scale,y0+box[3]/scale]
            # An already numbered device owns its own outline.
            body_seen=True
            points=opposing_leads(binary,shape) if passive else None
            stubs=[dict(x=px,y=py) for px,py in points] if points else perimeter_stubs(binary if passive else clean,box,32,corner_inset=0)
            if passive and points is None:
                sides={s['side'] for s in stubs}
                if len(stubs)==2 and sides in ({'top','bottom'},{'left','right'}):
                    points=[(s['x'],s['y']) for s in sorted(stubs,key=lambda s:s['y'] if 'top' in sides else s['x'])]
            if passive and (points is None or len(stubs)!=2):continue
            if not passive and not stubs:continue
            seen.append((x+w/2,y+h/2))
            candidates.append((distance,shape,world,stubs))
        if any(not row[1].get('raw_lead_gap') for row in candidates):
            candidates=[row for row in candidates if not row[1].get('raw_lead_gap')]
        candidates.sort(key=lambda row:row[0])
        meta.setdefault('zero_pin_geometry_audit',[]).append({'ref':ref,'reference_bbox':[token.x0,token.y0,token.x1,token.y1],
            'body_seen':body_seen,'candidates':[{'body':row[2],'stubs':len(row[3]),'distance':row[0]} for row in candidates]})
        if candidates:
            _,shape,world,stubs=candidates[0];used=set();numbered=[]
            ambiguous=len(candidates)>1 and candidates[1][0]-candidates[0][0]<=12
            alternatives=[row[2] for row in candidates if row[0]-candidates[0][0]<=12]
            if ambiguous:world=[min(b[0] for b in alternatives),min(b[1] for b in alternatives),max(b[2] for b in alternatives),max(b[3] for b in alternatives)]
            for i,stub in enumerate(stubs,1):
                px=x0+stub['x']/scale;py=y0+stub['y']/scale
                if ambiguous:pin=f'STUB{i}'
                elif passive:pin=str(i)
                else:
                    horizontal=bool(stub.get('direction',[1,0])[0])
                    digits=sorted((abs((py-t.y1) if horizontal else (px-t.x1))+.1*abs((px-t.cx) if horizontal else (py-t.cy)),t.text) for t in tokens
                                  if t.conf>=.9 and re.fullmatch(r'[1-9]\d{0,2}',t.text)
                                  and t.text not in used and math.dist((px,py),(t.cx,t.cy))<4*ch)
                    pin=digits[0][1] if digits and (len(digits)==1 or digits[1][0]-digits[0][0]>.25*ch) else f'STUB{i}'
                used.add(pin);numbered.append((pin,px,py))
            if not passive:
                allowed=local_package_numbers(component['value']) or set()
                known={pin for pin,_,_ in numbered if not pin.startswith('STUB')}
                unknown=[i for i,(pin,_,_) in enumerate(numbered) if pin.startswith('STUB')]
                if len(unknown)==1 and len(allowed-known)==1:
                    i=unknown[0];numbered[i]=(next(iter(allowed-known)),*numbered[i][1:])
            for pin,px,py in numbered:
                node={'ref':ref,'pin':pin,'source':'provisional_stub','confidence':.25 if ambiguous else .35}
                graph['nets'].append({'name':f'N_PROVISIONAL_{ref}_{pin}','nodes':[node]})
                reason=('Multiple nearby symbol bodies; provisional stub ownership, physical number and net require confirmation' if ambiguous else
                        'Visible symbol and incident wire stub; provisional terminal requires physical number and net confirmation')
                anchor={**node,'x':px,'y':py,'body':world,'physical_net':None,'provisional':True}
                anchors.append(anchor)
                action={**node,'bbox':world,'kind':'provisional_stub','reason':reason,'candidate_bodies':alternatives}
                actions.append(action);meta.setdefault('review_hotspots',[]).append(action)
            continue
        # Absence is checked at the literal caption, never at a misassigned
        # component centroid. A nearby symbol or actual wire blocks quarantine.
        cx,cy=map(round,center);pad=max(1,round(12*scale))
        horizontal=cv2.morphologyEx(clean,cv2.MORPH_OPEN,np.ones((1,32),np.uint8))
        vertical=cv2.morphologyEx(clean,cv2.MORPH_OPEN,np.ones((32,1),np.uint8))
        a=max(0,round((token.x0-x0)*scale)-pad);b=max(0,round((token.y0-y0)*scale)-pad)
        c=round((token.x1-x0)*scale)+pad;d=round((token.y1-y0)*scale)+pad
        incident=bool((horizontal|vertical)[b:d,a:c].any())
        if not body_seen and not candidates and not incident:
            box=[token.x0,token.y0,token.x1,token.y1];reason='Zero-pin caption has no independently owned symbol with incident leads or wire within 12 source-working pixels'
            meta.setdefault('quarantined_components',[]).append({'component':dict(component),'bbox':box,
                'original_token':token.text,'reason':reason,'kind':'unanchored_zero_pin_caption',
                'source':'ocr_alias_quarantine','no_incident_stub_within_px':12})
            meta.setdefault('review_hotspots',[]).append({'ref':ref,'bbox':box,'reason':reason,'confidence':.25,'source':'wire_trace'})
            rejected.append(ref)
    if rejected:graph['components']=[c for c in graph['components'] if c['ref'] not in rejected]
    meta.setdefault('local_recovery_actions',[]).extend(actions)
    if actions:graph.setdefault('warnings',[]).append(f'{len(actions)} provisional isolated terminals require source review before electrical use.')
    return graph
