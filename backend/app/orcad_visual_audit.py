"""Visual/geometry discrepancies measured independently from electrical fidelity."""
import base64
import math
from pathlib import Path
import re


def comparison_svg(graph,source,preview,title,scale):
    """Register the reopened Capture drawing beside the original source image."""
    from PIL import Image
    from .orcad_capture import _esc
    source=Path(source);size=Image.open(source).size;meta=graph.get('image_metadata',{})
    width=meta.get('width')
    if not width:return None
    (a,b,c),(d,e,f)=meta.get('source_affine',[[1,0,0],[0,1,0]])
    det=a*e-b*d
    if abs(det)<1e-12:return None
    k=width/scale
    matrix=[e/det*k,-d/det*k,-b/det*k,a/det*k,
            (b*f-e*c)/det-300*k*(e-b)/det,(d*c-a*f)/det-300*k*(a-d)/det]
    embedded=base64.b64encode(source.read_bytes()).decode()
    mime=Image.MIME.get(Image.open(source).format,'image/png')
    body=re.sub(r'^<svg[^>]*>|</svg>$','',preview.strip())
    panel=1000;height=round(panel*size[1]/size[0]);gap=20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="2020" height="{height+70}" viewBox="0 0 2020 {height+70}">'
            '<rect width="100%" height="100%" fill="white"/>'
            f'<text x="20" y="24" font-family="Arial" font-size="18">{_esc(title)} — original source</text>'
            '<text x="1040" y="24" font-family="Arial" font-size="18">Native .DSN readback, registered to source coordinates</text>'
            f'<svg x="0" y="45" width="1000" height="{height}" viewBox="0 0 {size[0]} {size[1]}">'
            f'<image href="data:{mime};base64,{embedded}" width="{size[0]}" height="{size[1]}"/></svg>'
            f'<svg x="1020" y="45" width="1000" height="{height}" viewBox="0 0 {size[0]} {size[1]}">'
            f'<g transform="matrix({" ".join(str(v) for v in matrix)})">{body}</g></svg>'
            f'<text x="20" y="{height+65}" font-family="Arial" font-size="13">Electrical agreement and source fidelity are separate checks. See visual-comparison.json and routing-audit.json.</text></svg>')


def _distance(point,segment):
    a,b=segment
    dx,dy=b[0]-a[0],b[1]-a[1]
    denominator=dx*dx+dy*dy
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/denominator)) if denominator else 0
    return math.dist(point,(a[0]+t*dx,a[1]+t*dy))


def audit(graph,page,source_layout,routing,margin=300):
    from .orcad_source_wires import candidates
    from . import orcad_capture as oc
    meta=graph.get('image_metadata',{});width=meta.get('width')
    scale=source_layout['source_scale'];factor=scale/width if width else None
    anchors={(a['ref'],str(a['pin'])):a for a in meta.get('pin_anchors',[])}
    actual={(p['base'],str(pin['number'])):(pin['hx'],pin['hy']) for p in page['parts'] for pin in p['pins']}
    pin_errors=[]
    for key,anchor in anchors.items():
        if factor is None or key not in actual:continue
        expected=(margin+factor*anchor['x'],margin+factor*anchor['y'])
        error=math.dist(expected,actual[key])
        pin_errors.append({'ref':key[0],'pin':key[1],'source_capture':expected,'actual_capture':actual[key],
                           'error_capture':error,'error_source_px':error/factor,
                           'above_grid_tolerance':error>math.sqrt(2)*5+.01})
    aliases={old:new.upper() for old,new in oc.net_aliases(graph).items()}
    paths,_=candidates(graph,scale,aliases,margin)
    source_segments=[(p['net'],a,b) for p in paths for a,b in zip(p['path'],p['path'][1:])]
    output=page['wires'];deviations=[];missing=[]
    for net,a,b in source_segments:
        points=[(a[0]+(b[0]-a[0])*i/4,a[1]+(b[1]-a[1])*i/4) for i in range(5)]
        maximum=max(min((_distance(p,(w[:2],w[2:])) for w in output),default=float('inf')) for p in points)
        row={'net':net,'a':a,'b':b,'maximum_deviation_capture':maximum}
        deviations.append(row)
        if maximum>10:missing.append(row)
    source=routing.get('source_reconstruction',{})
    library=source_layout.get('library_symbols',{})
    symbol_mismatches=[{'ref':ref,**row} for ref,row in library.items() if row.get('status')=='unresolved']
    actual_junctions={tuple(p) for p in page.get('junctions',[])}
    expected_junctions=source.get('source_junctions',[])
    missing_junctions=[j for j in expected_junctions if tuple(j['at']) not in actual_junctions]
    source_crossings=source.get('source_crossings',[])
    incorrect_crossings=[j for j in source_crossings if tuple(j['at']) in actual_junctions]
    inferred=source.get('inferred_segments',[])
    free_ends=routing.get('endpoint_verification',{})
    return {'source_faithful':not (free_ends.get('free_end_count') or missing or missing_junctions or incorrect_crossings or symbol_mismatches or
                                   source_layout.get('fallback_components') or any(p['above_grid_tolerance'] for p in pin_errors) or inferred),
            'scope':'Source geometry/appearance audit; electrical equivalence is verified separately',
            'component_source_geometry_count':len(source_layout['source_geometry_components']),
            'component_fallbacks':source_layout['fallback_components'],
            'pin_placement_errors':pin_errors,'pins_above_grid_tolerance':sum(p['above_grid_tolerance'] for p in pin_errors),
            'source_route_segments_measured':len(source_segments),'source_route_segments_missing_or_deviating':missing,
            'route_deviations':deviations,'missing_source_junctions':missing_junctions,
            'incorrect_source_crossing_junctions':incorrect_crossings,'symbol_mismatches':symbol_mismatches,
            'inferred_segments':inferred,'observed_source_edges_kept':len(source.get('accepted_edges',[])),
            'endpoint_verification':free_ends,'source_supported_gap_repairs':source.get('source_supported_gap_repairs',[]),
            'rejected_source_edges':source.get('rejected_edges',[]),
            'limitations':['Source route coverage is geometric, not proof of wire identity; see independent native netlist comparison.',
                           'Missing/ambiguous OCR observations and generated fallback symbols remain unresolved.',
                           'Grid quantization, fonts, line weights and colour can differ from the original image.']}
