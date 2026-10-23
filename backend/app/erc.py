"""Local, evidence-bound repair of image proposals before strict graph validation."""
from collections import defaultdict,deque
from copy import deepcopy
import math
import re

from .local_recovery import anonymous,_distance

GROUND={'GND','AGND','DGND','GNDA','GNDD'}
POWER=re.compile(r'^(?:VCC|VDD|AVCC|AVDD|VBUS|\+\d+(?:\.\d+)?V\d*)$')


def erc_self_heal(circuit_graph,image_metadata=None):
    graph=deepcopy(circuit_graph)
    metadata=graph.setdefault('image_metadata',deepcopy(image_metadata or {}))
    if image_metadata is not None:metadata=graph['image_metadata']=deepcopy(image_metadata)
    actions=[];warnings=graph.setdefault('warnings',[])
    anchors={(p['ref'],str(p['pin'])):p for p in metadata.get('pin_anchors',[])}
    def note(reason,kind,anchor=None,**fields):
        action={'kind':kind,'reason':reason,'source':'erc_healed',**fields}
        if anchor:
            action.update(ref=anchor['ref'],pin=anchor['pin'],bbox=[anchor['x']-12,anchor['y']-12,anchor['x']+12,anchor['y']+12])
        if action not in metadata.get('erc_actions',[]) and action not in actions:actions.append(action)
        message='ERC: '+reason
        if message not in warnings:warnings.append(message)
    # Duplicate observations cannot enter the strict Pydantic graph. Retain the
    # original proposal and expose conflicts; never invent a replacement pin ID.
    seen={}
    for net in graph.get('nets',[]):
        kept=[]
        for node in net['nodes']:
            key=node['ref'],str(node['pin'])
            if key in seen:
                note(f'{key[0]}.{key[1]} observed more than once; retained {seen[key]} and flagged {net["name"]}.',
                     'duplicate_physical_pin',anchors.get(key),confidence=.35,review=True)
                continue
            seen[key]=net['name'];kept.append(node)
        net['nodes']=kept
    graph['nets']=[n for n in graph.get('nets',[]) if n['nodes']]
    width,height=metadata.get('width'),metadata.get('height')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (width,height)):
        metadata.setdefault('erc_actions',[]).extend(actions)
        return graph
    def valid_point(point):
        return len(point)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in point) and -16<=point[0]<=width+16 and -16<=point[1]<=height+16
    anchors={key:a for key,a in anchors.items() if valid_point((a.get('x'),a.get('y')))}
    wires=[w for w in metadata.get('wires',[]) if not w.get('bus') and valid_point(w.get('p0',[])) and valid_point(w.get('p1',[]))]
    def owners():return {(p['ref'],p['pin']):n for n in graph['nets'] for p in n['nodes']}
    def obstructed(a,b):
        for box in metadata.get('unverified_body_regions',[]):
            for t in (0,.25,.5,.75,1):
                x,y=a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])
                if box[0]+2<x<box[2]-2 and box[1]+2<y<box[3]-2:return True
        return False
    # Snap a single isolated, actually observed passive terminal. Nearby wires
    # need a corroborating terminal from a different component on that conductor.
    for key,a in anchors.items():
        by_pin=owners();net=by_pin.get(key)
        if not re.fullmatch(r'[RCLD]\d+[A-H]?',key[0]) or key[1] not in ('1','2') or net is None:continue
        if len(net['nodes'])!=1 or not anonymous(net['name']):continue
        other=anchors.get((key[0],'2' if key[1]=='1' else '1'))
        if other is None:continue
        direction=a.get('direction',[])
        if not valid_point(direction) or math.hypot(*direction)<.8:continue
        choices=[]
        for wire in wires:
            distance,q=_distance((a['x'],a['y']),wire['p0'],wire['p1'])
            dx,dy=q[0]-a['x'],q[1]-a['y'];forward=dx*direction[0]+dy*direction[1]
            if not 0<distance<=8 or forward<=0 or abs(dx*direction[1]-dy*direction[0])>2 or obstructed((a['x'],a['y']),q):continue
            for target_key,b in anchors.items():
                if target_key[0]==key[0] or b.get('wire')!=wire['id'] or b.get('confidence',0)<.85:continue
                target=by_pin.get(target_key)
                if target is None or target is net or by_pin.get((key[0],other['pin'])) is target:continue
                if b.get('physical_net') is None or b.get('physical_net')!=wire.get('traced_physical_net'):continue
                choices.append((distance,target,wire))
        choices.sort(key=lambda row:row[0])
        if choices and (len({id(c[1]) for c in choices})==1 or choices[1][0]-choices[0][0]>=2):
            _,target,wire=choices[0];target['nodes'].extend(net['nodes']);graph['nets'].remove(net)
            note(f'{key[0]}.{key[1]} snapped outward to {target["name"]} within 8px.','dangling_passive_snap',a,
                 net=target['name'],wire=wire['id'],confidence=.75)
    # Orphan text is attached independently of other sheet anchors. A verified
    # contradictory name is a review conflict, never permission to join rails.
    for label in metadata.get('external_labels',[]):
        if label.get('wire') is not None or label.get('confidence',0)<.9 or label.get('role')!='external_net_label':continue
        name=label.get('text','')
        if name.upper() in ('NC','N/C','UNKNOWN','UNCONNECTED') or anonymous(name):continue
        box=label.get('bbox',[])
        if len(box)!=4 or not valid_point(box[:2]) or not valid_point(box[2:]):continue
        choices=[]
        for wire in wires:
            horizontal=abs(wire['p1'][0]-wire['p0'][0])>=abs(wire['p1'][1]-wire['p0'][1])
            if horizontal==bool(label.get('vertical')):continue
            axis=0 if horizontal else 1;cross=1-axis
            along=min(max(wire['p0'][axis],wire['p1'][axis]),box[axis+2])-max(min(wire['p0'][axis],wire['p1'][axis]),box[axis])
            distance=min(abs(wire['p0'][cross]-box[cross]),abs(wire['p0'][cross]-box[cross+2]))
            if along<.5*(box[axis+2]-box[axis]) or distance>15:continue
            matching=[(key,a) for key,a in anchors.items() if a.get('wire')==wire['id'] and a.get('physical_net') is not None
                      and a.get('physical_net')==wire.get('traced_physical_net')]
            by_pin=owners();nets={id(by_pin[key]):by_pin[key] for key,_ in matching if key in by_pin}
            if len(nets)!=1:continue
            net=next(iter(nets.values()))
            if not anonymous(net['name']):continue
            if set((p['ref'],p['pin']) for p in net['nodes'])-{key for key,_ in matching}:continue
            choices.append((distance,wire,net))
        choices.sort(key=lambda row:row[0])
        if not choices or len({id(c[2]) for c in choices if c[0]<=choices[0][0]+2})>1:continue
        _,wire,net=choices[0]
        target=next((n for n in graph['nets'] if n['name']==name and n is not net),None)
        if target:target['nodes'].extend(net['nodes']);graph['nets'].remove(net)
        else:net['name']=name
        label['wire']=wire['id']
        note(f'Orphan label {name} attached to a unique parallel wire within 15px.','orphan_label_attachment',
             bbox=list(box),net=name,wire=wire['id'],confidence=.8)
    _review_power_paths(graph,metadata,anchors,note)
    metadata.setdefault('erc_actions',[]).extend(actions)
    metadata.setdefault('review_hotspots',[]).extend(actions)
    return graph


