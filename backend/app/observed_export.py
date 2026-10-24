"""Native exports that preserve the reviewed graph's literal observed pin IDs.

Generated symbols preserve graph data; they do not certify recognition accuracy
or reproduce the source drawing's functional symbol appearance.
"""
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .engine import OperationError,Schematic,generated_symbol


def facts(graph):
    components={c['ref']:c['value'] for c in graph['components']}
    pins={(p['ref'],str(p['pin'])):n['name'] for n in graph['nets'] for p in n['nodes']}
    return components,pins


def compare(graph,components,pins):
    expected,connections=facts(graph)
    missing_parts=sorted(expected.keys()-components.keys());extra_parts=sorted(components.keys()-expected.keys())
    wrong_values=sorted((ref,expected[ref],components[ref]) for ref in expected.keys()&components.keys() if expected[ref]!=components[ref])
    missing=sorted(connections.keys()-pins.keys());extra=sorted(pins.keys()-connections.keys())
    wrong=sorted((ref,pin,connections[ref,pin],pins[ref,pin]) for ref,pin in connections.keys()&pins.keys() if connections[ref,pin]!=pins[ref,pin])
    return {'passed':not any((missing_parts,extra_parts,wrong_values,missing,extra,wrong)),
            'scope':'Complete observed graph export fidelity, not recognition accuracy',
            'components':len(components),'checked_pins':len(connections),'matched_pins':sum(pins.get(k)==v for k,v in connections.items()),
            'missing_parts':missing_parts,'extra_parts':extra_parts,'wrong_values':wrong_values,
            'missing_pins':missing,'extra_pins':extra,'wrong_pins':wrong}


def footprint_plan(graph,used,cache_dir,root):
    """Resolve footprint properties without changing literal symbols or wiring."""
    from . import orcad_capture as oc
    index=oc.library_index(Path(cache_dir)/'orcad-lib-index.tsv')
    resolved={};generated={}
    for component in graph['components']:
        ref=component['ref']
        result=oc.resolve(component,index,root,used.get(ref,()),generate=True)
        # A pinout substitute cannot establish the observed part's physical package.
        if result[2].startswith('substitute'):
            result=(oc.GENERATED_LIB,oc.generated_name(component),'generated symbol')
        resolved[ref]=result
        if result[2]=='generated symbol':generated[result[1]]=(ref,used.get(ref,set()))
    return oc.assign_footprints(graph,resolved,generated,used,cache_dir,root)


def footprint_readiness(footprints,placed,summary):
    """Footprint readback is separate from electrical graph verification."""
    missing=sorted(ref for ref in footprints if not placed.get(ref))
    mismatched=sorted(ref for ref,(name,_) in footprints.items() if name and placed.get(ref)!=name)
    review=sorted(ref for ref,(name,source) in footprints.items() if name and source not in {'component','part map','symbol library'})
    return {'footprint_properties_complete':not missing and not mismatched,
            'ready':not any((missing,mismatched,review,summary['not_in_library'])),
            'missing':missing,'readback_mismatches':mismatched,'needs_review':review,
            'not_in_library':summary['not_in_library'],'native_pcb_netlisting_verified':False,
            'scope':'Footprint properties and library availability; physical package suitability requires review'}


