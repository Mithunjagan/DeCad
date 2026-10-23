"""Mask/trace physical wiring before symbolic labels are applied.

Pixel work is banded. Four-arm crossings have separate conductor ports unless
a filled dot is corroborated; a crossing pixel is not an electrical junction.
Confidence scores are review heuristics, not calibrated accuracy estimates.
"""
import itertools
import math
import re

import cv2
import numpy as np


def _passive_ref(ref):
    return re.fullmatch(r'[RCLD]\d+[A-H]?',ref) is not None


def verified_bodies(anchors,segments,ch):
    """Reject enclosing bus/wire rectangles that contain other ICs or through wires."""
    result=[]
    for ref,_,_,box in anchors:
        if box is None or not ref.startswith(('U','IC')):continue
        x0,y0,x1,y1=box
        if any(other!=ref and other.startswith(('U','IC')) and x0<x<x1 and y0<y<y1
               for other,x,y,_ in anchors):continue
        through=any((s.horizontal and y0+ch<s.y0<y1-ch and s.x0<x0-ch and s.x1>x1+ch)
                    or (not s.horizontal and x0+ch<s.x0<x1-ch and s.y0<y0-ch and s.y1>y1+ch)
                    for s in segments)
        if not through and box not in result:result.append(box)
    return result


def unmasked_components(components,anchors,bodies):
    """Every recognized symbol needs an observed, erasable body before rewiring."""
    grouped={}
    for (ref,pin),value in anchors.items():grouped.setdefault(ref,{})[pin]=value
    missing=[]
    for ref,value in components.items():
        pins=grouped.get(ref,{})
        if not pins or value in ('','UNKNOWN'):
            missing.append(ref);continue
        if ref.startswith(('U','IC')):
            if not any(p.get('body') in bodies for p in pins.values()):missing.append(ref)
        elif _passive_ref(ref) and set(pins)=={'1','2'}:
            a,b=pins['1'],pins['2'];da=a.get('direction',[0,0]);db=b.get('direction',[0,0])
            dx,dy=abs(a['x']-b['x']),abs(a['y']-b['y'])
            if da[0]*db[0]+da[1]*db[1]>-.8 or not (min(dx,dy)<3 and max(dx,dy)>10):missing.append(ref)
        else:missing.append(ref)
    return sorted(missing)


def power_pin_numbers(components,tables=None):
    """Literal package alternatives only; fuzzy part matches cannot certify a rail."""
    if tables is None:
        from .recognition_catalog import pin_tables
        tables=pin_tables
    result={}
    for ref,value in components.items():
        if value in ('','UNKNOWN'):continue
        if _passive_ref(ref):
            result[ref]={'1','2'};continue
        alternatives={frozenset(row['pins']) for row in tables(value) if row['pins']}
        if len(alternatives)==1:result[ref]=set(alternatives.pop())
    return result


