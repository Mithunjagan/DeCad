"""Read-only package constraints. Symbol rows need observed ordering evidence.

Package counter-clockwise numbering is not assumed for functionally rearranged
schematic symbols. Missing numbers need at least three agreeing visible anchors.
"""
from collections import Counter
import re

import numpy as np

from .pin_crop_recovery import reference_numbers
from .recognition_catalog import pin_tables


def normalize_graph(graph, *, tokens=None):
    """Normalize a private export copy using source evidence and catalog facts.

    No OCR or model calls. Missing geometry is never replaced with guessed wires.
    """
    from copy import deepcopy
    from .local_recovery import recover_locally, _side
    from .recognition_catalog import recover_marking
    graph=graph.model_dump() if hasattr(graph,'model_dump') else deepcopy(graph)
    if not graph.get('components'):return graph
    graph.setdefault('nets',[])
    meta=graph.setdefault('image_metadata',{}) or {}
    graph['image_metadata']=meta
    tokens=tokens if tokens is not None else meta.get('ocr_tokens',[])
    if not isinstance(tokens,(list,tuple)):tokens=[]
    from types import SimpleNamespace
    tokens=[SimpleNamespace(**t) if isinstance(t,dict) else t for t in tokens]
    heights=[l['bbox'][3]-l['bbox'][1] for l in meta.get('external_labels',[]) if l.get('bbox')]
    ch=meta.get('character_height') or (float(np.median(heights)) if heights else 1)
    claimed={c.get('value','').upper() for c in graph['components'] if c.get('value','').upper()!='UNKNOWN'}
    for component in graph['components']:
        ref=component['ref'];value=component.get('value','')
        if value.upper()!='UNKNOWN':continue
        bodies={tuple(a['body']) for a in meta.get('pin_anchors',[]) if a['ref']==ref and a.get('body')}
        options=set()
        for t in tokens:
            if t.text.upper() in claimed:continue
            if any(max(b[0]-t.x1,t.x0-b[2],b[1]-t.y1,t.y0-b[3],0)<=1.5*ch for b in bodies):
                match=recover_marking(t.text)
                if match:options.add(match)
        if len(options)==1:component['value']=options.pop();claimed.add(component['value'])
    # Graph-only observations still carry package evidence; pixel crops are optional.
    occupied={(p['ref'],str(p['pin'])) for n in graph['nets'] for p in n['nodes']}
    replacements={};ceilings={}
    for component in graph['components']:
        ref=component['ref']
        if not re.fullmatch(r'(?:U|IC)[A-Za-z0-9_]*',ref,re.I):continue
        observed=sorted({p for r,p in occupied if r==ref and p.isdigit() and 0<int(p)<=64},key=int)
        maximum=pin_ceiling(component.get('value'),observed)
        if maximum is None:continue
        ceilings[ref]=maximum
        for net in graph['nets']:
            result=[]
            for node in net['nodes']:
                text=str(node['pin'])
                if node['ref']!=ref or not text.isdigit() or int(text)<=maximum:
                    result.append(node);continue
                digits=list(text)
                split=len(digits) in (2,3) and all(0<int(d)<=maximum for d in digits) and all(a<b for a,b in zip(digits,digits[1:]))
                new=[d for d in digits if (ref,d) not in occupied] if split else []
                replacements[ref,text]=new
                for d in new:result.append({**deepcopy(node),'pin':d});occupied.add((ref,d))
                meta.setdefault('rejected_pin_observations',[]).append({'node':deepcopy(node),'net':net['name'],'split_pins':new,'reason':'Outside physical package ceiling'})
            net['nodes']=result
    for owner,field in ((graph,'physical_pins'),(meta,'pin_anchors')):
        if field not in owner:continue
        result=[]
        for p in owner[field]:
            key=p['ref'],str(p['pin'])
            if key not in replacements:result.append(p);continue
            # A fused observation has no independently observed anchor per digit.
            if field=='physical_pins':
                for d in replacements[key]:
                    item=deepcopy(p);item['pin']=d
                    item.get('metadata',{}).pop('td9_attributes',None);result.append(item)
        owner[field]=result
    graph=recover_locally(graph)
    meta=graph['image_metadata'];rejected=set()
    for component in graph['components']:
        maximum=pin_ceiling(component.get('value'))
        if maximum is None:continue
        for net in graph['nets']:
            for p in net['nodes']:
                if p['ref']==component['ref'] and str(p['pin']).isdigit() and not 1<=int(p['pin'])<=maximum:
                    rejected.add((p['ref'],str(p['pin'])))
    for net in graph['nets']:
        removed=[p for p in net['nodes'] if (p['ref'],str(p['pin'])) in rejected]
        for p in removed:meta.setdefault('rejected_pin_observations',[]).append({'node':deepcopy(p),'net':net['name'],'reason':'Outside catalog pin ceiling'})
        net['nodes']=[p for p in net['nodes'] if (p['ref'],str(p['pin'])) not in rejected]
    for owner,field in ((graph,'physical_pins'),(meta,'pin_anchors')):
        if field in owner:owner[field]=[p for p in owner[field] if (p['ref'],str(p['pin'])) not in rejected]
    # Existing named nets also need token ownership checks, not only new labels.
    anchors=meta.get('pin_anchors',[]);detached=[]
    for net in graph['nets']:
        if net['name'].upper() in {'VCC','VDD','VSS','VEE','GND','AGND','DGND'}:continue
        labels=[l for l in meta.get('external_labels',[]) if l.get('text','').upper()==net['name'].upper() and l.get('bbox')]
        for t in tokens:
            text=t.text.upper();name=net['name'].upper();prefix=text[:-len(name)] if name and text.endswith(name) else None
            if prefix=='' or prefix is not None and prefix.isdigit():
                box=[t.x0,t.y0,t.x1,t.y1];vertical=getattr(t,'vertical',False)
                if prefix:
                    if vertical:box[3]-=(t.y1-t.y0)*len(prefix)/len(text)
                    else:box[0]+=(t.x1-t.x0)*len(prefix)/len(text)
                labels.append({'text':name,'bbox':box,'vertical':vertical})
        labels=list({tuple(l['bbox']):l for l in labels}.values())
        if not labels:continue
        for node in list(net['nodes']):
            anchor=next((a for a in anchors if a['ref']==node['ref'] and str(a['pin'])==str(node['pin'])),None)
            if anchor is None:continue
            peers=[a for a in anchors if a['ref']==anchor['ref'] and a.get('body')==anchor.get('body') and _side(a)==_side(anchor)]
            horizontal=abs(anchor.get('direction',[1,0])[0])>=abs(anchor.get('direction',[1,0])[1])
            def nearby(label,a):
                b=label['bbox']
                return max(b[0]-a['x'],a['x']-b[2],b[1]-a['y'],a['y']-b[3],0)<=6*ch
            local=[l for l in labels if nearby(l,anchor) and horizontal!=bool(l.get('vertical'))]
            if len(local)!=1:continue
            label=local[0];box=label['bbox']
            def distance(a):return abs(a['y']-box[3]) if horizontal else abs(a['x']-box[2])
            owners=[a for a in peers if nearby(label,a)]
            if not owners:continue
            nearest=min(owners,key=distance)
            if not any(p['ref']==nearest['ref'] and str(p['pin'])==str(nearest['pin']) for p in net['nodes']):continue
            if str(anchor['pin']).isdigit() and str(nearest['pin']).isdigit() and abs(int(anchor['pin'])-int(nearest['pin']))!=1:continue
            connected=anchor.get('physical_net') is not None and anchor.get('physical_net')==nearest.get('physical_net')
            if not connected and distance(nearest)+1e-6<distance(anchor):
                net['nodes'].remove(node);detached.append(node)
                meta.setdefault('normalization_actions',[]).append({'kind':'exclusive_label_owner','node':deepcopy(node),'old_net':net['name']})
    occupied={n['name'] for n in graph['nets']}
    for node in detached:
        index=1
        while f'N_UNCLAIMED_{index}' in occupied:index+=1
        name=f'N_UNCLAIMED_{index}';occupied.add(name);graph['nets'].append({'name':name,'nodes':[node]})
    graph['nets']=[n for n in graph['nets'] if n['nodes']]
    return graph


