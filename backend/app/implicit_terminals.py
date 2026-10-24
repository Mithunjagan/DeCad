"""Pixel-supported terminals for unnumbered symbols; no reference netlists.

All measurements use a normalized working image. RefDes alone never certifies
a terminal: a geometric body and two opposite, continuous leads are required.
"""
import math
import re

import cv2
import numpy as np


def graphic_token(token):
    text=token.text.upper()
    return bool(re.fullmatch(r'[WMNV~]{1,6}',text) or
                token.conf<.8 and re.fullmatch(r'[A-Z]{1,4}',text))


def diode_bodies(binary):
    """Triangle-and-bar diode graphics, with an independently observed bar."""
    result=[]
    for horizontal in (True,False):
        view=binary if horizontal else binary.T.copy()
        contours,_=cv2.findContours(view,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour)
            if min(w,h)<12 or max(w,h)>180:continue
            poly=cv2.approxPolyDP(contour,.035*cv2.arcLength(contour,True),True).reshape(-1,2)
            if len(poly)!=3:continue
            for i in range(3):
                a,b=poly[i],poly[(i+1)%3];tip=poly[(i+2)%3]
                if abs(int(a[0])-int(b[0]))>3 or abs(int(a[1])-int(b[1]))<12:continue
                base=(int(a[0])+int(b[0]))/2;sign=1 if tip[0]>base else -1
                left=max(0,int(tip[0])-12);right=min(view.shape[1],int(tip[0])+13)
                top=max(0,y-4);bottom=min(view.shape[0],y+h+4)
                bars=cv2.morphologyEx(view[top:bottom,left:right],cv2.MORPH_OPEN,np.ones((max(8,round(.7*h)),1),np.uint8))
                _,_,stats,_=cv2.connectedComponentsWithStats(bars,8)
                candidates=[left+xx+ww/2 for xx,yy,ww,hh,area in stats[1:] if hh>=.7*h and ww<=8
                            and sign*(left+xx+ww/2-tip[0])>=-3]
                if not candidates:continue
                bar=min(candidates,key=lambda p:abs(p-tip[0]));lo=round(min(base,bar));hi=round(max(base,bar))
                body=dict(kind='D',x=lo,y=y,w=hi-lo+1,h=h,vertical=False)
                if not horizontal:body=dict(kind='D',x=y,y=lo,w=h,h=hi-lo+1,vertical=True)
                result.append(body)
    return result


def symbol_view(gray, tokens, max_size=1400):
    scale=min(1.,max_size/max(gray.shape))
    view=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale!=1 else gray
    binary=(view<180).astype('uint8')*255
    words=[{'text':t.text,'conf':t.conf,'vertical':t.vertical,'bbox':[round(v*scale) for v in (t.x0,t.y0,t.x1,t.y1)]} for t in tokens]
    clean=binary.copy()
    for word in words:
        if not re.search('[A-Za-z0-9]',word['text']):continue
        x,y,xx,yy=word['bbox'];clean[max(0,y-1):yy+2,max(0,x-1):xx+2]=0
    return scale,binary,clean,words