def mask_canvas(binary,bodies,texts,segments,terminal_wires=()):
    canvas=binary.copy();h,w=canvas.shape
    def restore(a,b,thickness):
        pad=max(2,thickness+1)
        x0=max(0,min(a[0],b[0])-pad);y0=max(0,min(a[1],b[1])-pad)
        x1=min(w,max(a[0],b[0])+pad+1);y1=min(h,max(a[1],b[1])+pad+1)
        if x1<=x0 or y1<=y0:return
        strip=np.zeros((y1-y0,x1-x0),np.uint8)
        cv2.line(strip,(a[0]-x0,a[1]-y0),(b[0]-x0,b[1]-y0),255,thickness)
        canvas[y0:y1,x0:x1]|=cv2.bitwise_and(binary[y0:y1,x0:x1],strip)
    for token in texts:
        x0,y0,x1,y1=(max(0,int(token.x0)-1),max(0,int(token.y0)-1),
                     min(w,int(token.x1)+1),min(h,int(token.y1)+1))
        if x1<=x0 or y1<=y0:continue
        canvas[y0:y1,x0:x1]=0
        # Restore only the straight wire through the text box, not its glyphs.
        for s in segments:
            if s.horizontal and s.x0<=x0-2 and s.x1>=x1+2 and y0<=s.y0<y1:
                restore((x0,int(s.y0)),(x1-1,int(s.y0)),max(1,round(s.thick)))
            elif not s.horizontal and s.y0<=y0-2 and s.y1>=y1+2 and x0<=s.x0<x1:
                restore((int(s.x0),y0),(int(s.x0),y1-1),max(1,round(s.thick)))
    # A number's text box can overlap the end of a verified terminal lead.
    # Preserve that observed lead before erasing the symbol's own outline.
    for i in terminal_wires:
        s=segments[i]
        restore((round(s.x0),round(s.y0)),(round(s.x1),round(s.y1)),max(1,round(s.thick)))
    for box in bodies:
        x0,y0,x1,y1=map(round,box)
        canvas[max(0,y0+2):min(h,y1-1),max(0,x0+2):min(w,x1-1)]=0
        # Outlines are symbol ink too; otherwise the outline shorts every pin.
        # Exterior lead endpoints remain available to 8px terminal anchoring.
        cv2.rectangle(canvas,(x0,y0),(x1,y1),0,5)
    # A bus trunk is a drawing container, not a conductor joining its members.
    # Verified indexed tap labels are merged later during symbolic stitching.
    for s in segments:
        if s.bus:cv2.line(canvas,(round(s.x0),round(s.y0)),(round(s.x1),round(s.y1)),0,max(3,round(s.thick)+2))
    return canvas


def heal_gaps(canvas,band=512):
    result=canvas.copy();height=canvas.shape[0]
    for start in range(0,height,band):
        a,b=max(0,start-4),min(height,start+band+4)
        patch=canvas[a:b]
        horizontal=cv2.morphologyEx(patch,cv2.MORPH_OPEN,np.ones((1,3),np.uint8))
        vertical=cv2.morphologyEx(patch,cv2.MORPH_OPEN,np.ones((3,1),np.uint8))
        horizontal=cv2.morphologyEx(horizontal,cv2.MORPH_CLOSE,np.ones((1,3),np.uint8))
        vertical=cv2.morphologyEx(vertical,cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))
        repaired=cv2.bitwise_or(patch,cv2.bitwise_or(horizontal,vertical))
        result[start:min(height,start+band)]=repaired[start-a:min(height,start+band)-a]
    healed=cv2.bitwise_and(result,cv2.bitwise_not(canvas))
    return result,healed


def _thin(mask):
    image=np.pad((mask>0).astype(np.uint8),1)
    for _ in range(64):
        removed=0
        for second in (False,True):
            p2=image[:-2,1:-1];p3=image[:-2,2:];p4=image[1:-1,2:];p5=image[2:,2:]
            p6=image[2:,1:-1];p7=image[2:,:-2];p8=image[1:-1,:-2];p9=image[:-2,:-2]
            around=[p2,p3,p4,p5,p6,p7,p8,p9,p2]
            count=p2+p3+p4+p5+p6+p7+p8+p9
            transitions=sum((a==0)&(b==1) for a,b in zip(around,around[1:]))
            center=image[1:-1,1:-1]
            remove=(center==1)&(count>=2)&(count<=6)&(transitions==1)
            if second:remove&=(p2*p4*p8==0)&(p2*p6*p8==0)
            else:remove&=(p2*p4*p6==0)&(p4*p6*p8==0)
            removed+=int(remove.sum());center[remove]=0
        if not removed:break
    return image[1:-1,1:-1]*255


def skeletonize(canvas,band=512,overlap=32):
    result=np.zeros_like(canvas);height=canvas.shape[0]
    for start in range(0,height,band):
        a,b=max(0,start-overlap),min(height,start+band+overlap)
        thin=_thin(canvas[a:b])
        result[start:min(height,start+band)]=thin[start-a:min(height,start+band)-a]
    return result


