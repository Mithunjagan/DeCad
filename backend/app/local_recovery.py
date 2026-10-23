"""Add locally supported observations without replacing confident sheet readings.

Reference answers and benchmark identities are deliberately absent. Each proposal
records its own evidence; unrelated unresolved symbols do not disable recovery.
"""
from collections import defaultdict
from copy import deepcopy
import math
import re


def anonymous(name):
    return bool(re.fullmatch(r'(?:N\d+(?:_[A-Za-z0-9]+)*|NET[_$]?\d+)',name,re.I))


def _side(anchor):
    dx,dy=anchor.get('direction',(0,0))
    return ('left' if dx<0 else 'right') if abs(dx)>=abs(dy) else ('top' if dy<0 else 'bottom')


def repair_impossible_numbers(graph,metadata,*,numbers=None):
    """Remove a fused digit only when package bounds and observed order agree.

    Three legitimate side readings must already be strictly ordered. No uniform
    pin pitch is assumed: functional symbols can leave unused drawing slots.
    Existing valid physical numbers are never replaced.
    """
    if numbers is None:
        from .pin_crop_recovery import reference_numbers
        numbers=reference_numbers
    values={c['ref']:c['value'] for c in graph['components']}
    anchors=metadata.get('pin_anchors',[])
    groups=defaultdict(list)
    for a in anchors:
        if a.get('body') and len(a.get('direction',[]))==2:
            groups[a['ref'],tuple(a['body']),_side(a)].append(a)
    occupied={(p['ref'],str(p['pin'])) for n in graph['nets'] for p in n['nodes']}
    actions=[]
    for (ref,body,side),group in groups.items():
        allowed=numbers(values.get(ref))
        if not allowed:continue
        group=sorted(group,key=lambda a:a['y'] if side in ('left','right') else a['x'])
        good=[(i,int(a['pin'])) for i,a in enumerate(group) if a['pin'] in allowed and a['pin'].isdigit()]
        if len(good)<3:continue
        signs={1 if b[1]>a[1] else -1 if b[1]<a[1] else 0 for a,b in zip(good,good[1:])}
        if len(signs)!=1 or 0 in signs:continue
        sign=next(iter(signs))
        for i,anchor in enumerate(group):
            old=anchor['pin']
            if old in allowed or not old.isdigit() or len(old)<2:continue
            # OCR can fuse a wire stroke into an adjacent printed digit. Only
            # literal one-character deletions are candidates, never arbitrary IDs.
            candidates={old[:j]+old[j+1:] for j in range(len(old))}
            candidates={p for p in candidates if p in allowed and (ref,p) not in occupied
                        and all(sign*(int(p)-n)>0 if j<i else sign*(n-int(p))>0 for j,n in good)}
            if len(candidates)!=1:continue
            new=candidates.pop()
            for net in graph['nets']:
                for node in net['nodes']:
                    if (node['ref'],node['pin'])==(ref,old):node['pin']=new
            anchor['pin']=new;anchor['confidence']=min(anchor.get('confidence',1),.75)
            anchor['source']='erc_healed';occupied.add((ref,new))
            actions.append({'kind':'catalog_ordered_digit_repair','ref':ref,'old_pin':old,'pin':new,
                            'bbox':[anchor['x']-12,anchor['y']-12,anchor['x']+12,anchor['y']+12],
                            'confidence':.75,'source':'erc_healed','reason':'Fused pin digit resolved by package and three ordered observations'})
    return actions


def _distance(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/max(1e-12,dx*dx+dy*dy)))
    q=(a[0]+t*dx,a[1]+t*dy)
    return math.dist(point,q),q