def write_kicad(graph,folder,name='observed'):
    """Write native KiCad, export actual XML with its CLI, compare every fact."""
    from .ingestion import Circuit
    from .catalog_pin_solver import normalize_graph
    graph=Circuit.model_validate(normalize_graph(graph)).model_dump()
    folder=Path(folder);folder.parent.mkdir(parents=True,exist_ok=True)
    Schematic.create(folder,name);schematic=Schematic(folder)
    pins=defaultdict(set)
    for net in graph['nets']:
        for pin in net['nodes']:pins[pin['ref']].add(pin['pin'])
    y=40.;row_height=0.
    for index,component in enumerate(graph['components']):
        if index and index%4==0:y+=row_height+25;row_height=0
        ref=component['ref'];definition=generated_symbol(ref,component['value'],pins[ref])
        height=max(1,(len(pins[ref])+1)//2)*2.54+8
        row_height=max(row_height,height)
        schematic.add(ref,component['value'],lib_id=definition[1],definition=definition,
                      footprint=component.get('footprint'),x=45+(index%4)*100,y=y+height/2)
    # One labeled terminal per operation prevents incidental routed crossings.
    for net in graph['nets']:
        for pin in net['nodes']:schematic.connect(net['name'],[(pin['ref'],pin['pin'])])
    schematic.save()
    xml=schematic.netlist();(folder/'readback.xml').write_text(xml,encoding='utf-8')
    root=ET.fromstring(xml)
    actual={c.attrib['ref']:c.findtext('value','') for c in root.findall('./components/comp')}
    names={n['name'] for n in graph['nets']};readback={}
    for net in root.findall('./nets/net'):
        label=net.attrib['name']
        if label not in names and label.startswith('/') and label[1:] in names:label=label[1:]
        for pin in net.findall('node'):readback[pin.attrib['ref'],pin.attrib['pin']]=label
    report=compare(graph,actual,readback)
    report.update(native_readback=True,format='KiCad',symbol_mode='literal observed pin IDs')
    (folder/'verification.json').write_text(json.dumps(report,indent=2))
    if not report['passed']:raise OperationError('Observed KiCad export did not preserve the complete graph: '+json.dumps(report))
    return report


def orcad_bundle(name,graph,cache_dir,*,source_image=None):
    """Capture-native exact-pin symbols, no substitutions/remaps/dropped pins."""
    from . import orcad_capture as oc
    from .ingestion import Circuit
    from .catalog_pin_solver import normalize_graph
    graph=Circuit.model_validate(normalize_graph(graph)).model_dump()
    from .orcad_source_raster import enrich
    routing_graph=enrich(graph,source_image)
    root=oc.orcad_root()
    if root is None:raise OperationError('OrCAD Capture is unavailable.')
    aliases={old:new.upper() for old,new in oc.net_aliases(graph).items()}
    inverse={new:old for old,new in aliases.items()}
    _,observed=facts(graph)
    used=defaultdict(set)
    for ref,pin in observed:used[ref].add(pin)
    resolved={};generate={};mapping={}
    for component in graph['components']:
        ref=component['ref'];package='OBS_'+re.sub(r'[^A-Za-z0-9_]','_',ref)
        prefix=re.match(r'[A-Za-z]+',ref)[0]
        resolved[ref]=(oc.GENERATED_LIB,package,'generated symbol')
        generate[package]=(prefix,used[ref])
        mapping[ref]={'package':package,'match':'literal observed pins','value':component['value'],
                      'footprint':component.get('footprint') or ''}
    footprints=footprint_plan(graph,used,cache_dir,root)
    for ref,(footprint,source) in footprints.items():
        mapping[ref].update(footprint=footprint,footprint_source=source)
    expected={key:aliases[net] for key,net in observed.items()}
    safe=re.sub(r'[^A-Za-z0-9_-]','_',name)[:60] or 'observed'
    from .orcad_source_layout import prepare,verify_positions
    from .orcad_source_symbols import resolve as resolve_source_symbols
    with tempfile.TemporaryDirectory() as temporary:
        folder=Path(temporary);dsn=folder/(safe+'.DSN');library=folder/oc.GENERATED_LIB
        attempts=[]
        for strategy in ('library and recovered source geometry','measured source geometry','conservative measured source geometry'):
            drawing,source_symbols,source_layout=prepare(graph,margin=oc.SOURCE_MARGIN,
                                                       recover_incomplete=strategy!='conservative measured source geometry')
            if strategy=='library and recovered source geometry':
                source_layout['library_symbols']=resolve_source_symbols(graph,source_symbols,cache_dir)
            else:
                source_layout['library_symbols']={c['ref']:{'status':'unresolved','reason':'library geometry rejected after native routing failure; reviewed pin IDs retained'} for c in graph['components']}
            try:
                oc.compress_source_spacing(drawing,source_symbols,source_layout['source_scale'])
                source_layout['spacing_policy']='rigid source-order placement with empty bands compressed to 600 mil'
                oc._write(root,temporary,dsn,library,drawing,resolved,generate,expected,footprints=footprints,literal_pins=True,wiring=True,source_symbols=source_symbols,source_scale=source_layout['source_scale'])
                routing=oc._wire(root,temporary,dsn,expected,require_wires=True,source_graph=routing_graph,source_scale=source_layout['source_scale'],source_image=source_image)
                attempts.append({'strategy':strategy,'passed':True});break
            except OperationError as error:
                if not str(error).startswith(('Visible wire routing incomplete','Saved OrCAD wires failed physical continuity')):raise
                attempts.append({'strategy':strategy,'passed':False,'error':str(error)})
                if strategy=='conservative measured source geometry':raise
                for path in folder.iterdir():
                    if path.is_file():path.unlink()
        source_layout['native_build_attempts']=attempts
        pages=oc.drawing(dsn)
        source_layout['position_verification']=verify_positions(source_symbols,pages[0])
        if not source_layout['position_verification']['passed']:
            raise OperationError('Saved OrCAD pin positions changed the measured source layout: '+json.dumps(source_layout['position_verification']))
        dump=oc._run(root,'orcad_dump.tcl',dsn)
        parts={};pins={};placed_footprints={}
        for line in dump.splitlines():
            words=oc._tcl_list(line)
            if not words:continue
            if words[0]=='PART' and len(words)>=4:
                parts[words[1]]=words[3]
                if len(words)>4 and words[4]:placed_footprints[words[1]]=words[4]
            elif words[0]=='PIN' and len(words)>=4:
                # A physical pin with no net is a distinct isolated vertex,
                # never an invented wire stub or a shared empty-name net.
                native=words[3] or f'UNCONNECTED::{words[1]}::{words[2]}'
                pins[words[1],words[2]]=inverse.get(native.upper(),native)
        # Unnamed source nets intentionally have no synthetic aliases. Match their
        # independently read physical memberships, including extra pins and shorts.
        native_groups=defaultdict(set)
        for key,native in pins.items():native_groups[native].add(key)
        expected_groups=defaultdict(set)
        for key,net in observed.items():expected_groups[net].add(key)
        canonical={};group_errors=[]
        for native,members in native_groups.items():
            matches=[net for net,wanted in expected_groups.items() if wanted==members]
            if len(matches)==1:
                canonical.update({key:matches[0] for key in members})
            else:
                group_errors.append({'native_net':native,'pins':sorted(members),'reason':'missing connection, extra pin or unintended short'})
                canonical.update({key:native for key in members})
        report=compare(graph,parts,canonical)
        report['electrical_group_errors']=group_errors
        report['native_pin_memberships']=[{'ref':ref,'pin':pin,'native_net':net} for (ref,pin),net in sorted(pins.items())]
        report['raster_geometry']=routing_graph.get('image_metadata',{}).get('export_raster_geometry')
        from .orcad_visual_audit import audit as visual_audit
        report['visual_comparison']=visual_audit(routing_graph,pages[0],source_layout,routing,oc.SOURCE_MARGIN)
        report.update(native_readback=True,format='OrCAD Capture',symbol_mode='literal observed pin IDs',routing=routing,source_layout=source_layout,
                      net_aliases=aliases,generated_symbols=sorted(generate),corrections=[],substitutions={},implicit_power_pins=[])
        report['unlabelled_loose_ends']=routing.get('unlabelled_loose_ends',0)
        report['placed_footprints']=placed_footprints
        report['footprints']=oc.footprint_summary(footprints,placed_footprints,root)
        report['pcb_readiness']=footprint_readiness(footprints,placed_footprints,report['footprints'])
        if report['pcb_readiness']['readback_mismatches']:
            raise OperationError('Saved OrCAD footprint properties differ from their assignments: '+', '.join(report['pcb_readiness']['readback_mismatches']))
        if not report['passed']:raise OperationError('Observed DSN export did not preserve the complete graph: '+json.dumps(report))
        netlist=oc.physical_netlist(dump,mapping)
        report['netlist']={'nets':len(netlist['nets']),'parts':len(netlist['parts']),
                           'connections':sum(len(n['nodes']) for n in netlist['nets']),
                           'without_footprint':[p['ref'] for p in netlist['parts'] if not p['footprint']]}
        files={safe+'.DSN':dsn.read_bytes(),oc.GENERATED_LIB:library.read_bytes(),
               safe+'.opj':oc.project_file(safe+'.DSN',[oc.GENERATED_LIB]).encode(),
               'circuit.json':json.dumps(graph,indent=2).encode(),'netlist.json':json.dumps(netlist,indent=2).encode(),
               'orcad-mapping.json':json.dumps(mapping,indent=2).encode(),
               'net-aliases.json':json.dumps(aliases,indent=2).encode(),
               'visual-comparison.json':json.dumps(report['visual_comparison'],indent=2).encode(),
               'routing-audit.json':json.dumps(routing.get('source_reconstruction',{}),indent=2).encode(),
               'capture-drawing.json':json.dumps(pages,indent=2).encode(),
               'preview.svg':oc.svg(pages,name,preserve_page=bool(source_symbols)).encode(),
               'verification.json':json.dumps(report,indent=2).encode(),'readback.txt':dump.encode()}
        for path in oc.orcad_library.footprint_files({name for name,_ in footprints.values()}):
            files['footprints/'+path.name]=path.read_bytes()
        if source_image:
            from .orcad_visual_audit import comparison_svg
            comparison=comparison_svg(graph,source_image,files['preview.svg'].decode(),name,source_layout['source_scale'])
            if comparison:files['source-versus-output.svg']=comparison.encode('utf-8')
    files['manifest.json']=json.dumps({'mode':'preserve_connections','files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}},indent=2).encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for filename,data in files.items():archive.writestr(filename,data)
    return output.getvalue(),report