def dot_score(binary,x,y,width=2.,vector_dots=()):
    if any(math.hypot(x-dx,y-dy)<=max(2.,radius) for dx,dy,radius in vector_dots):return 1.
    radius=max(5,round(width*3));h,w=binary.shape
    x,y=round(x),round(y);x0,y0=max(0,x-radius),max(0,y-radius)
    patch=binary[y0:min(h,y+radius+1),x0:min(w,x+radius+1)]
    if not patch.size:return 0.
    dist=cv2.distanceTransform(patch,cv2.DIST_L2,5)
    cx,cy=x-x0,y-y0
    core=float(dist[cy,cx])
    core_score=np.clip((core-width/2)/max(1.,width*1.5),0.,1.)
    yy,xx=np.indices(patch.shape);dx,dy=xx-cx,yy-cy
    off_axis=(abs(dx)>max(.5,width/2))&(abs(dy)>max(.5,width/2))&(dx*dx+dy*dy<=(2*width)**2)
    fractions=[]
    for sx,sy in itertools.product((-1,1),repeat=2):
        region=off_axis&(sx*dx>0)&(sy*dy>0)
        if region.any():fractions.append(float((patch[region]>0).mean()))
    roundness=min(fractions) if fractions else 0.
    return float(min(core_score,roundness))


