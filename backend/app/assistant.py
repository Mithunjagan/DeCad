"""Explicit command execution with transactional edits and post-edit native ERC."""
from __future__ import annotations
import asyncio
import json
import os
import re
import time
from pathlib import Path
import httpx
from .engine import OperationError, Schematic, atomic_text, project_lock
from .ingestion import Circuit, Component, Net, Node, REF, VALUE, ingest, parse_json, parse_spice, parse_text

HELP='Commands: add R1 10k; change R1 to 4.7k; remove R1; connect net GND to R1 pin 2; connect R1 pin 2 to C1 pin 1; create voltage divider; create RC lowpass; run ERC; undo; redo. Import SPICE, circuit JSON, PDF/DOCX text, or images with the local vision model.'


def remember(project, before, label):
    folder=project/'.history';folder.mkdir(exist_ok=True)
    atomic_text(folder/f'{time.time_ns()}.kicad_sch',before)
    files=sorted(folder.glob('*.kicad_sch'))
    for f in files[:-50]:f.unlink()
    redo=project/'.redo'
    if redo.exists():
        for f in redo.glob('*.kicad_sch'):f.unlink()


def undo_redo(project,redo=False):
    source=project/('.redo' if redo else '.history');dest=project/('.history' if redo else '.redo')
    snapshots=sorted(source.glob('*.kicad_sch'))
    if not snapshots:raise OperationError('Nothing to redo.' if redo else 'Nothing to undo.')
    sch=Schematic(project);dest.mkdir(exist_ok=True)
    atomic_text(dest/f'{time.time_ns()}.kicad_sch',sch.path.read_text())
    atomic_text(sch.path,snapshots[-1].read_text());snapshots[-1].unlink()
    return [{'action':'redo' if redo else 'undo'}]


def apply_circuit(sch,circuit):
    edits=[]
    pins={}
    for n in circuit.nets:
        for p in n.nodes:pins.setdefault(p.ref,set()).add(str(p.pin))
    for c in circuit.components:
        if sch.get(c.ref):raise OperationError(f'Import conflicts with existing {c.ref}. Use a new project or rename references.')
        edits.append(sch.add(c.ref,c.value,c.library,c.footprint,pins=pins.get(c.ref)))
    for n in circuit.nets:edits.extend(sch.connect(n.name,[(p.ref,p.pin) for p in n.nodes]))
    return edits


