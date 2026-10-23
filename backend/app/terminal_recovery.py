"""Bounded OCR of locally uncovered component terminals, independent of sheet recall."""
from collections import Counter,defaultdict
from functools import lru_cache
import math
import re

import cv2
import numpy as np


@lru_cache(maxsize=128)
def local_package_numbers(value):
    from .pin_crop_recovery import reference_numbers
    from .recognition_catalog import connect,pin_tables
    exact=reference_numbers(value)
    if exact:return exact
    # Logic-family variants can corroborate only a shared physical-number
    # range. They never identify a signal function or connect a power rail.
    pattern=r'^74(?:LS|ALS|HC|HCT|AC|ACT|AHC|AHCT|AS|S|F|LV|LVC|VHC|ABT)?(\d+)(?:[A-Z/].*)?$'
    match=re.fullmatch(pattern,(value or '').upper())
    if not match:return None
    with connect() as db:
        if db is None:return None
        names=[r[0] for r in db.execute("SELECT DISTINCT normalized FROM names WHERE normalized LIKE '74%'")]
    alternatives=set()
    for name in names:
        other=re.fullmatch(pattern,name)
        if other and other[1]==match[1]:
            alternatives.update(frozenset(table['pins']) for table in pin_tables(name) if table['pins'])
    return alternatives.pop() if len(alternatives)==1 else None


def perimeter_stubs(binary,box,ch):
    """Find observed straight ink approaching each side, including non-free ends."""
    x0,y0,x1,y1=map(round,box);height,width=binary.shape
    length=max(12,round(1.5*ch));near=4
    horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,max(9,round(.7*ch))),np.uint8))
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((max(9,round(.7*ch)),1),np.uint8))
    sides=[('left',horizontal[max(0,y0):min(height,y1),max(0,x0-length):max(0,x0-near)],1,x0,y0,(-1,0)),
           ('right',horizontal[max(0,y0):min(height,y1),min(width,x1+near):min(width,x1+length)],1,x1,y0,(1,0)),
           ('top',vertical[max(0,y0-length):max(0,y0-near),max(0,x0):min(width,x1)],0,y0,x0,(0,-1)),
           ('bottom',vertical[min(height,y1+near):min(height,y1+length),max(0,x0):min(width,x1)],0,y1,x0,(0,1))]
    result=[]
    for side,strip,axis,edge,start,direction in sides:
        if not strip.size or strip.shape[axis]<length-near-2:continue
        indices=np.flatnonzero((strip>0).mean(axis=axis)>=.82)
        runs=[]
        for index in indices:
            if runs and index-runs[-1][-1]<=2:runs[-1].append(int(index))
            else:runs.append([int(index)])
        for run in runs:
            if len(run)>max(8,.4*ch):continue
            along=start+float(np.mean(run))
            if along<start+.5*ch or along>start+strip.shape[1-axis]-.5*ch:continue
            x,y=(edge,along) if side in ('left','right') else (along,edge)
            result.append({'x':x,'y':y,'direction':list(direction),'side':side})
    return result


