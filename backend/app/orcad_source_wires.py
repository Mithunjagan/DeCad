"""Evidence-constrained reuse of source conductors in native Capture routing.

Source roots are admitted only when every reviewed pin on that root agrees on its
net. Crossing ports remain separate. Every newly routed segment is audited.
"""
from collections import defaultdict
import math
import re


def routing_hints(graph):
    """Image traces are advisory; only placed pin hotspots define emitted wires."""
    return {'accepted_edges':[],'rejected_edges':[], 'source_junctions':[],
            'source_crossings':[],'inferred_segments':[],
            'raw_segments_disabled':True,
            'source_segments_used_as_hints_only':len(graph.get('image_metadata',{}).get('wire_edges',[]))}


def point_transform(metadata, scale, margin=300, grid=10):
    width = metadata.get('width')
    if not width or width <= 0:
        return None
    # Geometry is in processed-image pixels (the same frame as pin_anchors).
    # The affine maps original pixels into that frame; applying it again here
    # would scale/rotate the conductor paths twice.
    return lambda p: tuple(round((margin + scale * float(v) / width) / grid) * grid for v in p)


def named_nets(graph):
    """Allow real source names; suppress generated OCR bookkeeping aliases."""
    meta = graph.get('image_metadata', {})
    source_names = {name for row in meta.get('physical_labels', []) for name in row.get('labels', [])}
    names = set()
    for net in graph['nets']:
        name = net['name']
        if name in source_names or net.get('source') == 'net_label' or net.get('metadata', {}).get('explicit_name'):
            names.add(name)
        elif real_net_name(name):
            # Preserve arbitrary reviewed/source signal names. No particular
            # circuit's label vocabulary is built into the exporter.
            names.add(name)
    return names


def real_net_name(name):
    return bool(name and not re.match(r'^(?:N(?:\$|_)?\d+(?:_\d+)?$|NET(?:\$|_)?\d+$|UNCONNECTED(?:\b|[:_]).*|UNCONNECTED$|N_|NET-)',name,re.I))


def global_nets(graph):
    """Disconnected fragments require source global/off-page evidence, not just a name."""
    return {n['name'] for n in graph['nets'] if
            re.fullmatch(r'(?:GND|AGND|DGND|VCC|VDD|VSS|VEE|[+-]\d+V)',n['name'],re.I)
            or n.get('metadata',{}).get('connection_kind') in ('global','hierarchical','offpage')}


def simplify(points, tolerance):
    """Remove scan stair steps while retaining genuine conductor bends."""
    if len(points) <= 2:
        return points
    a, b = points[0], points[-1]
    dx,dy = b[0]-a[0],b[1]-a[1]
    length = math.hypot(dx,dy)
    distances = [abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length if length else math.dist(a,p) for p in points]
    index = max(range(len(points)),key=distances.__getitem__)
    if distances[index] <= tolerance:
        return [a,b]
    return simplify(points[:index+1],tolerance)[:-1]+simplify(points[index:],tolerance)