def template(kind, **kwargs):
    vin = kwargs.get('vin', '5')
    r1 = kwargs.get('r1', '10k')
    r2 = kwargs.get('r2', '10k')
    c1 = kwargs.get('c1', '100nF')
    
    if kind == 'divider':
        return Circuit(components=[
            Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
            Component(ref='R1', value=r1, library='Device:R'),
            Component(ref='R2', value=r2, library='Device:R')
        ], nets=[
            Net(name='VIN', nodes=[Node(ref='V1', pin='1'), Node(ref='R1', pin='1')]),
            Net(name='VOUT', nodes=[Node(ref='R1', pin='2'), Node(ref='R2', pin='1')]),
            Net(name='GND', nodes=[Node(ref='R2', pin='2'), Node(ref='V1', pin='2')])
        ])
    
    if kind == 'rc' or kind == 'rc_lowpass':
        return Circuit(components=[
            Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
            Component(ref='R1', value=r1, library='Device:R'),
            Component(ref='C1', value=c1, library='Device:C')
        ], nets=[
            Net(name='VIN', nodes=[Node(ref='V1', pin='1'), Node(ref='R1', pin='1')]),
            Net(name='VOUT', nodes=[Node(ref='R1', pin='2'), Node(ref='C1', pin='1')]),
            Net(name='GND', nodes=[Node(ref='C1', pin='2'), Node(ref='V1', pin='2')])
        ])
        
    if kind == 'rc_highpass':
        return Circuit(components=[
            Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
            Component(ref='C1', value=c1, library='Device:C'),
            Component(ref='R1', value=r1, library='Device:R')
        ], nets=[
            Net(name='VIN', nodes=[Node(ref='V1', pin='1'), Node(ref='C1', pin='1')]),
            Net(name='VOUT', nodes=[Node(ref='C1', pin='2'), Node(ref='R1', pin='1')]),
            Net(name='GND', nodes=[Node(ref='R1', pin='2'), Node(ref='V1', pin='2')])
        ])

    if kind == 'opamp' or kind == 'inverting_amp':
        rf = kwargs.get('rf', kwargs.get('r2', '100k'))
        rin = kwargs.get('rin', kwargs.get('r1', '10k'))
        return Circuit(components=[
            Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
            Component(ref='R1', value=rin, library='Device:R'),
            Component(ref='R2', value=rf, library='Device:R'),
            Component(ref='U1', value='LM741', library='Amplifier_Operational:LM741')
        ], nets=[
            Net(name='VIN', nodes=[Node(ref='V1', pin='1'), Node(ref='R1', pin='1')]),
            Net(name='IN_NEG', nodes=[Node(ref='R1', pin='2'), Node(ref='U1', pin='2'), Node(ref='R2', pin='1')]),
            Net(name='GND', nodes=[Node(ref='V1', pin='2'), Node(ref='U1', pin='3')]),
            Net(name='VOUT', nodes=[Node(ref='U1', pin='6'), Node(ref='R2', pin='2')])
        ])

    if kind == 'rectifier' or kind == 'bridge_rectifier':
        return Circuit(components=[
            Component(ref='V1', value='12V', library='Simulation_SPICE:VSIN'),
            Component(ref='D1', value='1N4007', library='Device:D'),
            Component(ref='D2', value='1N4007', library='Device:D'),
            Component(ref='D3', value='1N4007', library='Device:D'),
            Component(ref='D4', value='1N4007', library='Device:D'),
            Component(ref='C1', value='470uF', library='Device:C_Polarized'),
            Component(ref='R1', value='1k', library='Device:R')
        ], nets=[
            Net(name='AC1', nodes=[Node(ref='V1', pin='1'), Node(ref='D1', pin='2'), Node(ref='D2', pin='1')]),
            Net(name='AC2', nodes=[Node(ref='V1', pin='2'), Node(ref='D3', pin='2'), Node(ref='D4', pin='1')]),
            Net(name='VDC_POS', nodes=[Node(ref='D1', pin='1'), Node(ref='D3', pin='1'), Node(ref='C1', pin='1'), Node(ref='R1', pin='1')]),
            Net(name='GND', nodes=[Node(ref='D2', pin='2'), Node(ref='D4', pin='2'), Node(ref='C1', pin='2'), Node(ref='R1', pin='2')])
        ])

    if kind == 'timer_555' or kind == '555':
        return Circuit(components=[
            Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
            Component(ref='U1', value='NE555P', library='Timer:NE555P'),
            Component(ref='R1', value='10k', library='Device:R'),
            Component(ref='R2', value='47k', library='Device:R'),
            Component(ref='C1', value='10uF', library='Device:C_Polarized'),
            Component(ref='C2', value='10nF', library='Device:C')
        ], nets=[
            Net(name='VCC', nodes=[Node(ref='V1', pin='1'), Node(ref='U1', pin='8'), Node(ref='U1', pin='4'), Node(ref='R1', pin='1')]),
            Net(name='DISCHARGE', nodes=[Node(ref='R1', pin='2'), Node(ref='R2', pin='1'), Node(ref='U1', pin='7')]),
            Net(name='TRIGGER_THRESH', nodes=[Node(ref='R2', pin='2'), Node(ref='U1', pin='6'), Node(ref='U1', pin='2'), Node(ref='C1', pin='1')]),
            Net(name='VOUT', nodes=[Node(ref='U1', pin='3')]),
            Net(name='CONT', nodes=[Node(ref='U1', pin='5'), Node(ref='C2', pin='1')]),
            Net(name='GND', nodes=[Node(ref='V1', pin='2'), Node(ref='U1', pin='1'), Node(ref='C1', pin='2'), Node(ref='C2', pin='2')])
        ])

    if kind == 'transceiver' or kind == 'buffer_bus' or kind == '74ls244':
        return Circuit(components=[
            Component(ref='U1', value='74LS244', library='74xx:74LS244'),
            Component(ref='U2', value='74LS244', library='74xx:74LS244'),
            Component(ref='R1', value='4.7k', library='Device:R'),
            Component(ref='C1', value='100nF', library='Device:C')
        ], nets=[
            Net(name='VCC', nodes=[Node(ref='U1', pin='20'), Node(ref='U2', pin='20'), Node(ref='R1', pin='1'), Node(ref='C1', pin='1')]),
            Net(name='GND', nodes=[Node(ref='U1', pin='10'), Node(ref='U2', pin='10'), Node(ref='C1', pin='2')]),
            Net(name='OE_BUS', nodes=[Node(ref='U1', pin='1'), Node(ref='U1', pin='19'), Node(ref='R1', pin='2')])
        ])

    return Circuit(components=[
        Component(ref='V1', value=vin, library='Simulation_SPICE:VDC'),
        Component(ref='R1', value=r1, library='Device:R'),
        Component(ref='C1', value=c1, library='Device:C')
    ], nets=[
        Net(name='VIN', nodes=[Node(ref='V1', pin='1'), Node(ref='R1', pin='1')]),
        Net(name='VOUT', nodes=[Node(ref='R1', pin='2'), Node(ref='C1', pin='1')]),
        Net(name='GND', nodes=[Node(ref='C1', pin='2'), Node(ref='V1', pin='2')])
    ])


