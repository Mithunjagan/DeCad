"""Read real Capture library geometry; adapt it only with unchanged physical IDs."""
import json
import math
from pathlib import Path


def library_shapes(wanted,cache_dir):
    from . import orcad_capture as oc
    cache=Path(cache_dir)/'orcad-source-symbols.json'
    known=json.loads(cache.read_text()) if cache.is_file() else {}
    missing=[pair for pair in sorted(set(wanted)) if '|'.join(pair) not in known]
    if missing:
        output=oc._run(oc.orcad_root(),'orcad_render.tcl','--library',*[p for pair in missing for p in pair])
        current=None
        for line in output.splitlines():
            words=oc._tcl_list(line)
            if not words:continue
            if words[0]=='SYMBOL':
                key='|'.join(words[1:3]);current={'section':int(words[3]),'vectors':[],'pins':{}}
                known.setdefault(key,[]).append(current)
            elif current is not None and words[0]=='V':current['vectors'].append([words[1],*[int(v) for v in words[2:]]])
            elif current is not None and words[0]=='SYMBOLPIN':
                current['pins'][words[1]]={'name':words[2],'hotspot':[int(v) for v in words[3:5]],'start':[int(v) for v in words[5:7]]}
        for pair in missing:known.setdefault('|'.join(pair),[])
        cache.parent.mkdir(parents=True,exist_ok=True)
        cache.write_text(json.dumps(known,indent=2))
    return {pair:known['|'.join(pair)] for pair in wanted}


def line_vectors(vectors):
    result=[]
    for vector in vectors:
        kind,n=vector[0],vector[1:]
        if kind in ('LINE','BOX'):
            result.append(vector);continue
        if kind=='POLY':
            points=list(zip(n[1::2],n[2::2]))
            if n[0] and points:points.append(points[0])
        elif kind in ('ELLIPSE','ARC'):
            x0,y0,x1,y1=n[:4];cx,cy=(x0+x1)/2,(y0+y1)/2;rx,ry=abs(x1-x0)/2,abs(y1-y0)/2
            start,delta=0,2*math.pi
            if kind=='ARC' and rx and ry:
                start=math.atan2((n[5]-cy)/ry,(n[4]-cx)/rx)
                end=math.atan2((n[7]-cy)/ry,(n[6]-cx)/rx)
                delta=-((start-end)%(2*math.pi)) or -2*math.pi
            count=max(12,round(abs(delta)*8))
            points=[(cx+rx*math.cos(start+delta*i/count),cy+ry*math.sin(start+delta*i/count)) for i in range(count+1)]
        else:continue
        result.extend(['LINE',*a,*b] for a,b in zip(points,points[1:]))
    return result


def fit(section,definition):
    """Fit rotation/mirror and axis scale to measured physical pin hotspots."""
    target={str(p[0]):p[3:5] for p in definition['pins']}
    if not target.keys()<=section['pins'].keys() or len(target)<2:
        return None
    best=None
    for mirror in (False,True):
        for rotation in range(4):
            def orient(x,y):
                if mirror:x=-x
                for _ in range(rotation):x,y=y,-x
                return x,y
            original=[orient(*section['pins'][pin]['hotspot']) for pin in target]
            wanted=list(target.values());parameters=[]
            for axis in (0,1):
                xs=[p[axis] for p in original];ys=[p[axis] for p in wanted]
                xm,ym=sum(xs)/len(xs),sum(ys)/len(ys)
                variance=sum((x-xm)**2 for x in xs)
                scale=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/variance if variance else None
                parameters.append((scale,xm,ym))
            valid=[p[0] for p in parameters if p[0] is not None]
            if not valid or min(valid)<=0:continue
            replacement=sum(valid)/len(valid)
            def transform(x,y):
                xy=orient(x,y)
                return tuple(round((parameters[i][0] or replacement)*(xy[i]-parameters[i][1])+parameters[i][2]) for i in (0,1))
            error=max(math.dist(transform(*section['pins'][pin]['hotspot']),target[pin]) for pin in target)
            # The pin's incoming side must also agree; fitting positions alone can
            # disguise an incompatible op-amp output/supply pin mapping.
            directions=True
            for p in definition['pins']:
                expected=(p[3]-p[1],p[4]-p[2]);src=section['pins'][str(p[0])]
                a,b=transform(*src['hotspot']),transform(*src['start'])
                actual=(a[0]-b[0],a[1]-b[1])
                if sum(e*v for e,v in zip(expected,actual))<=0:directions=False;break
            if not directions:continue
            if best is None or error<best['error']:
                vectors=[]
                for v in line_vectors(section['vectors']):
                    a,b=transform(*v[1:3]),transform(*v[3:5])
                    if a!=b:vectors.append([v[0],*a,*b])
                pins=[]
                for p in definition['pins']:
                    start=transform(*section['pins'][str(p[0])]['start'])
                    pins.append([p[0],*start,*p[3:5],section['pins'][str(p[0])].get('name',p[0])])
                best={'error':error,'rotation_quarters':rotation,'mirror':mirror,'vectors':vectors,'pins':pins,'section':section['section']}
    return best