def candidates(graph, scale, aliases, margin=300):
    meta = graph.get('image_metadata', {})
    transform = point_transform(meta,scale,margin)
    report = {'accepted_edges': [], 'rejected_edges': [], 'ambiguous_roots': [],
              'source_junctions': [], 'source_crossings': [], 'inferred_segments': []}
    if transform is None:
        return [],report
    pin_net = {(p['ref'],str(p['pin'])):aliases[n['name']] for n in graph['nets'] for p in n['nodes']}
    root_nets = defaultdict(set)
    anchors = meta.get('pin_anchors', [])
    for anchor in anchors:
        key = (anchor['ref'],str(anchor['pin']))
        if key in pin_net and anchor.get('physical_net') is not None:
            root_nets[anchor['physical_net']].add(pin_net[key])
    report['ambiguous_roots'] = [root for root,nets in root_nets.items() if len(nets)>1]
    result=[]
    nodes = {n['id']:n for n in meta.get('wire_nodes', [])}
    for edge in meta.get('wire_edges', []):
        nets = root_nets.get(edge.get('physical_net'),set())
        if len(nets)!=1:
            if nets:
                report['rejected_edges'].append({'id':edge['id'],'reason':'source root contradicts reviewed net memberships'})
            continue
        if edge.get('confidence',0)<.75:
            report['rejected_edges'].append({'id':edge['id'],'reason':'low source confidence'})
            continue
        ends=[nodes.get(edge.get(k),{}) for k in ('a','b')]
        if any(n.get('kind')=='ambiguous' for n in ends):
            report['rejected_edges'].append({'id':edge['id'],'reason':'ambiguous intersection'})
            continue
        points=edge.get('points',[])
        if not points:
            continue
        raw=simplify(points,max(2,meta.get('character_height',20)*.08))
        raw=[([ends[0]['x'],ends[0]['y']] if ends[0] else raw[0]),*raw[1:-1],
             ([ends[1]['x'],ends[1]['y']] if ends[1] else raw[-1])]
        path=[]
        for point in raw:
            p=transform(point)
            if path and p[0]!=path[-1][0] and p[1]!=path[-1][1]:
                a=path[-1]
                if min(abs(a[0]-p[0]),abs(a[1]-p[1]))<=10:
                    # Grid alignment correction is explicit evidence, not an unreported route.
                    bend=(p[0],a[1]) if abs(a[0]-p[0])>=abs(a[1]-p[1]) else (a[0],p[1])
                    path.append(bend)
                else:
                    path=[];break
            if not path or p!=path[-1]:path.append(p)
        if len(path)<2:
            report['rejected_edges'].append({'id':edge['id'],'reason':'diagonal or collapsed geometry'})
            continue
        result.append({'id':edge['id'],'net':next(iter(nets)),'path':path,'root':edge.get('physical_net'),
                       'nodes':[edge.get('a'),edge.get('b')]})
    # A non-connected crossing has two distinct graph ports. Join the two
    # collinear edges of each port into one native wire passing through the
    # crossing, so the Capture writer never creates an endpoint there.
    for node_id,node in nodes.items():
        if node.get('kind')!='crossing':continue
        touching=[p for p in result if node_id in p['nodes']]
        if len(touching)!=2:
            for path in touching:
                result.remove(path);report['rejected_edges'].append({'id':path['id'],'reason':'incomplete non-connected crossing port'})
            continue
        left,right=touching
        a=left['path'] if left['nodes'][-1]==node_id else left['path'][::-1]
        b=right['path'] if right['nodes'][0]==node_id else right['path'][::-1]
        if a[-1]!=b[0] or not (a[-2][0]==a[-1][0]==b[1][0] or a[-2][1]==a[-1][1]==b[1][1]):
            for path in touching:
                result.remove(path);report['rejected_edges'].append({'id':path['id'],'reason':'crossing port is not collinear after grid alignment'})
            continue
        ends=[next(n for n in p['nodes'] if n!=node_id) for p in touching]
        result.remove(left);result.remove(right)
        result.append({**left,'id':left['id']+'+'+right['id'],'path':a[:-1]+b[1:],'nodes':ends})
    for node in nodes.values():
        nets=root_nets.get(node.get('physical_net'),set())
        if len(nets)!=1:
            continue
        entry={'id':node['id'],'at':transform((node['x'],node['y'])),'net':next(iter(nets)),
               'kind':node['kind'],'confidence':node.get('confidence')}
        if node['kind'] in ('junction','t_junction') and node.get('confidence',0)>=.75:
            report['source_junctions'].append(entry)
        elif node['kind']=='crossing':
            report['source_crossings'].append(entry)
    return result,report


def seed(router, paths, report):
    """Admit only safe paths; source intersections cannot short different nets."""
    router.hotspots={h for pins in router.pins.values() for h,_,_,_ in pins}|{h for h,n in router.owner.items() if n is None}
    kept=[]
    for item in sorted(paths,key=lambda p:sum(abs(b[0]-a[0])+abs(b[1]-a[1]) for a,b in zip(p['path'],p['path'][1:])),reverse=True):
        net=item['net'];cells=[]
        for a,b in zip(item['path'],item['path'][1:]):
            a,b=tuple(v//router.grid for v in a),tuple(v//router.grid for v in b)
            dx,dy=(b[0]>a[0])-(b[0]<a[0]),(b[1]>a[1])-(b[1]<a[1])
            line=[(a[0]+dx*k,a[1]+dy*k) for k in range(abs(b[0]-a[0])+abs(b[1]-a[1])+1)]
            cells.extend(line if not cells else line[1:])
        reason=None
        for i,c in enumerate(cells):
            if c in router.blocked or c[0]<1 or c[1]<1 or c[0]>=router.W-1 or c[1]>=router.H-1:
                reason='source segment meets a placed symbol or page boundary';break
            if c in router.owner and router.owner[c]!=net:
                reason='source segment meets another reviewed terminal';break
            other=router.occ.get(c)
            if not other or other[0]==net:
                continue
            prev,nxt=(cells[i-1] if i else None),(cells[i+1] if i+1<len(cells) else None)
            axis='H' if prev and nxt and prev[1]==c[1]==nxt[1] else 'V' if prev and nxt and prev[0]==c[0]==nxt[0] else None
            if not (axis and other[1] in ('H','V') and other[1]!=axis):
                reason='intersection would create an unsupported electrical junction';break
        if reason:
            report['rejected_edges'].append({'id':item['id'],'reason':reason})
            continue
        router._commit(net,cells)
        report['accepted_edges'].append(item)
        kept.append(item)
    return kept