def _review_power_paths(graph,metadata,anchors,note):
    """Report suspected shorts without choosing an edge to delete or a new net."""
    labels=metadata.get('external_labels',[])
    named=[(a,labels[a['index']]['text']) for a in metadata.get('label_anchors',[])
           if isinstance(a.get('index'),int) and 0<=a['index']<len(labels) and a.get('graph_node')]
    edges={e['id']:e for e in metadata.get('wire_edges',[]) if 'id' in e and 'a' in e and 'b' in e}
    disabled=set(metadata.get('erc_disabled_edges',[]))
    for power,pname in named:
        if not POWER.fullmatch(pname):continue
        for ground,gname in named:
            if gname not in GROUND:continue
            adjacency=defaultdict(list)
            for identity,edge in edges.items():
                if identity not in disabled:
                    adjacency[edge['a']].append((edge['b'],identity));adjacency[edge['b']].append((edge['a'],identity))
            start,end=power['graph_node'],ground['graph_node'];previous={start:None};queue=deque([start])
            while queue and end not in previous:
                node=queue.popleft()
                for target,identity in adjacency[node]:
                    if target not in previous:previous[target]=(node,identity);queue.append(target)
            if end not in previous:continue
            path=[];node=end
            while previous[node] is not None:
                node,identity=previous[node];path.append(identity)
            if not path:continue
            points=[p for identity in path for p in edges[identity].get('points',[])]
            bbox=([min(p[0] for p in points)-2,min(p[1] for p in points)-2,
                   max(p[0] for p in points)+2,max(p[1] for p in points)+2] if points else None)
            note(f'{pname}/{gname} share an observed path; suspected short, source review required. Connections retained.',
                 'power_ground_review',path=path,bbox=bbox,confidence=.4,review=True)