def resolve(graph,definitions,cache_dir):
    from . import orcad_capture as oc
    # Reuse the installed library index, never a value/substitute pin remapper.
    index=oc.library_index(Path(__file__).resolve().parents[1]/'.state/orcad-lib-index.tsv')
    choices={};report={}
    for c in graph['components']:
        ref=c['ref'];value=c['value'].upper().strip()
        if value in index:package=value;library=oc._pick(index[value])
        else:
            generic=oc.GENERIC.get(oc.kicad_symbol(c) or '')
            package=generic[1] if generic else None
            library=oc._in_lib(index,*generic) if generic else None
        if not library:
            report[ref]={'status':'unresolved','reason':'no exact part or compatible generic library symbol; no electrical substitution'};continue
        choices[ref]=(library,package)
    shapes=library_shapes(list(choices.values()),cache_dir)
    for ref,pair in choices.items():
        definition=definitions.get(ref);sections=shapes[pair]
        used={p['pin'] for n in graph['nets'] for p in n['nodes'] if p['ref']==ref}
        inventory={pin for section in sections for pin in section['pins']}
        row={'library':pair[0],'package':pair[1],'physical_pin_mapping':{p:p for p in sorted(used)},
             'unavailable_physical_pins':sorted(used-inventory)}
        report[ref]=row
        if used-inventory:
            row.update(status='unresolved',reason='reviewed physical pin IDs absent from library; observations retained');continue
        if not definition or definition['shape'] in ('split package','source ports'):
            row.update(status='unresolved',reason='no single reliable source body for library geometry fit');continue
        fits=[f for section in sections if (f:=fit(section,definition))]
        match=min(fits,key=lambda f:f['error']) if fits else None
        tolerance=max(10,graph.get('image_metadata',{}).get('character_height',20)*graph.get('image_metadata',{}).get('source_export_scale',6000)/max(1,graph.get('image_metadata',{}).get('width',6000))*.8)
        if not match or match['error']>tolerance:
            row.update(status='unresolved',reason='library terminal directions or positions do not match observed physical identities',fit_error=match['error'] if match else None);continue
        # Keep source IEC rectangular resistors rather than replacing them with a
        # different visual convention. Pin identities were still validated above.
        if definition['shape']=='R':
            row.update(status='pin_inventory_verified',reason='retained source rectangular resistor convention');continue
        definition['vectors']=match['vectors'];definition['pins']=match['pins']
        row.update(status='library_geometry_adapted',rotation_quarters=match['rotation_quarters'],mirror=match['mirror'],
                   section=match['section'],maximum_pin_fit_error=match['error'],
                   note='design-local editable copy of library graphics fitted to measured source terminals; physical IDs unchanged')
    return report