def trace(page,bodies,texts,segments,anchors,reader=None,labels=()):
    """Return physical graph, conductor-to-segment mapping, and review regions.

    anchors maps (reference, physical number) to x/y/direction/legacy wire id.
    No net label can join paths during this stage.
    """
    anchors={key:dict(value) for key,value in anchors.items()}
    for value in anchors.values():
        box=value.get('body');direction=value.get('direction',[0,0])
        if box is not None and box in bodies:
            value['observed_xy']=[value['x'],value['y']]
            if abs(direction[0])>=abs(direction[1]):value['x']=box[0] if direction[0]<0 else box[2]
            else:value['y']=box[1] if direction[1]<0 else box[3]
    canvas=mask_canvas(page.binary,bodies,texts,segments,{value['wire'] for value in anchors.values()})
    # A resistor/diode outline is ink between two terminals, not a wire.
    # Mask only an observed opposing pair; never infer a missing terminal.
    passive={}
    for (ref,pin),value in anchors.items():
        if _passive_ref(ref):passive.setdefault(ref,{})[pin]=value
    for pins in passive.values():
        if set(pins)!={'1','2'}:continue
        a,b=pins['1'],pins['2'];dx=b['x']-a['x'];dy=b['y']-a['y']
        da=a.get('direction',[0,0]);db=b.get('direction',[0,0])
        if da[0]*db[0]+da[1]*db[1]>-.8:continue
        span=math.hypot(dx,dy)
        if span<10:continue
        margin=max(3,round(min(span*.3,24)))
        if abs(dx)<3 and abs(dy)>10:
            x=round((a['x']+b['x'])/2)
            canvas[max(0,round(min(a['y'],b['y']))+3):round(max(a['y'],b['y']))-2,max(0,x-margin):x+margin+1]=0
        elif abs(dy)<3 and abs(dx)>10:
            y=round((a['y']+b['y'])/2)
            canvas[max(0,y-margin):y+margin+1,max(0,round(min(a['x'],b['x']))+3):round(max(a['x'],b['x']))-2]=0
    canvas,healed=heal_gaps(canvas)
    thin=skeletonize(canvas)
    del canvas
    height,width=thin.shape
    ys,xs=np.nonzero(thin)
    pixels=set(map(int,ys.astype(np.int64)*width+xs));del ys,xs,thin
    def neighbors(pixel):
        y,x=divmod(pixel,width);out=[]
        for dx,dy in ((0,-1),(1,0),(0,1),(-1,0),(-1,-1),(1,-1),(1,1),(-1,1)):
            if not (0<=x+dx<width and 0<=y+dy<height):continue
            candidate=pixel+dy*width+dx
            if candidate not in pixels:continue
            # Do not turn a right-angle path into a diagonal triangle.
            if dx and dy and (pixel+dx in pixels or pixel+dy*width in pixels):continue
            out.append(candidate)
        return out
    def near(x,y,radius=8):
        x,y=round(x),round(y);found=[]
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                if dx*dx+dy*dy>radius*radius or not (0<=x+dx<width and 0<=y+dy<height):continue
                p=(y+dy)*width+x+dx
                if p in pixels:found.append((dx*dx+dy*dy,p))
        return min(found)[1] if found else None
    critical={p for p in pixels if len(neighbors(p))!=2}
    anchor_pixels={}
    for key,value in anchors.items():
        pixel=near(value['x'],value['y'])
        if pixel is None and value.get('observed_xy'):pixel=near(*value['observed_xy'])
        anchor_pixels[key]=pixel
    critical.update(p for p in anchor_pixels.values() if p is not None)
    clusters=[];owner={}
    for first in sorted(critical):
        if first in owner:continue
        group=len(clusters);stack=[first];owner[first]=group;cluster=[]
        while stack:
            p=stack.pop();cluster.append(p)
            for q in neighbors(p):
                if q in critical and q not in owner:owner[q]=group;stack.append(q)
        clusters.append(cluster)
    nodes=[];ports={};centers={};confidence={};sources={};hotspots=[]
    median=float(np.median([s.thick for s in segments])) if segments else 2.
    vector_dots=page.vector.dots if getattr(page,'vector',None) is not None else ()
    for group,cluster in enumerate(clusters):
        center=(float(np.mean([p%width for p in cluster])),float(np.mean([p//width for p in cluster])))
        centers[group]=center
        boundary={q:p for p in cluster for q in neighbors(p) if q not in critical}
        arms=sorted(boundary);degree=len(arms);connected=True;score=None;source='vector' if vector_dots else 'wire_trace'
        certainty=.95 if degree<=3 else .45
        kind='endpoint' if degree<=1 else 'pin_terminal' if degree==2 else 't_junction'
        pair_groups=[arms]
        if degree==4:
            score=dot_score(page.binary,*center,median,vector_dots)
            connected=score>.7;certainty=.9 if score<.3 else .6;kind='junction' if connected else 'crossing'
            if .3<=score<=.7:
                answer=reader.query(page.gray,(center[0]-48,center[1]-48,center[0]+48,center[1]+48),'junction') if reader else None
                if answer is not None:
                    connected=answer.decision=='connected_junction';source='vlm_tiebreak';certainty=.75
                hotspots.append({'bbox':[center[0]-48,center[1]-48,center[0]+48,center[1]+48],
                                 'reason':'Ambiguous junction dot','confidence':certainty,'source':source})
            if connected:kind='junction';certainty=max(certainty,.85)
            else:
                def vector(p):
                    v=np.array([p%width-center[0],p//width-center[1]],dtype=float)
                    return v/max(1e-9,np.linalg.norm(v))
                vectors={p:vector(p) for p in arms}
                pairings=[[(arms[0],arms[j]),tuple(p for k,p in enumerate(arms) if k not in (0,j))] for j in (1,2,3)]
                best=min(pairings,key=lambda pairs:sum(1+float(np.dot(vectors[a],vectors[b])) for a,b in pairs))
                pair_groups=[list(pair) for pair in best]
        elif degree>4:
            kind='ambiguous';certainty=.35
            # Preserve only opposite directions; do not short a noisy cluster.
            by_axis={}
            for p in arms:
                angle=math.atan2(p//width-center[1],p%width-center[0])%math.pi
                by_axis.setdefault(round(angle/(math.pi/4))%4,[]).append(p)
            pair_groups=list(by_axis.values())
            hotspots.append({'bbox':[center[0]-16,center[1]-16,center[0]+16,center[1]+16],
                             'reason':'Noisy wire intersection','confidence':certainty,'source':source})
        for index,group_arms in enumerate(pair_groups):
            identity=f'W{group}:{index}'
            nodes.append({'id':identity,'x':center[0],'y':center[1],'kind':kind,'degree':degree,
                          'confidence':certainty,'source':source,**({'dot_score':score} if score is not None else {})})
            confidence[identity]=certainty;sources[identity]=source
            for q in group_arms:ports[group,q]=identity
        if not arms:
            identity=f'W{group}:0'
            confidence.setdefault(identity,certainty);sources.setdefault(identity,source)
    visited=set();edges=[];pixel_edge={};edge_roots=[]
    for (group,q),start_node in ports.items():
        p=next(p for p in clusters[group] if q in neighbors(p))
        key=(min(p,q),max(p,q))
        if key in visited:continue
        visited.add(key);path=[p,q];previous,current=p,q
        while current not in critical:
            onward=[r for r in neighbors(current) if r!=previous]
            if len(onward)!=1:break
            nxt=onward[0];visited.add((min(current,nxt),max(current,nxt)))
            previous,current=current,nxt;path.append(current)
        if current not in owner:continue
        end_node=ports.get((owner[current],previous),f'W{owner[current]}:0')
        points=np.array([[p%width,p//width] for p in path],dtype=np.int32)
        polyline=cv2.approxPolyDP(points.reshape(-1,1,2),.5,False).reshape(-1,2).tolist()
        repaired=[p for p in path if healed[p//width,p%width]]
        certainty=min(confidence[start_node],confidence.get(end_node,.35),.65 if repaired else 1.)
        source='vlm_tiebreak' if 'vlm_tiebreak' in (sources[start_node],sources.get(end_node)) else 'vector' if getattr(page,'vector',None) is not None else 'wire_trace'
        index=len(edges)
        edges.append({'id':f'E{index}','a':start_node,'b':end_node,'points':polyline,'confidence':certainty,'source':source})
        for pixel in path:
            if pixel not in critical:pixel_edge[pixel]=index
        if repaired:
            px,py=repaired[len(repaired)//2]%width,repaired[len(repaired)//2]//width
            hotspots.append({'bbox':[px-5,py-5,px+5,py+5],'reason':'Healed scan gap','confidence':.65,'source':'wire_trace'})
    parent={n['id']:n['id'] for n in nodes}
    def find(value):
        parent.setdefault(value,value)
        while parent[value]!=value:parent[value]=parent[parent[value]];value=parent[value]
        return value
    for edge in edges:parent[find(edge['a'])]=find(edge['b'])
    root_ids={root:i for i,root in enumerate(sorted({find(key) for key in parent}))}
    for node in nodes:node['physical_net']=root_ids[find(node['id'])]
    edge_roots=[root_ids[find(edge['a'])] for edge in edges]
    for edge,root in zip(edges,edge_roots):edge['physical_net']=root
    wire_roots=[]
    for segment in segments:
        hits=[]
        for fraction in (.2,.4,.5,.6,.8):
            x=segment.x0+(segment.x1-segment.x0)*fraction;y=segment.y0+(segment.y1-segment.y0)*fraction
            pixel=near(x,y,3)
            if pixel in pixel_edge:hits.append(edge_roots[pixel_edge[pixel]])
        wire_roots.append(hits[0] if hits and len(set(hits))==1 else None)
    pin_anchors=[]
    for key,value in anchors.items():
        pixel=anchor_pixels[key];node=None
        if pixel in owner:
            group=owner[pixel];options=[n for n in nodes if n['id'].startswith(f'W{group}:')]
            if len(options)==1:node=options[0]
            elif options:
                # A terminal on a crossing selects its own outgoing conductor.
                direction=value.get('direction',[1,0]);choices=[]
                for (g,q),port in ports.items():
                    if g!=group:continue
                    dx,dy=q%width-value['x'],q//width-value['y']
                    choices.append((dx*direction[0]+dy*direction[1],port))
                if choices:node=next(n for n in options if n['id']==max(choices)[1])
        certainty=min(.9,node['confidence']) if node else .4
        pin_anchors.append({'ref':key[0],'pin':key[1],**value,'confidence':certainty,
                            'source':'vector' if getattr(page,'vector',None) is not None else 'wire_trace',
                            'graph_node':node['id'] if node else None,'physical_net':node['physical_net'] if node else None})
        if node is None:
            hotspots.append({'bbox':[value['x']-12,value['y']-12,value['x']+12,value['y']+12],
                             'ref':key[0],'pin':key[1],'reason':'Unresolved wire terminal anchor','confidence':.4,'source':'wire_trace'})
    for wire in {value['wire'] for value in anchors.values()}:
        roots={pin['physical_net'] for pin in pin_anchors if pin['wire']==wire}
        if len(roots)==1 and None not in roots:wire_roots[wire]=roots.pop()
    label_anchors=[]
    for index,label in enumerate(labels):
        wire=label.get('wire');root=None
        if wire is not None:
            segment=segments[wire];box=label['bbox']
            x=min(segment.x1,max(segment.x0,(box[0]+box[2])/2)) if segment.horizontal else segment.x0
            y=segment.y0 if segment.horizontal else min(segment.y1,max(segment.y0,(box[1]+box[3])/2))
            for shift in (0,-2,2,-4,4):
                pixel=near(x+shift if segment.horizontal else x,y if segment.horizontal else y+shift,3)
                if pixel in pixel_edge:root=edge_roots[pixel_edge[pixel]];break
        label_anchors.append({'index':index,'physical_net':root})
    return {'coordinate_space':'working_pixels','width':width,'height':height,
            'source_size':list(getattr(page,'source_size',None) or (width,height)),
            'source_affine':page.affine.tolist() if getattr(page,'affine',None) is not None else [[1,0,0],[0,1,0]],
            'wire_nodes':nodes,'wire_edges':edges,'wire_roots':wire_roots,'pin_anchors':pin_anchors,
            'review_hotspots':hotspots,'component_bodies':[list(box) for box in bodies],'label_anchors':label_anchors,
            'algorithm':'masked_directional_closing_zhang_suen_physical_graph'}


def reconcile_pin_groups(legacy,node_wires,pin_anchors,*,require_complete=False,mask_complete=True):
    """A legacy merged segment can span two distinct traced physical nets.

    Register by physical terminal, rather than forcing one net per old segment.
    An old group with any unmapped terminal is kept intact for source review.
    """
    observed={(p['ref'],p['pin']):p.get('physical_net') for p in pin_anchors}
    old={}
    for key,wire in node_wires.items():old.setdefault(legacy.find(wire),set()).add(key)
    blocked={root for root,keys in old.items() if any(observed.get(key) is None for key in keys)}
    if require_complete and (blocked or not mask_complete):
        # Partial masking can still carry paths through an unrecognized symbol.
        # A successfully anchored subset does not certify the intervening ink.
        return {key:legacy.find(wire) for key,wire in node_wires.items()},{},set(old)
    new={};assigned={};raw_to_final={}
    for root,keys in old.items():
        if root in blocked:
            assigned.update({key:root for key in keys});continue
        for key in keys:new.setdefault(observed[key],set()).add(key)
    offset=len(legacy.p)
    for raw,members in new.items():
        previous=legacy.find(node_wires[next(iter(members))])
        target=previous if members==old[previous] else offset+raw
        assigned.update({key:target for key in members});raw_to_final[raw]=target
    return assigned,raw_to_final,blocked