def _local_wire_label(anchor,label,wire,metadata):
    """Certify a short, straight, observed conductor outside symbol interiors."""
    if wire.get('bus'):return False
    a,b=wire['p0'],wire['p1'];horizontal=abs(b[0]-a[0])>=abs(b[1]-a[1])
    if horizontal==bool(label.get('vertical')):return False
    bbox=label['bbox'];center=((bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2)
    d,p=_distance((anchor['x'],anchor['y']),a,b)
    ld,q=_distance(center,a,b)
    label_half=(bbox[3]-bbox[1] if horizontal else bbox[2]-bbox[0])/2
    if d>8 or ld>label_half+15 or math.dist(p,q)>600:return False
    dx,dy=anchor.get('direction',(0,0))
    if (q[0]-p[0])*dx+(q[1]-p[1])*dy < -3:return False
    # Check only the proposed path. An unmasked symbol elsewhere is irrelevant.
    for box in metadata.get('unverified_body_regions',[]):
        x0,y0,x1,y1=box
        for step in range(max(2,math.ceil(math.dist(p,q)/2))+1):
            t=step/max(2,math.ceil(math.dist(p,q)/2));x=p[0]+t*(q[0]-p[0]);y=p[1]+t*(q[1]-p[1])
            if x0+2<x<x1-2 and y0+2<y<y1-2:return False
    # The local skeleton must actually cover the route, rather than relying on
    # a long Hough segment that can span a masked or missing interval.
    edges=[e for e in metadata.get('wire_edges',[]) if e.get('confidence',0)>=.6]
    length=math.dist(p,q);steps=max(1,math.ceil(length/4))
    for step in range(steps+1):
        point=(p[0]+step/steps*(q[0]-p[0]),p[1]+step/steps*(q[1]-p[1]))
        if not any(_distance(point,c,d)[0]<=5 for e in edges for c,d in zip(e['points'],e['points'][1:])):return False
    return True


def recover_locally(circuit_graph,image_metadata=None):
    graph=deepcopy(circuit_graph)
    metadata=graph.setdefault('image_metadata',deepcopy(image_metadata or {}))
    if image_metadata is not None:metadata=graph['image_metadata']=deepcopy(image_metadata)
    actions=repair_impossible_numbers(graph,metadata)
    pins={(p['ref'],p['pin']):net for net in graph['nets'] for p in net['nodes']}
    wires={w['id']:w for w in metadata.get('wires',[])}
    for anchor in metadata.get('pin_anchors',[]):
        key=anchor['ref'],anchor['pin'];net=pins.get(key)
        # A named observation is retained. Moving one member of an established
        # multi-pin net could silently lose a previously correct connection.
        if net is None or not anonymous(net['name']) or len(net['nodes'])!=1:continue
        wire=wires.get(anchor.get('wire'))
        if wire is None:continue
        labels=[l for l in metadata.get('external_labels',[]) if l.get('confidence',0)>=.85
                and l.get('role')=='external_net_label' and l.get('wire')==wire['id']
                and l.get('text','').upper() not in ('NC','N/C','UNKNOWN','UNCONNECTED')
                and _local_wire_label(anchor,l,wire,metadata)]
        names={label['text'] for label in labels}
        if len(names)!=1:continue
        name=names.pop()
        if anonymous(name):continue
        target=next((n for n in graph['nets'] if n['name']==name),None)
        node=net['nodes'][0]
        if target:target['nodes'].append(node);graph['nets'].remove(net);pins[key]=target
        else:net['name']=name
        actions.append({'kind':'local_wire_label','ref':key[0],'pin':key[1],'net':name,
                        'bbox':[anchor['x']-12,anchor['y']-12,anchor['x']+12,anchor['y']+12],
                        'reason':'Unnamed isolated pin attached along a locally masked trace',
                        'confidence':min(.85,anchor.get('confidence',.85)),'source':'wire_trace'})
    metadata['connectivity_policy']='local_additive'
    metadata.setdefault('local_recovery_actions',[]).extend(actions)
    metadata.setdefault('review_hotspots',[]).extend(actions)
    metadata['applied']=bool(metadata['local_recovery_actions'])
    if actions:graph.setdefault('warnings',[]).append(f'{len(actions)} local pin/label observations recovered; review highlighted source evidence.')
    return graph
