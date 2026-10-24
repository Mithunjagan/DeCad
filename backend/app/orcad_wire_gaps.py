"""Audit native free wire ends and repair only short, source-supported gaps."""
from collections import defaultdict
import math


def endpoints(page, isolated_stubs=(), valid_aliases=()):
    wires=page['wires']
    terminals={(p['hx'],p['hy']) for part in page['parts'] for p in part['pins']}
    terminals.update((p['x'],p['y']) for p in page.get('globals',[]))
    terminals.update(tuple(p) for p in page.get('observed_ports',[]))
    isolated={tuple(p['b']) for p in isolated_stubs if p.get('source')=='isolated_terminal_stub'}
    def on(p,w):
        x,y=p;a,b,c,d=w
        return a==c==x and min(b,d)<=y<=max(b,d) or b==d==y and min(a,c)<=x<=max(a,c)
    ends={tuple(w[:2]) for w in wires}|{tuple(w[2:]) for w in wires}
    free=sorted(p for p in ends-terminals if sum(on(p,w) for w in wires)==1)
    from .orcad_source_wires import real_net_name
    # Only an actual named alias on the free endpoint terminates a stub.
    labeled={tuple((a['x'],a['y'])) for a in page.get('aliases',[]) if a.get('name') in valid_aliases or real_net_name(a.get('name',''))}
    legal=[p for p in free if p in labeled]
    free=[p for p in free if p not in labeled]
    unresolved=[{'at':list(p),'kind':'isolated_reviewed_terminal' if p in isolated else 'unterminated_wire'} for p in free]
    nearby=[{'a':list(a),'b':list(b),'distance':math.dist(a,b)} for i,a in enumerate(free)
            for b in free[:i] if 0<math.dist(a,b)<=40]
    return {'passed':not unresolved,'free_end_count':len(free),'unlabelled_loose_ends':len(free),'legal_labeled_stub_ends':len(legal),
            'isolated_reviewed_terminals':sum(p in isolated for p in free),
            'unterminated_wires':unresolved,'nearby_free_end_pairs':nearby,
            'scope':'Native drawing endpoints; aliases do not close a physical gap. Source ports may require explicit review.'}


def source_support(graph,image_path,scale,margin=300):
    """Test a short Capture segment against pixels of the actual source image."""
    if not image_path:return None
    import cv2
    import numpy as np
    image=cv2.imread(str(image_path))
    width=graph.get('image_metadata',{}).get('width')
    if image is None or not width:return None
    meta=graph['image_metadata'];affine=np.asarray(meta.get('source_affine',[[1,0,0],[0,1,0]]),dtype=float)
    if abs(np.linalg.det(affine[:,:2]))<1e-12:return None
    inverse=cv2.invertAffineTransform(affine)
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    # A narrow tolerance covers quantization and antialiased scan strokes.
    ink=cv2.dilate((gray<175).astype(np.uint8),np.ones((3,3),np.uint8))
    def support(a,b):
        points=[]
        for t in np.linspace(0,1,max(3,round(math.dist(a,b)*width/scale)*2)):
            p=((np.asarray(a)*(1-t)+np.asarray(b)*t)-margin)*width/scale
            x,y=inverse@np.array([p[0],p[1],1.0]);x,y=round(x),round(y)
            if not (0<=x<ink.shape[1] and 0<=y<ink.shape[0]):return 0.0
            points.append(bool(ink[y,x]))
        return sum(points)/len(points)
    return support


def repair(router,support,report):
    """Bridge collinear free ends only on the same reviewed net and visible ink.

    Different nets, symbol bodies, other terminals and unsupported intersections
    retain the seed validator's existing rejection rules. No labels are added.
    """
    if support is None:return {}
    from .orcad_source_wires import seed
    repairs=[];added={}
    for net,edges in list(router.edges.items()):
        adjacency=defaultdict(set)
        for edge in edges:
            a,b=tuple(edge);adjacency[a].add(b);adjacency[b].add(a)
        free=sorted(p for p,n in adjacency.items() if len(n)==1 and p not in router.hotspots)
        used=set()
        for i,a in enumerate(free):
            for b in free[i+1:]:
                if a in used or b in used or not (a[0]==b[0] or a[1]==b[1]):continue
                distance=abs(a[0]-b[0])+abs(a[1]-b[1])
                if not 1<=distance<=4:continue
                # Only close a gap in the forward direction of both strokes.
                na=next(iter(adjacency[a]));nb=next(iter(adjacency[b]))
                if (a[0]-na[0])*(b[0]-a[0])+(a[1]-na[1])*(b[1]-a[1])<=0:continue
                if (b[0]-nb[0])*(a[0]-b[0])+(b[1]-nb[1])*(a[1]-b[1])<=0:continue
                pa,pb=[v*router.grid for v in a],[v*router.grid for v in b]
                coverage=support(pa,pb)
                if coverage<.9:continue
                item={'id':f'gap:{net}:{a}:{b}','net':net,'path':[pa,pb],
                      'source':'source_supported_gap','ink_coverage':coverage}
                before=set(edges);temporary={'accepted_edges':[],'rejected_edges':[]}
                if not seed(router,[item],temporary):continue
                added.setdefault(net,set()).update(edges-before)
                repairs.append(item);report['accepted_edges'].append(item);used.update((a,b))
    report['source_supported_gap_repairs']=repairs
    return added