def recover_terminals(graph,cropper,*,max_reads=64):
    """Read only uncovered or duplicate-number terminals, using unchanged OCR.

    cropper returns grayscale pixels in the recognizer's working coordinates.
    Both independent readers must corroborate a literal, unused package pin.
    All existing assignments stay intact; source pixels supply every new stub.
    """
    from . import digital_vision as dv
    from .local_recovery import anonymous
    meta=graph.get('image_metadata',{})
    anchors=meta.get('pin_anchors',[])
    width,height=meta.get('width',0),meta.get('height',0)
    if not width or not height:return []
    affine=np.asarray(meta.get('source_affine',[[1,0,0],[0,1,0]]),dtype=float)
    scale=math.hypot(affine[0,0],affine[1,0])
    ch=max(16,min(64,meta.get('measurements',{}).get('source_character_height',30)*scale))
    values={c['ref']:c['value'] for c in graph['components']}
    occupied={(p['ref'],p['pin']) for n in graph['nets'] for p in n['nodes']}
    nets_by_pin={(p['ref'],p['pin']):n['name'] for n in graph['nets'] for p in n['nodes']}
    vocabulary={n['name'] for n in graph['nets']}|{l['text'] for l in meta.get('external_labels',[])}
    groups=defaultdict(list)
    for anchor in anchors:
        if anchor.get('body'):groups[anchor['ref'],tuple(anchor['body'])].append(anchor)
    counts=Counter((o['ref'],o.get('pin')) for o in meta.get('terminal_observations',[]) if o.get('pin'))
    actions=[];reads=0;pending=defaultdict(list)
    def repairable(ref,pin):
        name=nets_by_pin.get((ref,pin),'')
        current=next((a for a in anchors if (a['ref'],a['pin'])==(ref,pin)),{})
        return anonymous(name) or counts[ref,pin]>1 or (name in ('GND','AGND','DGND') and current.get('confidence',1)<.6)
    for (ref,body),observed in groups.items():
        allowed=local_package_numbers(values.get(ref))
        if not allowed and values.get(ref) in ('','UNKNOWN'):
            # An unknown package cannot invent numbers. Already observed IDs
            # may still have conflicting stubs resolved from actual pixels.
            allowed={a['pin'] for a in anchors if a['ref']==ref}
        if not allowed or len({a['pin'] for a in observed}&allowed)<4:continue
        margin=round(10*ch)
        bounds=(max(0,math.floor(body[0])-margin),max(0,math.floor(body[1])-margin),
                min(width,math.ceil(body[2])+margin),min(height,math.ceil(body[3])+margin))
        gray=cropper(bounds)
        binary=dv.binarize(gray)
        hl=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,max(20,round(1.7*ch))),np.uint8))
        vl=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((max(20,round(1.7*ch)),1),np.uint8))
        text=cv2.bitwise_and(binary,cv2.bitwise_not(cv2.bitwise_or(hl,vl)))
        page=dv.Page(gray,binary,hl,vl,text)
        local_box=[body[0]-bounds[0],body[1]-bounds[1],body[2]-bounds[0],body[3]-bounds[1]]
        stubs=perimeter_stubs(binary,local_box,ch)
        def side_of(a):
            dx,dy=a.get('direction',(0,0))
            return ('left' if dx<0 else 'right') if abs(dx)>=abs(dy) else ('top' if dy<0 else 'bottom')
        incomplete_sides={side for side in ('left','right','top','bottom')
            if sum(s['side']==side for s in stubs)>sum(side_of(a)==side for a in observed)
            or any(side_of(a)==side and a['pin'] not in allowed for a in observed)}
        for stub in stubs:
            x,y=stub['x']+bounds[0],stub['y']+bounds[1]
            nearby=[a for a in observed if math.hypot(a['x']-x,a['y']-y)<max(8,.3*ch)]
            if stub['side'] not in incomplete_sides and nearby and all(a['pin'] in allowed and not repairable(ref,a['pin']) for a in nearby):continue
            if reads>=max_reads:break
            reads+=1
            proposals=[]
            for factor in (.72,.86,1.):
                for side in (-1,1):
                    audit={};dx,dy=stub['direction']
                    pin,labels=dv._read_strip(page,stub['x']-dx*5,stub['y']-dy*5,-dx,-dy,ch*factor,side,audit=audit)
                    if pin not in allowed or ((ref,pin) in occupied and not repairable(ref,pin)) or not labels or len(labels)<2:continue
                    a,b=audit.get('primary'),audit.get('secondary')
                    if not a or not b or a[0]!=pin or b[0]!=pin or min(a[1],b[1])<.9:continue
                    number_box=audit.get('pin_bbox')
                    if not number_box:continue
                    axis=1 if dx else 0
                    center_number=(number_box[axis]+number_box[axis+2])/2
                    target_axis=stub['y'] if dx else stub['x']
                    rivals=[abs(center_number-(other['y'] if dx else other['x'])) for other in stubs
                            if other is not stub and other['side']==stub['side']]
                    if rivals and min(rivals)+2<abs(center_number-target_axis):continue
                    options=[dv.strip_label_options([label],vocabulary) for label in labels]
                    common=set(options[0]).intersection(*map(set,options[1:]))
                    if len(common)!=1:continue
                    name=common.pop()
                    if name not in vocabulary or not dv.LABEL_RE.match(name):continue
                    old_name=nets_by_pin.get((ref,pin))
                    if old_name==name:continue
                    if old_name and not anonymous(old_name):
                        la,lb=audit.get('label_primary'),audit.get('label_secondary')
                        if min(a[1],b[1])<.95 or not la or not lb or min(la[1],lb[1])<.95:continue
                    label_box=audit.get('label_bbox')
                    if not label_box:continue
                    center=((label_box[0]+label_box[2])/2,(label_box[1]+label_box[3])/2)
                    # Require observed ink along the proposed pin-to-label path.
                    # Directional closing is restricted to the allowed 1-2px gaps.
                    line=hl if dx else vl
                    kernel=np.ones((1,3) if dx else (3,1),np.uint8)
                    line=cv2.morphologyEx(line,cv2.MORPH_CLOSE,kernel)
                    distance=(center[0]-stub['x'])*dx+(center[1]-stub['y'])*dy
                    if distance<6:continue
                    supported=True
                    for offset in range(5,math.ceil(distance)+1):
                        px=round(stub['x']+dx*offset);py=round(stub['y']+dy*offset)
                        patch=line[max(0,py-3):py+4,max(0,px-3):px+4]
                        if not patch.any():supported=False;break
                    if not supported:continue
                    proposals.append((pin,name,min(a[1],b[1]),factor,side))
                if proposals:break
            identities={(p,n) for p,n,_,_,_ in proposals}
            if len(identities)!=1:continue
            pin,name,certainty,factor,side=max(proposals,key=lambda p:p[2])
            action={'kind':'clipped_terminal_recovery','ref':ref,'pin':pin,'net':name,
                    'bbox':[x-14,y-14,x+14,y+14],'confidence':min(.9,certainty),'source':'erc_healed',
                    'reason':'Observed body-edge stub and two independent cropped OCR readers',
                    'ocr_scale':factor,'ocr_side':side,'body':list(body),'x':x,'y':y,'direction':stub['direction']}
            pending[ref,pin].append(action)
        if reads>=max_reads:break
    for (ref,pin),proposals in pending.items():
        if len({a['net'] for a in proposals})!=1:continue
        action=max(proposals,key=lambda a:a['confidence']);name=action['net']
        old_name=nets_by_pin.get((ref,pin))
        for net in graph['nets']:
            net['nodes']=[p for p in net['nodes'] if (p['ref'],p['pin'])!=(ref,pin)]
        graph['nets']=[n for n in graph['nets'] if n['nodes']]
        target=next((n for n in graph['nets'] if n['name']==name),None)
        node={'ref':ref,'pin':pin}
        if target:target['nodes'].append(node)
        else:graph['nets'].append({'name':name,'nodes':[node]})
        occupied.add((ref,pin));nets_by_pin[ref,pin]=name
        current=next((a for a in anchors if (a['ref'],a['pin'])==(ref,pin)),None)
        anchor={'ref':ref,'pin':pin,'x':action['x'],'y':action['y'],'direction':action['direction'],'body':action['body'],
                'confidence':action['confidence'],'source':'erc_healed','physical_net':None,'graph_node':None}
        if current is None:anchors.append(anchor)
        else:
            anchor['previous_observation']=dict(current);current.clear();current.update(anchor)
        if old_name:action.update(previous_net=old_name,kind='erc_ambiguous_terminal_repair')
        actions.append(action)
    meta.setdefault('terminal_recovery_audit',[]).extend(actions)
    meta.setdefault('review_hotspots',[]).extend(actions)
    meta['terminal_recovery_reads']=reads
    meta['applied']=bool(meta.get('local_recovery_actions') or meta['terminal_recovery_audit'])
    return actions
