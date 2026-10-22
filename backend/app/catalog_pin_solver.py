"""Read-only package constraints. Symbol rows need observed ordering evidence.

Package counter-clockwise numbering is not assumed for functionally rearranged
schematic symbols. Missing numbers need at least three agreeing visible anchors.
"""
from collections import Counter
import re

import numpy as np

from .pin_crop_recovery import reference_numbers
from .recognition_catalog import pin_tables


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