def row_grammar(pins):
    established={p for p in pins if re.fullmatch(r'[A-Z][1-9]\d?',str(p))}
    if len(established)<3:return {}
    rows={p[0] for p in established};maximum=max(int(p[1:]) for p in established)
    result={}
    for pin in pins:
        match=re.fullmatch(r'([8015])(\d{1,2})',str(pin))
        if not match or not 1<=int(match[2])<=maximum:continue
        candidates=set({'8':'B','0':'DO','1':'I','5':'S'}[match[1]])&rows
        if len(candidates)==1:result[pin]=candidates.pop()+str(int(match[2]))
    return result


def pin_ceiling(value, observed=(), side_count=0):
    tables=pin_tables(value or '')
    pins={str(p) for t in tables for p in t['pins']}
    numeric={int(p) for p in pins if p.isdigit()}
    if numeric and len(numeric)==len(pins):return max(numeric)
    # Unknown packages need three monotonic, plausible side observations.
    small=[int(p) for p in observed if str(p).isdigit() and 0<int(p)<=64]
    if len(small)<3 or not (all(a<b for a,b in zip(small,small[1:])) or all(a>b for a,b in zip(small,small[1:]))):return None
    needed=max(max(small),2*side_count)
    return next((n for n in (8,14,16,20,24,28,32,40,44,48,64) if n>=needed),None)


