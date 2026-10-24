"""Recover missing physical anchors from two already observed text tokens.

An actual outside lead, a literal package pin and its aligned external net text
must agree. Existing pin assignments are never replaced.
"""
from collections import defaultdict
import math
import re

import cv2
import numpy as np

from .terminal_recovery import perimeter_stubs,local_package_numbers


def recover_observed_pairs(graph,tokens,cropper):
    meta=graph.get('image_metadata',{});anchors=meta.get('pin_anchors',[])
    width,height=meta.get('width',0),meta.get('height',0)
    if not width or not height:return []
    affine=meta.get('source_affine',[[1,0,0],[0,1,0]])
    ch=meta.get('character_height') or max(16,min(64,meta.get('measurements',{}).get('source_character_height',30)*math.hypot(affine[0][0],affine[1][0])))
    bodies=defaultdict(list)
    for a in anchors:
        if a.get('body') and a['ref'].startswith(('U','IC')):bodies[a['ref'],tuple(a['body'])].append(a)
    values={c['ref']:c['value'] for c in graph['components']}
    occupied={(p['ref'],str(p['pin'])) for n in graph['nets'] for p in n['nodes']}
    numbers=[t for t in tokens if t.conf>=.95 and re.fullmatch(r'[1-9]\d{0,2}',t.text)]
    labels=[t for t in tokens if t.conf>=.9 and re.fullmatch(r'[-~/+]?[A-Z][A-Z_]{0,9}\d{1,3}[A-Z]?',t.text.upper())
            and not re.fullmatch(r'(?:U|IC|R|C|D|L|Q|J|P|TP|Y|X)\d+[A-H]?',t.text.upper())]
    proposals=defaultdict(list)
    for (ref,body),observed in bodies.items():
        allowed=local_package_numbers(values.get(ref))
        if not allowed or len({a['pin'] for a in observed}&allowed)<4:continue
        margin=round(9*ch);x0=max(0,math.floor(body[0])-margin);y0=max(0,math.floor(body[1])-margin)
        bounds=(x0,y0,min(width,math.ceil(body[2])+margin),min(height,math.ceil(body[3])+margin))
        gray=cropper(bounds)
        binary=(gray<180).astype('uint8')*255
        box=[body[0]-x0,body[1]-y0,body[2]-x0,body[3]-y0]
        # Raster outlines can sit a few pixels inside a merged segment box.
        # Include a narrow outside band so a corner lead is not clipped away.
        edge_pad=max(2,.15*ch)
        stubs=perimeter_stubs(binary,[box[0]-edge_pad,box[1]-edge_pad,box[2]+edge_pad,box[3]+edge_pad],ch,corner_inset=0)
        lines={True:cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,max(9,round(.7*ch))),np.uint8)),
               False:cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((max(9,round(.7*ch)),1),np.uint8))}
        for stub in stubs:
            dx,dy=stub['direction'];horizontal=bool(dx);axis=0 if horizontal else 1;cross=1-axis
            x,y=stub['x']+x0,stub['y']+y0
            def aligned(t):
                b=[t.x0,t.y0,t.x1,t.y1];forward=(t.cx-x)*dx+(t.cy-y)*dy
                gap=min(abs((y if horizontal else x)-b[cross]),abs((y if horizontal else x)-b[cross+2]))
                return t.vertical!=horizontal and gap<.45*ch and 0<forward<8*ch
            digits=[t for t in numbers if t.text in allowed and (ref,t.text) not in occupied and aligned(t)
                    and (t.cx-x)*dx+(t.cy-y)*dy<2.2*ch]
            for number in digits:
                matches=[]
                for label in labels:
                    if not aligned(label):continue
                    distance=(label.cx-number.cx)*dx+(label.cy-number.cy)*dy
                    if not .3*ch<distance<7*ch:continue
                    nb=[number.x0,number.y0,number.x1,number.y1];lb=[label.x0,label.y0,label.x1,label.y1]
                    overlap=min(nb[cross+2],lb[cross+2])-max(nb[cross],lb[cross])
                    if overlap<.6*min(nb[cross+2]-nb[cross],lb[cross+2]-lb[cross]):continue
                    length=(label.cx-x)*dx+(label.cy-y)*dy
                    line=lines[horizontal];supported=True
                    for offset in range(5,math.ceil(length)+1,3):
                        px=round(stub['x']+dx*offset);py=round(stub['y']+dy*offset)
                        if not line[max(0,py-3):py+4,max(0,px-3):px+4].any():supported=False;break
                    if supported:matches.append((distance,label))
                if not matches:continue
                matches.sort(key=lambda p:p[0]);label=matches[0][1]
                if len(matches)>1 and matches[1][0]-matches[0][0]<ch:continue
                proposals[ref,number.text].append({'ref':ref,'pin':number.text,'net':label.text.upper(),'x':x,'y':y,
                    'alignment_error':abs((number.cy if horizontal else number.cx)-(y if horizontal else x))+
                                      abs((label.cy if horizontal else label.cx)-(y if horizontal else x)),
                    'direction':stub['direction'],'body':list(body),'bbox':[x-12,y-12,x+12,y+12],
                    'source':'wire_trace','confidence':min(.9,number.conf,label.conf),
                    'kind':'observed_terminal_pair','reason':'Printed package pin and aligned net text on a continuous outside lead'})
    actions=[]
    for key,options in proposals.items():
        if len({o['net'] for o in options})!=1:continue
        options.sort(key=lambda o:o['alignment_error'])
        action=options[0]
        if any(o['alignment_error']-action['alignment_error']<2 and math.hypot(o['x']-action['x'],o['y']-action['y'])>8
               for o in options[1:]):continue
        target=next((n for n in graph['nets'] if n['name']==action['net']),None)
        node={'ref':key[0],'pin':key[1]}
        if target:target['nodes'].append(node)
        else:graph['nets'].append({'name':action['net'],'nodes':[node]})
        anchors.append({**action,'physical_net':None,'graph_node':None});actions.append(action)
    meta.setdefault('local_recovery_actions',[]).extend(actions)
    meta.setdefault('review_hotspots',[]).extend(actions)
    return actions
