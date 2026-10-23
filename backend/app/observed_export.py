"""Native exports that preserve the reviewed graph's literal observed pin IDs.

Generated symbols preserve graph data; they do not certify recognition accuracy
or reproduce the source drawing's functional symbol appearance.
"""
from collections import defaultdict
from copy import deepcopy
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


def write_kicad(graph,folder,name='observed'):
    """Write native KiCad, export actual XML with its CLI, compare every fact."""
    from .ingestion import Circuit
    graph=Circuit.model_validate(graph).model_dump()
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


def orcad_bundle(name,graph,cache_dir):
    """Capture-native exact-pin symbols, no substitutions/remaps/dropped pins."""
    from . import orcad_capture as oc
    from .ingestion import Circuit
    graph=Circuit.model_validate(graph).model_dump()
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
    expected={key:aliases[net] for key,net in observed.items()}
    safe=re.sub(r'[^A-Za-z0-9_-]','_',name)[:60] or 'observed'
    drawing=deepcopy(graph)
    for component in drawing['components']:component.pop('x',None);component.pop('y',None)
    with tempfile.TemporaryDirectory() as temporary:
        folder=Path(temporary);dsn=folder/(safe+'.DSN');library=folder/oc.GENERATED_LIB
        oc._write(root,temporary,dsn,library,drawing,resolved,generate,expected,literal_pins=True)
        dump=oc._run(root,'orcad_dump.tcl',dsn)
        parts={};pins={}
        for line in dump.splitlines():
            words=oc._tcl_list(line)
            if not words:continue
            if words[0]=='PART' and len(words)>=4:parts[words[1]]=words[3]
            elif words[0]=='PIN' and len(words)>=4 and words[3]:
                pins[words[1],words[2]]=inverse.get(words[3].upper(),words[3])
        report=compare(graph,parts,pins)
        report.update(native_readback=True,format='OrCAD Capture',symbol_mode='literal observed pin IDs',
                      net_aliases=aliases,generated_symbols=sorted(generate),corrections=[],substitutions={},implicit_power_pins=[])
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
               'verification.json':json.dumps(report,indent=2).encode(),'readback.txt':dump.encode()}
    files['manifest.json']=json.dumps({'mode':'preserve_connections','files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}},indent=2).encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for filename,data in files.items():archive.writestr(filename,data)
    return output.getvalue(),report