def split_stacked_digits(text,count,ceiling):
    """Unique literal partition only; never manufacture missing digits."""
    def partitions(rest,k):
        if k==0:
            if not rest:yield ()
            return
        for size in range(1,len(rest)-k+2):
            head=rest[:size]
            if head.startswith('0') or not 1<=int(head)<=ceiling:continue
            for tail in partitions(rest[size:],k-1):yield (head,)+tail
    if not text.isdigit() or count<2 or count>len(text):return None
    choices={p for p in partitions(text,count) if all(int(a)<int(b) for a,b in zip(p,p[1:])) or all(int(a)>int(b) for a,b in zip(p,p[1:]))}
    return next(iter(choices)) if len(choices)==1 else None


def constrain_reads(rows,reads,components,ch,tokens=(),edge_pins=()):
    changes=[];positions={r[0]:(r[2],r[3]) for r in edge_pins}
    for ref in components:
        keys={key for group in rows.values() for key,owner,_ in group if owner==ref}
        replacements=row_grammar({reads[k][0] for k in keys if reads[k][0]})
        occupied={reads[k][0] for k in keys}
        for k in keys:
            old=reads[k][0];new=replacements.get(old)
            if new and new not in occupied:reads[k]=(new,reads[k][1]);occupied.add(new);changes.append((ref,old,new))
    for group in rows.values():
        group=sorted(group,key=lambda r:r[2]);ref=group[0][1]
        maximum=pin_ceiling(components.get(ref),[reads[k][0] for k,_,_ in group],len(group))
        if maximum is None:continue
        for token in tokens:
            text=token.text.strip()
            if not text.isdigit() or int(text)<=maximum:continue
            selected=[]
            for key,_,_ in group:
                if key not in positions:continue
                x,y=positions[key]
                if token.x0-1.5*ch<=x<=token.x1+1.5*ch and token.y0-.25*ch<=y<=token.y1+.25*ch:selected.append(key)
            split=split_stacked_digits(text,len(selected),maximum)
            if split and all(reads[k][0] in (None,'',text,p) for k,p in zip(selected,split)):
                occupied={reads[k][0] for other in rows.values() for k,r,_ in other if r==ref and k not in selected}
                if not occupied.intersection(split):
                    for k,p in zip(selected,split):
                        old=reads[k][0];reads[k]=(p,reads[k][1]);changes.append((ref,old,p))
        for key,_,_ in group:
            old=reads[key][0]
            if old and old.isdigit() and not 1<=int(old)<=maximum:
                reads[key]=(None,reads[key][1]);changes.append((ref,old,None))
    return changes


def exclusive_strip_labels(edge_pins,reads,tokens,ch):
    """Each printed token belongs to its closest parallel terminal axis."""
    for key,wire,x,y,ux,uy,ref in edge_pins:
        pin,labels=reads[key]
        if not labels:continue
        kept=[]
        for label in labels:
            matches=[t for t in tokens if t.text.upper().strip()==label.upper().strip()]
            if not matches:kept.append(label);continue
            peers=[r for r in edge_pins if r[6]==ref and round(r[4])==round(ux) and round(r[5])==round(uy)]
            horizontal=abs(ux)>=abs(uy)
            def distance(t,r):
                return min(abs(r[3]-t.y0),abs(r[3]-t.y1)) if horizontal else min(abs(r[2]-t.x0),abs(r[2]-t.x1))
            if any(distance(t,(key,wire,x,y,ux,uy,ref))<=min(distance(t,r) for r in peers)+1e-6 and sum(distance(t,r)<=distance(t,(key,wire,x,y,ux,uy,ref))+1e-6 for r in peers)==1 for t in matches):kept.append(label)
        reads[key]=(pin,kept or None)


