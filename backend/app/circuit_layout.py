"""Deterministic placement and obstacle-aware orthogonal routing.

Nets that cannot be routed without crossing unrelated geometry retain explicit
named connections; native netlist equivalence is checked by the caller.
"""
from math import ceil

def positions(circuit):
    parts=circuit.components
    sources=[c for c in parts if c.ref.startswith(('V','I'))]
    passive=[c for c in parts if c.ref.startswith(('R','C','L'))]
    if len(parts)==3 and len(sources)==1 and len(passive)==2:
        source=sources[0]
        ground={p.ref for n in circuit.nets if n.name.upper() in ('GND','0') for p in n.nodes}
        series=next((c for c in passive if c.ref not in ground),None)
        if series:
            shunt=next(c for c in passive if c.ref!=series.ref)
            return {source.ref:(50.8,76.2,0),series.ref:(88.9,50.8,90),shunt.ref:(127,76.2,0)}
    columns=min(5,max(2,ceil(len(parts)**.5)))
    return {c.ref:(50.8+(i%columns)*63.5,50.8+(i//columns)*63.5,0) for i,c in enumerate(parts)}

def intersects(a,b,c,d):
    """Inclusive intersection for axis-aligned segments."""
    if a[0]==b[0] and c[0]==d[0]:
        return abs(a[0]-c[0])<1e-5 and max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1]))+1e-5
    if a[1]==b[1] and c[1]==d[1]:
        return abs(a[1]-c[1])<1e-5 and max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0]))+1e-5
    if a[0]!=b[0]:a,b,c,d=c,d,a,b
    return min(c[0],d[0])-1e-5<=a[0]<=max(c[0],d[0])+1e-5 and min(a[1],b[1])-1e-5<=c[1]<=max(a[1],b[1])+1e-5

def route(sch,net_names=None):
    from .engine import E,N,A,uid
    from .sexpr import children,child
    boxes=[];pin_points=[]
    for symbol in sch.symbols():
        ps=list(sch.pin_positions(symbol).values());pin_points.extend(ps)
        if ps:boxes.append((min(x for x,y in ps)-1.27,min(y for x,y in ps)-1.27,max(x for x,y in ps)+1.27,max(y for x,y in ps)+1.27))
    labels={}
    for label in children(sch.tree,'label'):
        at=child(label,'at');labels.setdefault(label[1],[]).append((float(at[1]),float(at[2])))
    occupied=[]
    for wire in children(sch.tree,'wire'):
        points=children(child(wire,'pts'),'xy');a=tuple(map(float,points[0][1:3]));b=tuple(map(float,points[1][1:3]))
        owner=next((name for name,ps in labels.items() if a in ps or b in ps),None)
        occupied.append((a,b,owner))
    def clear(a,b,net):
        if a==b:return True
        if a[0]!=b[0] and a[1]!=b[1]:return False
        for x1,y1,x2,y2 in boxes:
            if a[0]==b[0] and x1<a[0]<x2 and max(min(a[1],b[1]),y1)<min(max(a[1],b[1]),y2):return False
            if a[1]==b[1] and y1<a[1]<y2 and max(min(a[0],b[0]),x1)<min(max(a[0],b[0]),x2):return False
        return not any(owner!=net and intersects(a,b,c,d) for c,d,owner in occupied)
    unrouted=[]
    for net,points in labels.items():
        if net_names is not None and net not in net_names:continue
        connected=[points[0]]
        for dest in points[1:]:
            candidates=[]
            for start in connected:
                candidates.extend([[start,(dest[0],start[1]),dest],[start,(start[0],dest[1]),dest]])
                xs={start[0]-7.62,dest[0]+7.62,*[v for box in boxes for v in (box[0]-2.54,box[2]+2.54)]}
                ys={start[1]-7.62,dest[1]+7.62,*[v for box in boxes for v in (box[1]-2.54,box[3]+2.54)]}
                candidates.extend([start,(x,start[1]),(x,dest[1]),dest] for x in xs)
                candidates.extend([start,(start[0],y),(dest[0],y),dest] for y in ys)
            candidates.sort(key=lambda ps:sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(ps,ps[1:])))
            chosen=next((ps for ps in candidates if all(clear(a,b,net) for a,b in zip(ps,ps[1:]))),None)
            if chosen:
                for a,b in zip(chosen,chosen[1:]):
                    if a==b:continue
                    sch.tree.append(E('wire',E('pts',E('xy',N(a[0]),N(a[1])),E('xy',N(b[0]),N(b[1]))),E('stroke',E('width',N(0)),E('type',A('default'))),E('uuid',uid())))
                    occupied.append((a,b,net))
                for point in (chosen[0],dest):
                    sch.tree.append(E('junction',E('at',N(point[0]),N(point[1])),E('diameter',N(0)),E('color',N(0),N(0),N(0),N(0)),E('uuid',uid())))
            else:unrouted.append(net)
            connected.append(dest)
    return sorted(set(unrouted))

def verify_graph(expected,actual,exact=False):
    """Compare every proposed reference/value and pin's exact net partition."""
    from .engine import OperationError
    expected_parts={c.ref:c.value for c in expected.components}
    actual_parts={c['ref']:c['value'] for c in actual['components']}
    if any(actual_parts.get(ref)!=value for ref,value in expected_parts.items()):raise OperationError('Native component round-trip differs from the proposed circuit. No changes were kept.')
    if exact and set(expected_parts)!=set(actual_parts):raise OperationError('Component inventory differs from the reviewed proposal.')
    observed={ (p['ref'],str(p['pin'])):n['name'] for n in actual['nets'] for p in n['nodes'] }
    if exact:
        wanted={n.name:{(p.ref,str(p.pin)) for p in n.nodes} for n in expected.nets}
        found={n['name']:{(p['ref'],str(p['pin'])) for p in n['nodes']} for n in actual['nets'] if not n['name'].startswith('unconnected-')}
        if wanted!=found:raise OperationError('Pin/net inventory differs from the reviewed proposal.')
    for n in expected.nets:
        for p in n.nodes:
            if observed.get((p.ref,str(p.pin)))!=n.name:
                raise OperationError(f'Native connectivity mismatch at {p.ref} pin {p.pin}: expected {n.name}. No changes were kept.')
