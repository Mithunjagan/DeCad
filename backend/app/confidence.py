"""Evidence scores and source-pixel review regions for image proposals.

Scores are conservative review heuristics, not calibrated accuracy probabilities.
Human confirmation changes the review flag, never these numeric scores.
"""
from copy import deepcopy
import hashlib
import math

SOURCES={'vector','wire_trace','net_label','erc_healed','vlm_tiebreak','implicit_passive_terminal','provisional_stub'}


def _finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def source_box(box,metadata):
    if not isinstance(box,(list,tuple)) or len(box)!=4 or not all(map(_finite,box)):return None
    size=metadata.get('source_size') or [metadata.get('width'),metadata.get('height')]
    if len(size)!=2 or not all(_finite(v) and v>0 for v in size):return None
    matrix=metadata.get('source_affine',[[1,0,0],[0,1,0]])
    try:
        (a,b,c),(d,e,f)=matrix
        if not all(map(_finite,(a,b,c,d,e,f))) or abs(a*e-b*d)<1e-12:return None
        determinant=a*e-b*d
        points=[((e*(x-c)-b*(y-f))/determinant,(-d*(x-c)+a*(y-f))/determinant)
                for x,y in ((box[0],box[1]),(box[0],box[3]),(box[2],box[1]),(box[2],box[3]))]
        x0=max(0,min(size[0],min(p[0] for p in points)));y0=max(0,min(size[1],min(p[1] for p in points)))
        x1=max(0,min(size[0],max(p[0] for p in points)));y1=max(0,min(size[1],max(p[1] for p in points)))
        if x1<=x0 or y1<=y0:return None
        return [round(x0,3),round(y0,3),round(x1,3),round(y1,3)]
    except (ValueError,TypeError,OverflowError):return None


def annotate_image_graph(graph):
    graph=deepcopy(graph);metadata=graph.setdefault('image_metadata',{})
    anchors={(p['ref'],str(p['pin'])):p for p in metadata.get('pin_anchors',[])}
    actions=metadata.get('local_recovery_actions',[])+metadata.get('terminal_recovery_audit',[])+metadata.get('erc_actions',[])
    recovered={(a.get('ref'),a.get('pin')):a for a in actions if a.get('pin')}
    labels={a['text'] for a in metadata.get('external_labels',[]) if a.get('confidence',0)>=.9}
    hotspots=list(metadata.get('review_hotspots',[]))
    for net in graph.get('nets',[]):
        for node in net['nodes']:
            key=node['ref'],node['pin'];anchor=anchors.get(key);action=recovered.get(key)
            certainty=(action or anchor or {}).get('confidence',.35)
            certainty=float(max(0,min(1,certainty))) if _finite(certainty) else .35
            source=(action or anchor or {}).get('source','wire_trace')
            if source not in SOURCES:source='wire_trace'
            if action:certainty=min(certainty,.8)
            if anchor is None:certainty=min(certainty,.35)
            node.update(confidence=certainty,source=source)
            if certainty<.8 and anchor:
                hotspots.append({'ref':key[0],'pin':key[1],'bbox':[anchor['x']-12,anchor['y']-12,anchor['x']+12,anchor['y']+12],
                                 'reason':'Uncertain pin assignment; compare physical number and net with source',
                                 'confidence':certainty,'source':source})
        net['confidence']=min((p['confidence'] for p in net['nodes']),default=.35)
        net['source']=('erc_healed' if any(p['source']=='erc_healed' for p in net['nodes']) else
                       'net_label' if net['name'] in labels else
                       'vector' if all(p['source']=='vector' for p in net['nodes']) else 'wire_trace')
    exposed=[];seen=set();size=metadata.get('source_size') or [metadata.get('width'),metadata.get('height')]
    old={h.get('id'):h for h in graph.get('review_hotspots',[])}
    for raw in hotspots:
        box=source_box(raw.get('bbox'),metadata)
        if box is None:continue
        reason=str(raw.get('reason','Source review required'))[:500]
        identity=hashlib.sha256(repr((raw.get('ref'),raw.get('pin'),reason,box)).encode()).hexdigest()[:20]
        if identity in seen:continue
        seen.add(identity)
        certainty=raw.get('confidence',.4)
        if not _finite(certainty):certainty=.4
        source=raw.get('source','wire_trace')
        exposed.append({'id':identity,'bbox':box,'page':1,'source_width':size[0],'source_height':size[1],
                        'coordinate_space':'source_pixels','reason':reason,'ref':raw.get('ref'),'pin':raw.get('pin'),'net':raw.get('net'),
                        'confidence':max(0,min(1,certainty)),'source':source if source in SOURCES else 'wire_trace',
                        'reviewed':bool(old.get(identity,{}).get('reviewed',False))})
    graph['review_hotspots']=exposed
    # Inventory only observed physical IDs; never fill a package from a catalog.
    refs={c['ref'] for c in graph.get('components',[])}
    inventory={(p['ref'],str(p['pin'])):p for p in graph.get('physical_pins',[])}
    for key,anchor in anchors.items():
        if key[0] in refs and key[1].strip() and '\n' not in key[1] and '\r' not in key[1]:
            inventory.setdefault(key,{'ref':key[0],'pin':key[1],'metadata':{'observed_anchor':anchor}})
    graph['physical_pins']=list(inventory.values())
    if len(size)==2 and all(_finite(v) and v>0 for v in size):
        metadata['source_frames']=[{'page':1,'width':size[0],'height':size[1],'coordinate_space':'source_pixels'}]
    metadata['confidence_description']='Heuristic evidence score; not calibrated accuracy. Confirmation does not increase the score.'
    return graph
