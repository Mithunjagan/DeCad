"""Capture symbol geometry and placement from measured source pin/body anchors.

Only measured pin IDs are used. Missing geometry keeps the explicit generated-symbol
fallback; it is reported rather than claiming a source-faithful reconstruction.
"""
from collections import defaultdict
from copy import deepcopy
import statistics


def prepare(graph, scale=None, margin=300,*,recover_incomplete=True):
    metadata = graph.get('image_metadata', {})
    width = metadata.get('width')
    drawing = deepcopy(graph)
    if scale is None:
        height = metadata.get('character_height')
        scale = max(1200, min(12000, round(width / height * 16 / 10) * 10)) if width and height else 6000
    if not isinstance(width, (int, float)) or width <= 0:
        return drawing, {}, {'source_geometry_components': [], 'fallback_components': [c['ref'] for c in graph['components']], 'source_scale': scale}
    factor = scale / width
    snap = lambda value: int(round(value / 10)) * 10
    point = lambda x, y: (snap(margin + factor * x), snap(margin + factor * y))
    anchors = {}
    for pin in graph.get('physical_pins', []):
        anchor = pin.get('metadata', {}).get('observed_anchor')
        if anchor:
            anchors[pin['ref'], str(pin['pin'])] = anchor
    for anchor in metadata.get('pin_anchors', []):
        anchors.setdefault((anchor['ref'], str(anchor['pin'])), anchor)
    used = defaultdict(set)
    for net in graph['nets']:
        for pin in net['nodes']:
            used[pin['ref']].add(str(pin['pin']))
    definitions = {};geometry_inferences=[]
    for component in drawing['components']:
        ref = component['ref']
        observed = [anchors.get((ref, pin)) for pin in sorted(used[ref])]
        if not observed or any(not a or a.get('x') is None or a.get('y') is None for a in observed):
            continue
        prefix = ''.join(c for c in ref if c.isalpha())
        if prefix in ('P','J') and all(not a.get('body') for a in observed):
            # Scanned connector references are often distributed sheet terminals,
            # not one drawn connector body. Keep those terminals at their source
            # positions rather than adding an unrelated connector block below it.
            points = [point(a['x'],a['y']) for a in observed]
            if len(set(points)) != len(points):
                continue
            cx = snap((min(p[0] for p in points)+max(p[0] for p in points))/2)
            cy = snap((min(p[1] for p in points)+max(p[1] for p in points))/2)
            vectors,pins = [],[]
            for number,anchor,(hx,hy) in zip(sorted(used[ref]),observed,points):
                dx,dy = anchor.get('direction') or [1,0]
                if abs(dx)>=abs(dy): dx,dy = (1 if dx>=0 else -1),0
                else: dx,dy = 0,(1 if dy>=0 else -1)
                sx,sy = hx-dx*20,hy-dy*20
                # Small chevron, with a real Capture pin at the measured endpoint.
                vectors += [['LINE',sx-cx-dy*5,sy-cy+dx*5,sx-cx+dx*5,sy-cy+dy*5],
                            ['LINE',sx-cx+dy*5,sy-cy-dx*5,sx-cx+dx*5,sy-cy+dy*5]]
                pins.append([number,sx-cx,sy-cy,hx-cx,hy-cy,ref+'.'+number])
            definitions[ref] = {'vectors':vectors,'pins':pins,'body':None,'center':[cx,cy],'shape':'source ports'}
            continue
        if any(not a.get('body') for a in observed):
            if not recover_incomplete:continue
            known=[a['body'] for a in observed if a.get('body')]
            if known:
                repaired=[]
                tolerance=metadata.get('character_height',20)*3
                for anchor in observed:
                    if anchor.get('body'):repaired.append(anchor);continue
                    body=min(known,key=lambda b:max(b[0]-anchor['x'],0,anchor['x']-b[2])+max(b[1]-anchor['y'],0,anchor['y']-b[3]))
                    distance=max(body[0]-anchor['x'],0,anchor['x']-body[2])+max(body[1]-anchor['y'],0,anchor['y']-body[3])
                    if distance<=tolerance:
                        repaired.append({**anchor,'body':body})
                        geometry_inferences.append({'ref':ref,'pin':anchor['pin'],'reason':'associated terminal with same-reference source body','source_distance_px':distance})
                    else:repaired.append(anchor)
                observed=repaired
            if any(not a.get('body') for a in observed):continue
        # A lone passive observation can be attached to a nearby IC contour. It
        # cannot establish a two-terminal symbol's source geometry or orientation.
        if prefix in ('R','C','L','D','V','I','BT') and len(observed) != 2:
            continue
        # Different distant bodies under one OCR reference are ambiguous; taking their
        # median would fabricate a body halfway between two real symbols.
        bodies = [a['body'] for a in observed]
        body = [statistics.median(b[i] for b in bodies) for i in range(4)]
        if any(abs(b[i]-body[i]) > max(10, (body[2]-body[0] if i%2 == 0 else body[3]-body[1])*.2)
               for b in bodies for i in range(4)):
            # Split packages (for example two buffer sections of the same IC) have
            # several valid source bodies. Retain each section at its measured spot.
            source_pins = []
            boxes = set()
            for pin, anchor in zip(sorted(used[ref]), observed):
                a,b = point(*anchor['body'][:2]); c,d = point(*anchor['body'][2:])
                boxes.add((a,b,c,d))
                hx,hy = point(anchor['x'],anchor['y'])
                direction = anchor.get('direction')
                if direction and max(abs(v) for v in direction):
                    side = ('R' if direction[0]>0 else 'L') if abs(direction[0])>=abs(direction[1]) else ('B' if direction[1]>0 else 'T')
                else:
                    side = min(((abs(hx-a),'L'),(abs(hx-c),'R'),(abs(hy-b),'T'),(abs(hy-d),'B')))[1]
                sx,sy = (max(a,hx+20),hy) if side=='L' else (min(c,hx-20),hy) if side=='R' else (hx,max(b,hy+20)) if side=='T' else (hx,min(d,hy-20))
                source_pins.append([pin,sx,sy,hx,hy])
            if len({tuple(p[3:]) for p in source_pins}) != len(source_pins):
                continue
            cx = snap((min(p[3] for p in source_pins)+max(p[3] for p in source_pins))/2)
            cy = snap((min(p[4] for p in source_pins)+max(p[4] for p in source_pins))/2)
            definitions[ref] = {'vectors':[['BOX',a-cx,b-cy,c-cx,d-cy] for a,b,c,d in sorted(boxes)],
                                'pins':[[p[0],p[1]-cx,p[2]-cy,p[3]-cx,p[4]-cy] for p in source_pins],
                                'body':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)],
                                'shape':'split package','center':[cx,cy]}
            continue
        x0, y0 = point(*body[:2]); x1, y1 = point(*body[2:])
        if x1 <= x0 or y1 <= y0:
            continue
        pair_axis = None
        if len(observed) == 2 and prefix in ('R','C','L','D','V','I','BT'):
            pair_axis = 0 if abs(observed[0]['x']-observed[1]['x']) >= abs(observed[0]['y']-observed[1]['y']) else 1
        pins = []
        for pin, anchor in zip(sorted(used[ref]), observed):
            hx, hy = point(anchor['x'], anchor['y'])
            direction = anchor.get('direction')
            if pair_axis is not None:
                lower = anchor['x' if pair_axis == 0 else 'y'] == min(a['x' if pair_axis == 0 else 'y'] for a in observed)
                side = ('L' if lower else 'R') if pair_axis == 0 else ('T' if lower else 'B')
            elif direction and max(abs(v) for v in direction):
                side = ('R' if direction[0] > 0 else 'L') if abs(direction[0]) >= abs(direction[1]) else ('B' if direction[1] > 0 else 'T')
            else:
                side = min(((abs(hx-x0), 'L'), (abs(hx-x1), 'R'), (abs(hy-y0), 'T'), (abs(hy-y1), 'B')))[1]
            # A measured body-edge anchor can coincide with the contour. Put the other
            # pin endpoint just inside it, preserving the measured external hotspot.
            if side == 'L': sx, sy = max(x0, hx + 20), hy
            elif side == 'R': sx, sy = min(x1, hx - 20), hy
            elif side == 'T': sx, sy = hx, max(y0, hy + 20)
            else: sx, sy = hx, min(y1, hy - 20)
            pins.append([pin, sx, sy, hx, hy, side])
        # Duplicate snapped pin hotspots would short distinct physical pins. Leave that
        # component to the spaced fallback instead of changing pin identity.
        if not recover_incomplete and len({(p[3],p[4]) for p in pins})!=len(pins):continue
        occupied=set()
        for p in pins:
            original=(p[3],p[4])
            if original in occupied:
                for offset in (10,-10,20,-20,30,-30):
                    shifted=(original[0],original[1]+offset) if p[5] in ('L','R') else (original[0]+offset,original[1])
                    if shifted not in occupied:
                        if p[5] in ('L','R'):p[2]+=offset;p[4]+=offset
                        else:p[1]+=offset;p[3]+=offset
                        geometry_inferences.append({'ref':ref,'pin':p[0],'reason':'conflicting detected physical pin positions require review',
                                                    'observed_capture':original,'placed_capture':shifted})
                        break
            occupied.add((p[3],p[4]))
        cx = snap((min(p[3] for p in pins) + max(p[3] for p in pins)) / 2)
        cy = snap((min(p[4] for p in pins) + max(p[4] for p in pins)) / 2)
        vectors = []
        line = lambda a, b, c, d: vectors.append(['LINE', a-cx, b-cy, c-cx, d-cy])
        sides = [p[5] for p in pins]
        inventories = ({'1','2','3','4','5'}, {'2','3','4','6','7'}, {'1','2','3','4','8'})
        amplifier = prefix == 'U' and used[ref] in inventories and sorted(sides) == ['B','L','L','R','T']
        if amplifier:
            middle = snap((y0+y1)/2)
            line(x0,y0,x1,middle); line(x1,middle,x0,y1); line(x0,y1,x0,y0)
            for p in pins:
                if p[5] in ('T','B'):
                    edge = snap(y0+(p[3]-x0)*(middle-y0)/(x1-x0))
                    p[2] = edge if p[5] == 'T' else snap(y1-(p[3]-x0)*(y1-middle)/(x1-x0))
        elif prefix == 'C' and len(pins) == 2:
            horizontal = abs(pins[0][3]-pins[1][3]) >= abs(pins[0][4]-pins[1][4])
            if horizontal:
                lo,hi = sorted(p[3] for p in pins)
                left,right = round(lo+.4*(hi-lo)),round(lo+.6*(hi-lo))
                line(left,y0,left,y1); line(right,y0,right,y1)
                for p in pins: p[1] = left if p[3] == lo else right
            else:
                lo,hi = sorted(p[4] for p in pins)
                top,bottom = round(lo+.4*(hi-lo)),round(lo+.6*(hi-lo))
                line(x0,top,x1,top); line(x0,bottom,x1,bottom)
                for p in pins: p[2] = top if p[4] == lo else bottom
        elif prefix in ('V','I','BT'):
            vectors.append(['ELLIPSE', x0-cx,y0-cy,x1-cx,y1-cy])
            midx, midy = snap((x0+x1)/2), snap((y0+y1)/2)
            line(midx-10,midy-20,midx+10,midy-20); line(midx,midy-30,midx,midy-10)
            line(midx-10,midy+20,midx+10,midy+20)
        else:
            vectors.append(['BOX',x0-cx,y0-cy,x1-cx,y1-cy])
        definitions[ref] = {'vectors': vectors, 'body': [x0,y0,x1,y1],
                            'pins': [[p[0],p[1]-cx,p[2]-cy,p[3]-cx,p[4]-cy] for p in pins],
                            'shape': 'amplifier' if amplifier else prefix}
        definitions[ref]['center'] = [cx,cy]
    # OCR can assign the same body/stubs to a nearby false reference. Keep distinct
    # components, but do not put their physical pins at identical page coordinates.
    kept = {}
    for ref, definition in definitions.items():
        if definition['body'] is None:
            kept[ref] = definition
            continue
        x0,y0,x1,y1 = definition['body']
        overlap = False
        for other in kept.values():
            if other['body'] is None:
                continue
            a,b,c,d = other['body']
            area = max(0,min(x1,c)-max(x0,a))*max(0,min(y1,d)-max(y0,b))
            if area > .5*min((x1-x0)*(y1-y0),(c-a)*(d-b)):
                overlap = True; break
        if not overlap:
            kept[ref] = definition
    definitions = kept
    for component in drawing['components']:
        if component['ref'] in definitions:
            cx,cy = definitions[component['ref']]['center']
            component['x'] = (cx-margin)/scale
            component['y'] = (cy-margin)/scale
    return drawing, definitions, {'source_geometry_components': sorted(definitions),
                                  'inferred_pin_geometry':geometry_inferences,
                                  'source_port_components': sorted(ref for ref,d in definitions.items() if d['shape']=='source ports'),
                                  'fallback_components': sorted(c['ref'] for c in drawing['components'] if c['ref'] not in definitions),
                                  'placement': 'source coordinates on Capture grid', 'grid_tolerance': 10, 'source_scale': scale}


def verify_positions(definitions, page, tolerance=10):
    """Compare reopened native pin hotspots with the measured source layout."""
    actual = {(part['base'],str(pin['number'])):(pin['hx'],pin['hy'])
              for part in page['parts'] for pin in part['pins']}
    missing, moved = [], []
    offsets = []
    for ref, definition in definitions.items():
        cx,cy = definition['center']
        for pin in definition['pins']:
            key = (ref,str(pin[0]))
            if key not in actual:
                missing.append(key)
                continue
            x,y = actual[key]
            offset = max(abs(x-cx-pin[3]),abs(y-cy-pin[4]))
            offsets.append(offset)
            if offset > tolerance:
                moved.append(key)
    return {'passed':not (missing or moved),'checked_pins':len(offsets),
            'maximum_offset':max(offsets,default=0),'tolerance':tolerance,
            'missing_pins':missing,'moved_pins':moved}