async def explanation(message):
    p=message.lower()
    if 'divider' in p:return 'For an unloaded divider, Vout = Vin × R2 / (R1 + R2). R1 connects VIN to VOUT; R2 connects VOUT to GND. Loading changes that ratio.'
    if 'lowpass' in p or 'rc filter' in p:return 'For an RC low-pass, R connects VIN to VOUT and C connects VOUT to GND. Cutoff frequency is 1 / (2πRC).'
    if 'erc' in p:return 'ERC checks native KiCad connectivity and electrical pin rules after changes. A clean ERC report does not establish equivalence to an uploaded source.'
    if os.getenv('CHAT_MODEL'):
        from .model_runtime import call
        return (await call('explanation',message))['content']
    return HELP


async def execute(message,project,attachment_paths=None,before_mutation=None,recognition_mode=None):
    text=message.strip();lower=re.sub(r'low[\s-]+pass','lowpass',text.lower());circuit=None;directives=[];warnings=[]
    if not text:raise OperationError('Enter a command.')
    read_only=bool(re.match(r'^(help|what\b|explain\b|how\b)',lower))
    if read_only and not attachment_paths:
        return {'reply':await explanation(text),'route':'explanation','edits':[]}
    if not project:raise OperationError('Choose a project first.')
    if attachment_paths:
        circuits=[]
        for path in attachment_paths:
            c,d=await ingest(path,recognition_mode=recognition_mode) if recognition_mode else await ingest(path);circuits.append(c);directives.extend(d)
        circuit=Circuit(components=[c for g in circuits for c in g.components],nets=[n for g in circuits for n in g.nets],warnings=[w for g in circuits for w in g.warnings])
        # Vision imports produce a reviewable proposal, not an unreviewed mutation.
        if circuit.warnings:
            return {'reply':'Review the extracted component/pin/net graph before applying it. '+ ' '.join(circuit.warnings),'route':'import_review','proposal':circuit.model_dump(),'edits':[]}
    elif re.search(r'\b(analy[sz]e|generate|synthesi[sz]e)\b',lower) and re.search(r'\b(uploaded|attached|file)\b',lower):
        raise OperationError('Attach a schematic PDF/image, SPICE netlist or circuit JSON using the paperclip or Import circuit source. No file was attached to this request.')
    elif text.startswith('{'):circuit=parse_json(text)
    elif re.search(r'^\s*[RCLVI]\d+\s+\S+\s+\S+\s+\S+',text,re.M) and '\n' in text:circuit,directives=parse_spice(text)
    elif (re.search(r'\b(?:voltage\s+)?divider\b',lower) or 'lowpass' in lower or 'highpass' in lower or 'opamp' in lower or 'inverting' in lower or 'rectifier' in lower or '555' in lower or 'timer' in lower or 'transceiver' in lower or '74ls244' in lower) and not re.match(r'^(remove|delete|connect|change|set|replace)\b',lower):
        try:values={c.ref:c.value for c in parse_text(text).components}
        except OperationError:values={}
        kind = ('divider' if 'divider' in lower
                else 'rc_highpass' if 'highpass' in lower or 'high-pass' in lower
                else 'opamp' if 'opamp' in lower or 'inverting' in lower
                else 'rectifier' if 'rectifier' in lower or 'bridge' in lower
                else 'timer_555' if '555' in lower or 'timer' in lower
                else 'transceiver' if 'transceiver' in lower or '74ls244' in lower or 'bus buffer' in lower
                else 'rc')
        circuit = template(kind, r1=values.get('R1', '10k'), r2=values.get('R2', '10k'), c1=values.get('C1', '100nF'), vin=values.get('V1', '5'))
    return await asyncio.to_thread(_execute_local,text,lower,project,circuit,directives,before_mutation)

