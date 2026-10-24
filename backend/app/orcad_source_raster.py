"""Recover coloured source conductor geometry without rerunning or changing OCR.

This adapter is deliberately bounded to schematics with a distinct wire colour.
Monochrome inputs use their existing observed wire graph instead.
"""
from copy import deepcopy
from collections import defaultdict
import math


def enrich(graph, image_path):
    import cv2
    import numpy as np
    meta=graph.get('image_metadata',{})
    if meta.get('wire_edges') or not image_path:
        return graph
    image=cv2.imread(str(image_path))
    if image is None:return graph
    b,g,r=[image[:,:,i].astype(float) for i in range(3)]
    mask=((g>r*1.4+15)&(g>b*1.4+15)&(g<230)&(g>45)).astype(np.uint8)*255
    if np.count_nonzero(mask)<100:return graph
    affine=np.array(meta.get('source_affine',[[1,0,0],[0,1,0]]),dtype=float)
    width,height=int(meta.get('width',image.shape[1])),int(meta.get('height',image.shape[0]))
    mask=cv2.warpAffine(mask,affine,(width,height),flags=cv2.INTER_NEAREST)
    char=float(meta.get('character_height',20));minimum=max(12,int(char*.6))
    lines=[]
    for axis,kernel in ((0,(minimum,1)),(1,(1,minimum))):
        opened=cv2.morphologyEx(mask,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,kernel))
        count,labels,stats,centres=cv2.connectedComponentsWithStats(opened)
        for x,y,w,h,area in stats[1:]:
            if max(w,h)<minimum:continue
            lines.append([[int(x),round(y+h/2)],[int(x+w-1),round(y+h/2)]] if axis==0 else
                         [[round(x+w/2),int(y)],[round(x+w/2),int(y+h-1)]])
    enriched=deepcopy(graph);m=enriched['image_metadata'];anchors=m.get('pin_anchors',[])
    # Extend a detected green conductor through its short red terminal lead up to
    # the measured hotspot. No extension is made through a component body.
    for line in lines:
        horizontal=line[0][1]==line[1][1]
        axis=0 if horizontal else 1;other=1-axis
        for endpoint in (0,1):
            choices=[]
            for anchor in anchors:
                p=[anchor.get('x'),anchor.get('y')]
                if None in p or abs(p[other]-line[0][other])>char*.35:continue
                distance=abs(line[endpoint][axis]-p[axis])
                beyond=p[axis]<=min(q[axis] for q in line) if endpoint==0 else p[axis]>=max(q[axis] for q in line)
                if beyond and distance<=char*3:choices.append((distance,p))
            if choices:
                _,p=min(choices,key=lambda c:c[0]);line[endpoint][axis]=round(p[axis])
    # Intersections near line ends are scan-thickness gaps. Align those ends.
    for h in lines:
        if h[0][1]!=h[1][1]:continue
        for v in lines:
            if v[0][0]!=v[1][0]:continue
            x,y=v[0][0],h[0][1];tol=char*.2
            if min(p[0] for p in h)-tol<=x<=max(p[0] for p in h)+tol and min(p[1] for p in v)-tol<=y<=max(p[1] for p in v)+tol:
                for line,axis,value in ((h,0,x),(v,1,y)):
                    end=min(range(2),key=lambda i:abs(line[i][axis]-value))
                    if abs(line[end][axis]-value)<=tol:line[end][axis]=value
    parent=list(range(len(lines)))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def on(p,line,tol=0):
        a,b=line
        return min(a[0],b[0])-tol<=p[0]<=max(a[0],b[0])+tol and min(a[1],b[1])-tol<=p[1]<=max(a[1],b[1])+tol
    intersections=defaultdict(list)
    for i,a in enumerate(lines):
        for j in range(i):
            b=lines[j]
            if (a[0][0]==a[1][0])==(b[0][0]==b[1][0]):continue
            h,v=(a,b) if a[0][1]==a[1][1] else (b,a)
            p=(v[0][0],h[0][1])
            if on(p,a) and on(p,b):
                # At an interior four-way crossing, require a filled coloured dot.
                endpoints=any(math.dist(p,q)<char*.2 for q in (*a,*b))
                radius=max(3,round(char*.18));x,y=p
                crop=mask[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1]
                dot=float(np.count_nonzero(crop))/max(1,crop.size)>.55
                if endpoints or dot:parent[root(i)]=root(j)
                intersections[p].append({'lines':[i,j],'connected':endpoints or dot,'dot':dot})
    assigned={(p['ref'],str(p['pin'])):n['name'] for n in graph['nets'] for p in n['nodes']}
    root_names=defaultdict(set);attached={}
    for anchor in anchors:
        key=(anchor['ref'],str(anchor['pin']))
        if key not in assigned:continue
        p=(anchor['x'],anchor['y']);hits=[i for i,line in enumerate(lines) if on(p,line,char*.25)]
        if hits:
            i=min(hits,key=lambda i:min(math.dist(p,q) for q in lines[i]));attached[key]=root(i)
            root_names[root(i)].add(assigned[key])
    nodes=[];edges=[]
    for i,line in enumerate(lines):
        physical=root(i)
        if len(root_names[physical])!=1:continue
        stops={tuple(p) for p in line}
        stops.update(p for p,entries in intersections.items() if any(i in e['lines'] for e in entries))
        stops=sorted(stops,key=lambda p:p[0] if line[0][1]==line[1][1] else p[1])
        ids=[]
        for p in stops:
            entries=intersections.get(p,[])
            joined=any(e['connected'] for e in entries)
            identity=f'R{physical}:{p[0]}:{p[1]}' if joined else f'R{i}:{p[0]}:{p[1]}'
            kind=('junction' if any(e['dot'] for e in entries) else 't_junction') if joined else 'crossing' if entries else 'endpoint'
            if not any(n['id']==identity for n in nodes):nodes.append({'id':identity,'x':p[0],'y':p[1],'kind':kind,'physical_net':f'raster:{physical}','confidence':.9,'source':'wire_trace'})
            ids.append(identity)
        for k,(a,b) in enumerate(zip(stops,stops[1:])):
            if a!=b:edges.append({'id':f'RASTER{i}:{k}','a':ids[k],'b':ids[k+1],'points':[list(a),list(b)],'physical_net':f'raster:{physical}','confidence':.9,'source':'wire_trace'})
    for anchor in anchors:
        key=(anchor['ref'],str(anchor['pin']))
        if key in attached:anchor['physical_net']=f'raster:{attached[key]}'
    degree=defaultdict(int)
    for edge in edges:degree[edge['a']]+=1;degree[edge['b']]+=1
    for node in nodes:
        node['degree']=degree[node['id']]
        if node['kind']=='t_junction' and node['degree']<3:
            node['kind']='bend' if node['degree']==2 else 'endpoint'
    m['wire_nodes']=nodes;m['wire_edges']=edges
    m['export_raster_geometry']={'source':str(image_path),'method':'distinct green conductor mask with terminal-gap alignment; no OCR rerun',
                                 'lines':len(lines),'edges':len(edges),'conflicting_roots':[k for k,v in root_names.items() if len(v)>1]}
    return enriched