def recover_sequences(rows,reads,components,ch,*,numbers=reference_numbers):
    proposals=[]
    counts=Counter((ref,reads[key][0]) for row in rows.values() for key,ref,_ in row if reads[key][0])
    known={ref:{pin for owner,pin in counts if owner==ref} for ref in components}
    for group in rows.values():
        group=sorted(group,key=lambda row:row[2])
        if len(group)<4:continue
        ref=group[0][1];allowed=numbers(components.get(ref))
        if not allowed:continue
        gaps=[b[2]-a[2] for a,b in zip(group,group[1:]) if b[2]-a[2]>.5*ch]
        if not gaps:continue
        pitch=float(np.median(gaps));slots=[round((position-group[0][2])/pitch) for _,_,position in group]
        if len(set(slots))!=len(slots):continue
        observed=[reads[key][0] for key,_,_ in group]
        hypotheses=set()
        for slot,pin in zip(slots,observed):
            if pin not in allowed or not pin.isdigit():continue
            for step in (-2,-1,1,2):hypotheses.add((int(pin)-slot*step,step))
        fits=[]
        for start,step in hypotheses:
            prediction=[str(start+slot*step) for slot in slots]
            if not set(prediction)<=allowed:continue
            anchors=sum(pin==candidate and pin in allowed for pin,candidate in zip(observed,prediction))
            # A unique, in-range reading is source evidence, even when a
            # package's physical numbering order suggests something else.
            conflict=any(pin in allowed and counts[ref,pin]==1 and pin!=candidate for pin,candidate in zip(observed,prediction))
            if anchors>=3 and not conflict:fits.append((anchors,tuple(prediction)))
        if not fits:continue
        best=max(n for n,_ in fits);solutions={prediction for n,prediction in fits if n==best}
        if len(solutions)!=1:continue
        for (key,_,_),old,new in zip(group,observed,solutions.pop()):
            if old==new or new in known.get(ref,set()):continue
            if old in allowed and counts[ref,old]==1:continue
            proposals.append((key,ref,old,new))
    destinations=Counter((ref,new) for _,ref,_,new in proposals)
    accepted=[]
    for key,ref,old,new in proposals:
        if destinations[ref,new]!=1:continue
        reads[key]=(new,reads[key][1]);accepted.append((ref,old,new))
    return accepted


def component_crop_pins(reader,page,anchors,components,edge_pins,reads,ch):
    """VLM observations can fill missing numbers only with local/package support.

    Ordered crop pins are mapped only when a side's complete stub count agrees,
    and at least two already-read numbers corroborate that exact orientation.
    The model never supplies external net labels or wire connectivity.
    """
    fixes=[]
    for ref,_,_,box in anchors:
        if box is None or not re.fullmatch(r'(U|IC)\d+[A-H]?',ref):continue
        stubs=[row for row in edge_pins if row[6]==ref and box[0]-.6*ch<=row[2]<=box[2]+.6*ch and box[1]-.6*ch<=row[3]<=box[3]+.6*ch]
        if not stubs or all(reads[row[0]][0] for row in stubs):continue
        answer=reader.query(page.gray,box,'component',margin=48)
        if answer is None or answer.ref_des!=ref:continue
        tables=pin_tables(answer.part_name)
        sets={frozenset(table['pins']) for table in tables if table['pins']}
        if len(sets)!=1:continue
        allowed=sets.pop()
        existing=components.get(ref,'UNKNOWN')
        if existing not in ('','UNKNOWN') and existing.upper()!=answer.part_name.upper():continue
        if not {pin.pin_number for pin in answer.pins}<=allowed:continue
        for pin in answer.pins:
            page.internal_pin_labels.append({'ref':ref,'pin':pin.pin_number,'text':pin.internal_label,
                'side':pin.side,'bbox':list(box),'role':'internal_pin_label'})
        if existing in ('','UNKNOWN'):components[ref]=answer.part_name
        for side in ('left','right','top','bottom'):
            axis=1 if side in ('left','right') else 0
            def belongs(row):
                _,_,x,y,ux,uy,_=row
                return ('left' if ux>0 else 'right')==side if abs(ux)>=abs(uy) else ('top' if uy>0 else 'bottom')==side
            group=sorted([row for row in stubs if belongs(row)],key=lambda row:row[3] if axis else row[2])
            proposed=[pin.pin_number for pin in answer.pins if pin.side==side]
            if len(group)!=len(proposed) or len(group)<3:continue
            candidates=[]
            for ordering in (proposed,list(reversed(proposed))):
                agreements=sum(reads[row[0]][0]==pin for row,pin in zip(group,ordering))
                conflicts=any(reads[row[0]][0] not in (None,'',pin) for row,pin in zip(group,ordering))
                if agreements>=2 and not conflicts:candidates.append(tuple(ordering))
            if len(set(candidates))!=1:continue
            occupied={reads[row[0]][0] for row in edge_pins if row[6]==ref and reads[row[0]][0]}
            for row,pin in zip(group,candidates[0]):
                if reads[row[0]][0] or pin in occupied:continue
                reads[row[0]]=(pin,reads[row[0]][1]);occupied.add(pin);fixes.append((ref,None,pin))
    return fixes