def opposing_leads(binary, body):
    x,y,w,h=[body[k] for k in ('x','y','w','h')]
    vertical=body.get('vertical',body['kind']=='V' or h>w)
    points=[(x+w//2,y-7),(x+w//2,y+h+7)] if vertical else [(x-7,y+h//2),(x+w+7,y+h//2)]
    for sign,(px,py) in zip((-1,1),points):
        # A real lead continues away from the body for at least eight pixels.
        for offset in (0,4,8):
            xx=px+(0 if vertical else sign*offset);yy=py+(sign*offset if vertical else 0)
            patch=binary[max(0,yy-2):yy+3,max(0,xx-2):xx+3]
            if not np.any(patch):return None
    return points


def passive_observations(gray,tokens,refs,ch):
    """Inspect bounded crops, normalized by lettering size, for passive bodies."""
    from .circuit_vision import bodies
    observations=[];seen=[]
    for token in tokens:
        ref=token.text.upper()
        if ref not in refs or not re.fullmatch(r'[RCLD]\d+[A-H]?',ref):continue
        pad=5*ch;x0=max(0,round(token.cx-pad));y0=max(0,round(token.cy-pad))
        x1=min(gray.shape[1],round(token.cx+pad));y1=min(gray.shape[0],round(token.cy+pad))
        scale=min(2.,32/max(ch,1));crop=cv2.resize(gray[y0:y1,x0:x1],None,fx=scale,fy=scale)
        binary=(crop<180).astype('uint8')*255;clean=binary.copy()
        for text in tokens:
            if text.x1<x0 or text.x0>x1 or text.y1<y0 or text.y0>y1:continue
            if not re.search('[A-Za-z0-9]',text.text):continue
            if graphic_token(text):continue
            a,b,c,d=[round(v*scale) for v in (text.x0-x0,text.y0-y0,text.x1-x0,text.y1-y0)]
            clean[max(0,b-1):d+2,max(0,a-1):c+2]=0
        candidates=[]
        for body in (diode_bodies(clean) if ref[0]=='D' else bodies(clean)):
            if body['kind']!=ref[0] and not (ref[0]=='L' and body['kind']=='R'):continue
            points=opposing_leads(binary,body)
            if points is None:continue
            center=(x0+(body['x']+body['w']/2)/scale,y0+(body['y']+body['h']/2)/scale)
            distance=math.dist(center,(token.cx,token.cy))
            if distance>4*ch:continue
            box=[x0+body['x']/scale,y0+body['y']/scale,x0+(body['x']+body['w'])/scale,y0+(body['y']+body['h'])/scale]
            candidates.append((distance,box,[(x0+x/scale,y0+y/scale) for x,y in points]))
        candidates.sort()
        if not candidates or len(candidates)>1 and candidates[1][0]-candidates[0][0]<.4*ch:continue
        _,box,points=candidates[0]
        if any(math.dist(box[:2],old[:2])<ch/2 for old in seen):continue
        seen.append(box);observations.append({'ref':ref,'body':box,'points':points})
    return observations


def attach_passives(graph,gray,tokens,ch):
    metadata=graph.setdefault('image_metadata',{});anchors=metadata.setdefault('pin_anchors',[])
    observed={(p['ref'],str(p['pin'])) for n in graph['nets'] for p in n['nodes']}|{(a['ref'],str(a['pin'])) for a in anchors}
    refs={c['ref'] for c in graph['components'] if c.get('library') in ('Device:R','Device:C','Device:L','Device:D')
          and len({p for r,p in observed if r==c['ref']})<2}
    actions=[]
    for item in passive_observations(gray,tokens,refs,ch):
        ref=item['ref'];points=item['points'];box=item['body']
        existing=[a for a in anchors if a['ref']==ref]
        if any(a['pin'] not in ('1','2') for a in existing):continue
        if existing:
            a=existing[0];order=sorted(range(2),key=lambda i:math.dist((a['x'],a['y']),points[i]))
            if math.dist((a['x'],a['y']),points[order[0]])>ch:continue
            if order[0]!=int(a['pin'])-1:points=list(reversed(points))
        for index,(x,y) in enumerate(points,1):
            pin=str(index)
            if (ref,pin) in observed:continue
            # New terminals are unassigned until a unique masked conductor is
            # corroborated by an already observed terminal from another device.
            choices=[]
            from .local_recovery import _distance
            for edge in metadata.get('wire_edges',[]):
                if min((_distance((x,y),a,b)[0] for a,b in zip(edge['points'],edge['points'][1:])),default=999)>5:continue
                root=edge.get('physical_net')
                if root is None:continue
                owners={n['name'] for n in graph['nets'] for p in n['nodes'] for a in anchors
                        if a['ref']==p['ref'] and a['pin']==p['pin'] and a.get('physical_net')==root and a['ref']!=ref}
                if len(owners)==1:choices.append((root,next(iter(owners))))
            # The legacy trace may still contain an unmasked second symbol.
            # Record the physical terminal without propagating that uncertain
            # root into the active graph. Full analog fusion masks every body.
            name=f'N_IMPLICIT_{ref}_{pin}'
            target=next((n for n in graph['nets'] if n['name']==name),None)
            node={'ref':ref,'pin':pin,'source':'implicit_passive_terminal','confidence':.75}
            if target is None:graph['nets'].append({'name':name,'nodes':[node]})
            else:target['nodes'].append(node)
            dx=x-points[2-index][0];dy=y-points[2-index][1];length=math.hypot(dx,dy)
            anchors.append({**node,'x':x,'y':y,'body':box,'direction':[dx/length,dy/length],
                            'physical_net':choices[0][0] if len(set(choices))==1 else None})
            actions.append({'kind':'implicit_passive_terminal','ref':ref,'pin':pin,'bbox':box,
                            'reason':'Two opposing raster leads at a verified passive body; deterministic terminal convention',
                            'source':'implicit_passive_terminal','confidence':.75})
        metadata.setdefault('passive_bodies',[]).append(item)
    metadata.setdefault('local_recovery_actions',[]).extend(actions)
    metadata.setdefault('review_hotspots',[]).extend(actions)
    return graph


def quarantine_unverified(graph,tokens,read_reference=None):
    """Keep corroborated zero-pin OCR aliases outside the electrical graph."""
    metadata=graph.setdefault('image_metadata',{});anchors=metadata.get('pin_anchors',[])
    pins={(p['ref'],str(p['pin'])) for n in graph['nets'] for p in n['nodes']}|{(a['ref'],str(a['pin'])) for a in anchors}
    refs={c['ref']:c for c in graph['components']};verified=set(metadata.get('verified_component_refs',[]))
    rejected=[]
    interfaces={'USB','UART','SPI','I2C','JTAG','GPIO'}
    for component in graph['components']:
        ref=component['ref']
        if any(r==ref for r,p in pins) or ref in verified:continue
        observations=[t for t in tokens if t.text.upper()==ref]
        if not observations:continue
        token=max(observations,key=lambda t:t.conf)
        reading=read_reference(token) if read_reference else None
        alias=reading[0].upper() if reading and reading[1]>=.95 else None
        overlap=alias in refs and alias!=ref and any(r==alias for r,p in pins) and refs[alias]['value'].upper()==component['value'].upper()
        weak=token.conf<.65 and component['value'] in ('','UNKNOWN')
        if alias not in interfaces and not overlap and not weak:continue
        reason='Zero-pin OCR alias has no independently verified symbol body'
        box=[token.x0,token.y0,token.x1,token.y1]
        rejected.append(ref)
        metadata.setdefault('quarantined_components',[]).append({'component':dict(component),
            'bbox':box,'original_token':token.text,'ocr_confidence':token.conf,'reread':reading,
            'reason':reason,'source':'ocr_alias_quarantine'})
        metadata.setdefault('review_hotspots',[]).append({'ref':ref,'bbox':box,'reason':reason,
            'source':'wire_trace','confidence':.35})
    if rejected:
        graph['components']=[c for c in graph['components'] if c['ref'] not in rejected]
        graph.setdefault('warnings',[]).append('Unverified zero-pin component aliases quarantined for source review: '+', '.join(rejected))
    return graph


def reread_reference(gray,token):
    """Two enlarged views must agree before quarantining an OCR alias."""
    from .digital_vision import ocr_engine
    crop=gray[max(0,round(token.y0)-2):round(token.y1)+3,max(0,round(token.x0)-2):round(token.x1)+3]
    if not crop.size:return None
    if token.vertical:crop=cv2.rotate(crop,cv2.ROTATE_90_CLOCKWISE)
    readings=[]
    for factor in (2.,3.):
        view=cv2.resize(crop,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC)
        view=cv2.copyMakeBorder(view,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
        rows,_=ocr_engine()(cv2.cvtColor(view,cv2.COLOR_GRAY2BGR),use_det=False,use_cls=False)
        if not rows:return None
        readings.append((str(rows[0][0]).strip(),float(rows[0][1])))
    return (readings[0][0],min(r[1] for r in readings)) if readings[0][0].upper()==readings[1][0].upper() else None


def complete_amplifier_stubs(binary,ref,body,polygon,anchors,ch,family=None):
    """Complete one unread number only from five visible amplifier leads.

    Four observed numbers must identify a unique standard inventory. A shared
    subset such as 1/2/3/4 is ambiguous between five- and eight-pin families.
    Geometry supplies the remaining physical terminal, never a guessed net.
    """
    from .terminal_recovery import perimeter_stubs
    if not re.fullmatch(r'U\d+',ref) or len(polygon)!=3:return []
    known=[a for a in anchors if a['ref']==ref]
    ids={str(a['pin']) for a in known}
    if len(known)!=4 or len(ids)!=4 or any(a.get('confidence',0)<.65 for a in known):return []
    families=[{'1','2','3','4','5'},{'2','3','4','6','7'},{'1','2','3','4','8'}]
    choices=[f for f in families if ids<f and (family is None or f==set(map(str,family)))]
    if len(choices)!=1:return []
    stubs=perimeter_stubs(binary,body,ch,corner_inset=0)
    if len(stubs)!=5:return []
    directions={tuple(s['direction']):sum(s['direction']==t['direction'] for t in stubs) for s in stubs}
    flat=[d for d,count in directions.items() if count==2]
    if len(flat)!=1 or len(directions)!=4:return []
    ux,uy=(-flat[0][0],-flat[0][1])
    projections=sorted(x*ux+y*uy for x,y in polygon);span=projections[-1]-projections[0]
    if span<=0 or projections[1]-projections[0]>.15*span:return []
    occupied=set()
    for anchor in known:
        distances=sorted((math.dist((anchor['x'],anchor['y']),(s['x'],s['y'])),i) for i,s in enumerate(stubs))
        distance,index=distances[0]
        if distance>max(10,1.1*ch) or index in occupied:return []
        occupied.add(index)
    stub=next(s for i,s in enumerate(stubs) if i not in occupied)
    dx,dy=stub['direction'];pin=next(iter(choices[0]-ids))
    return [{'ref':ref,'pin':pin,'x':round(stub['x']+8*dx),'y':round(stub['y']+8*dy),
             'body':list(body),'direction':[dx,dy],'source':'wire_trace','confidence':.7,
             'kind':'standard_amplifier_completion',
             'reason':'Five visible amplifier leads and four observed numbers uniquely identify the remaining terminal'}]


def analog_graph(gray,tokens,original):
    """Fuse passive/circle/triangle geometry only on small analog-only sheets.

    Existing digital or mixed-sheet observations cannot be replaced by this
    fallback. A triangle with a printed U reference is mandatory.
    """
    from .circuit_vision import bodies
    if any(not re.fullmatch(r'[RCLDVU]\d+',c['ref']) for c in original['components']):return None
    if sum(len(n['nodes']) for n in original['nets'])>5:return None
    scale,binary,clean,words=symbol_view(gray,tokens)
    refs=[w for w in words if re.fullmatch(r'[RCVU]\d+',w['text'],re.I) and w['conf']>=.6]
    if not any(w['text'].upper().startswith('U') for w in refs):return None
    symbols=bodies(clean)
    contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour);area=cv2.contourArea(contour)
        if not (35<min(w,h) and max(w,h)<240 and .3<area/(w*h)<.65):continue
        poly=cv2.approxPolyDP(contour,.035*cv2.arcLength(contour,True),True)
        if len(poly)==3 and not any(s['kind']=='U' and abs(s['x']-x)+abs(s['y']-y)<12 for s in symbols):
            symbols.append(dict(kind='U',x=x,y=y,w=w,h=h,polygon=poly.reshape(-1,2).tolist()))
    if not any(s['kind']=='U' for s in symbols):return None
    used=set();assigned=[];components=[];anchors=[]
    for word in refs:
        ref=word['text'].upper();x0,y0,x1,y1=word['bbox'];cx=(x0+x1)/2;cy=(y0+y1)/2
        choices=sorted((math.hypot(s['x']+s['w']/2-cx,s['y']+s['h']/2-cy),i,s)
                       for i,s in enumerate(symbols) if i not in used and s['kind']==ref[0])
        if not choices or choices[0][0]>160:continue
        distance,index,body=choices[0]
        points=opposing_leads(binary,body) if ref[0]!='U' else None
        if ref[0]!='U' and points is None:continue
        values=[v for v in words if v is not word and v['conf']>=.6 and
                (re.fullmatch(r'(?:ac=)?\d+(?:\.\d+)?[fpnumkKMG]?',v['text']) if ref[0]!='U' else
                 re.fullmatch(r'[A-Za-z]+\d+[A-Za-z0-9-]*',v['text'])) and
                not re.fullmatch(r'[RCVU]\d+',v['text'],re.I)]
        values=sorted(values,key=lambda v:math.dist(((v['bbox'][0]+v['bbox'][2])/2,(v['bbox'][1]+v['bbox'][3])/2),(cx,cy)))
        if not values or math.dist(((values[0]['bbox'][0]+values[0]['bbox'][2])/2,(values[0]['bbox'][1]+values[0]['bbox'][3])/2),(cx,cy))>110:continue
        value=values[0]['text'];used.add(index);assigned.append((ref,body))
        components.append({'ref':ref,'value':value,'library':{'R':'Device:R','C':'Device:C','V':'Simulation_SPICE:VDC'}.get(ref[0]),
                           'x':(body['x']+body['w']/2)/binary.shape[1],'y':(body['y']+body['h']/2)/binary.shape[1]})
        if points:
            for pin,(px,py) in enumerate(points,1):
                anchors.append(dict(ref=ref,pin=str(pin),x=px,y=py,source='implicit_passive_terminal' if ref[0] in 'RCLD' else 'wire_trace',
                                    confidence=.8,body=[body['x'],body['y'],body['x']+body['w'],body['y']+body['h']]))
        else:
            x,y,w,h=[body[k] for k in ('x','y','w','h')]
            for number in words:
                if not re.fullmatch(r'\d{1,2}',number['text']) or number['conf']<.65:continue
                nx,ny,nxx,nyy=number['bbox'];ncx=(nx+nxx)/2;ncy=(ny+nyy)/2
                if not x-35<ncx<x+w+35 or not y-35<ncy<y+h+35:continue
                horizontal=sorted([(abs(ncx-x),'left'),(abs(ncx-x-w),'right')])
                vertical=sorted([(abs(ncy-y),'top'),(abs(ncy-y-h),'bottom')])
                sides=vertical if vertical[0][0]+6<horizontal[0][0] else horizontal
                side=sides[0][1]
                # Printed numbers sit just above horizontal leads or beside vertical ones.
                candidates=[]
                for delta in range(-4,23):
                    px=x-8 if side=='left' else x+w+8 if side=='right' else round(ncx+delta)
                    py=y-8 if side=='top' else y+h+8 if side=='bottom' else round(ncy+delta)
                    if np.any(clean[max(0,py-1):py+2,max(0,px-1):px+2]):candidates.append((abs(delta-8),px,py))
                if candidates:
                    _,px,py=min(candidates);anchors.append(dict(ref=ref,pin=number['text'],x=px,y=py,confidence=.85,source='wire_trace',body=[x,y,x+w,y+h]))
    if not any(c['ref'].startswith('U') for c in components) or not {c['ref'] for c in original['components']}<={c['ref'] for c in components}:return None
    for ref,body in assigned:
        if body['kind']=='U':
            box=[body['x'],body['y'],body['x']+body['w'],body['y']+body['h']]
            heights=[w['bbox'][3]-w['bbox'][1] for w in words if w['conf']>=.9]
            lettering=float(np.median(heights)) if heights else 18
            anchors.extend(complete_amplifier_stubs(clean,ref,box,body.get('polygon',[]),anchors,lettering))
    wire=clean|cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((30,1),np.uint8))|cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,30),np.uint8))
    for ref,b in assigned:
        x,y,w,h=[b[k] for k in ('x','y','w','h')];wire[max(0,y-5):y+h+6,max(0,x-5):x+w+6]=0
    count,labels,stats,_=cv2.connectedComponentsWithStats(wire,8)
    nets={};resolved=[]
    for anchor in anchors:
        x,y=anchor['x'],anchor['y'];patch=labels[max(0,y-3):y+4,max(0,x-3):x+4]
        ids=[int(i) for i in np.unique(patch) if i and stats[i,cv2.CC_STAT_AREA]>12]
        if len(ids)!=1:continue
        root=ids[0];nets.setdefault(root,[]).append({'ref':anchor['ref'],'pin':anchor['pin'],'source':anchor['source'],'confidence':anchor['confidence']})
        anchor.update(x=x/scale,y=y/scale,body=[v/scale for v in anchor['body']],physical_net=root);resolved.append(anchor)
    names={}
    for word in words:
        if word['text'].upper() not in ('GND','VDD','VSS','VIN','VOUT','LOWPASS'):continue
        x,y,xx,yy=word['bbox'];cx=(x+xx)/2;cy=(y+yy)/2
        choices=[]
        region=labels[max(0,round(cy)-65):round(cy)+66,max(0,round(cx)-65):round(cx)+66]
        for root in np.unique(region):
            if not root or stats[root,cv2.CC_STAT_AREA]<20:continue
            ys,xs=np.where(labels[max(0,round(cy)-65):round(cy)+66,max(0,round(cx)-65):round(cx)+66]==root)
            if len(xs):choices.append((float(np.min((xs+max(0,round(cx)-65)-cx)**2+(ys+max(0,round(cy)-65)-cy)**2)),root))
        if choices:
            dist,root=min(choices)
            if dist<40**2:names[root]=word['text'].upper()
    merged={}
    for root,nodes in nets.items():merged.setdefault(names.get(root,f'N_ANALOG_{root}'),[]).extend(nodes)
    old={(p['ref'],p['pin']) for n in original['nets'] for p in n['nodes']}
    if not old<={(p['ref'],p['pin']) for n in merged.values() for p in n}:return None
    return {'components':components,'nets':[{'name':name,'nodes':nodes} for name,nodes in merged.items()],
            'warnings':['Analog symbols recovered from raster geometry. Unprinted passive terminals use left/top=1, right/bottom=2; review polarity and numbering.'],
            'image_metadata':{**original.get('image_metadata',{}),'pin_anchors':resolved,'analog_geometry_fusion':True,
                              'symmetric_terminal_refs':[c['ref'] for c in components if c['ref'][0] in 'RCL'],
                              'local_recovery_actions':original.get('image_metadata',{}).get('local_recovery_actions',[])+
                                  [dict(a,bbox=a['body']) for a in resolved if a.get('kind')=='standard_amplifier_completion']}}