def _execute_local(text,lower,project,circuit,directives,before_mutation=None):
    warnings=[]
    with project_lock(project):
        if before_mutation:before_mutation(project)
        sch=Schematic(project);before=sch.path.read_text();edits=[]
        try:
            if circuit:
                edits=apply_circuit(sch,circuit);warnings=circuit.warnings
            elif re.fullmatch(r'(run\s+)?(erc|check|validate)(\s+check)?',lower):pass
            elif lower in ['undo','redo']:
                edits=undo_redo(project,lower=='redo');sch=Schematic(project)
            elif re.match(r'^(remove|delete)\b',lower):
                refs=re.findall(rf'\b({REF})\b',text,re.I)
                if not refs:raise OperationError('Specify the component reference to remove.')
                edits=[sch.remove(ref.upper()) for ref in refs]
            elif re.match(r'^(connect|add\s+net|create\s+net)\b',lower):
                nodes=[(m[0].upper(),m[1]) for m in re.findall(rf'\b({REF})\s*(?:pin\s*|:)\s*([A-Za-z0-9]+)',text,re.I)]
                net_match=re.search(r'\bnet\s+([A-Za-z0-9_+./-]+)',text,re.I)
                if net_match:net=net_match[1]
                elif len(nodes)>=2:net=f'NET_{nodes[0][0]}_{nodes[0][1]}'
                else:raise OperationError('Specify a net name and component pin(s).')
                edits=sch.connect(net,nodes)
            elif re.match(r'^(change|set|replace)\b',lower) or re.match(rf'^\s*{REF}\s*(=|should\s+be|is|to)\s*',text,re.I):
                matches=list(re.finditer(rf'\b({REF})\s*(?:should\s+be|=|to|value|is)\s*({VALUE})',text,re.I))
                if not matches:raise OperationError('Use change R1 to 4.7k or R1 = 4.7k.')
                edits=[sch.set_value(m[1].upper(),m[2].strip()) for m in matches]
            elif re.match(r'^(add|place|insert|acquire)\b',lower):
                circuit=parse_text(text);edits=apply_circuit(sch,circuit)
            else:raise OperationError('Unsupported command. '+HELP)
            if edits and lower not in ['undo','redo']:
                sch.save()
                # Parsing via the native exporter is part of the transaction.
                sch.graph()
                remember(project,before,text)
            if directives:atomic_text(project/'.simulation.json',json.dumps({'directives':directives}))
        except Exception:
            atomic_text(sch.path,before)
            raise
        try:erc=sch.erc()
        except OperationError as e:erc={'status':'unavailable','passed':False,'violations':[],'error':str(e)}
    errors=[v for v in erc['violations'] if v.get('severity')=='error']
    reply=(f'Applied {len(edits)} change(s).' if edits else 'No schematic changes.')
    reply+=(' Native ERC passed.' if erc['status']=='completed' and erc['passed'] else f' Native ERC reports {len(errors)} error(s).' if erc['status']=='completed' else ' Native ERC is unavailable: '+erc['error'])
    return {'reply':reply,'route':'native_kicad','edits':edits,'warnings':warnings,'validation':erc,'stages':{'stage1_conversational':{'active_model':'explicit_commands','status':'executed'},'stage2_circuit_parser':{'components_found':len(circuit.components) if circuit else 0,'nets_found':len(circuit.nets) if circuit else 0},'stage3_feasibility_checker':{'status':erc['status'],'passed':erc['passed'],'errors':[v['description'] for v in errors],'warnings':warnings,'erc_count':len(erc['violations'])},'stage4_live_kicad_layout':{'edits_applied':len(edits),'details':edits}}}
