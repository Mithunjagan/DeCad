"""Actual circuit simulation: ngspice when installed, MNA for linear R/C/L/V/I otherwise."""
from __future__ import annotations
from .ground import reference_name
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from .engine import OperationError
from .formats import spice

SCALE={'':1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}

def number(text):
    m=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[tgkmunpfµ]?)(?:[a-zA-ZΩ]*)\s*',text,re.I)
    if not m:raise OperationError(f'Invalid numeric simulation value: {text}')
    value=float(m[1])*SCALE[m[2].lower().replace('µ','u')]
    if not math.isfinite(value):raise OperationError('Non-finite simulation value.')
    return value


def source(text,t):
    text=text.strip()
    if text.lower().startswith('dc '):return number(text[3:])
    m=re.fullmatch(r'(pulse|sin)\s*\(([^)]+)\)',text,re.I)
    if not m:return number(text)
    values=[number(x) for x in re.split(r'[\s,]+',m[2].strip())]
    if m[1].lower()=='sin':
        if len(values)<3:raise OperationError('SIN needs offset, amplitude, frequency.')
        off,amp,freq=values[:3];delay=values[3] if len(values)>3 else 0
        return off+amp*math.sin(2*math.pi*freq*max(0,t-delay))
    if len(values)!=7:raise OperationError('PULSE needs v1 v2 delay rise fall width period.')
    low,high,delay,rise,fall,width,period=values
    if period<=0 or width<0 or rise<0 or fall<0:raise OperationError('Invalid PULSE timing.')
    if t<delay:return low
    x=(t-delay)%period
    if rise>0 and x<rise:return low+(high-low)*x/rise
    if x<rise+width:return high
    if fall>0 and x<rise+width+fall:return high+(low-high)*(x-rise-width)/fall
    return low


def simulate(graph, controls=None):
    controls=controls or {};step=number(controls.get('step','10u'));stop=number(controls.get('stop','10m'))
    if step<=0 or stop<=0 or stop/step>20000:raise OperationError('Simulation needs positive times and at most 20,000 steps.')
    text=spice(graph,controls)
    if shutil.which('ngspice'):return run_ngspice(text,graph,controls)
    return mna(graph,step,stop)


def run_ngspice(text,graph,controls):
    nodes={};labels={}
    reference=reference_name(n['name'] for n in graph['nets'])
    for i,net in enumerate(graph['nets'],1):
        if net['name']!=reference:
            nodes[net['name']]=f'n{i}';labels[f'n{i}']=net['name']
    if not nodes:raise OperationError('There are no non-ground nodes to simulate.')
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'circuit.cir';out=Path(folder)/'waveform.dat'
        # Keep .ends (subcircuit terminators); remove only top-level analysis/end cards.
        body='\n'.join(l for l in text.splitlines() if not re.match(r'^\s*\.(?:tran|end)\b',l,re.I))
        body += '\n.control\nset wr_singlescale\nset wr_vecnames\ntran '+controls.get('step','10u')+' '+controls.get('stop','10m')+'\nwrdata '+str(out)+' '+' '.join('v('+v+')' for v in nodes.values())+'\nquit\n.endc\n.end\n'
        path.write_text(body)
        try:r=subprocess.run(['ngspice','-b',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=45)
        except subprocess.TimeoutExpired as e:raise OperationError('SPICE simulation timed out.') from e
        if r.returncode or not out.exists():raise OperationError('SPICE simulation failed: '+(r.stderr or r.stdout)[-1500:])
        data=np.loadtxt(out,skiprows=1,ndmin=2)
        if data.shape[1]!=len(nodes)+1:raise OperationError('Unexpected SPICE waveform output.')
        rows=[];names=list(nodes)
        for row in data[::max(1,len(data)//1000)]:
            sample={'t_us':float(row[0]*1e6),'signals':{name:float(row[i+1]) for i,name in enumerate(names)}}
            sample['vin']=sample['signals'].get('VIN',sample['signals'][names[0]])
            sample['vout']=sample['signals'].get('VOUT',sample['signals'][names[-1]])
            rows.append(sample)
        return {'title':'SPICE transient','solver':'ngspice','signals':names,'data':rows}


def mna(graph,step,stop):
    if not graph['components']:raise OperationError('Add a powered circuit before simulation.')
    nets=graph['nets'];reference=reference_name(n['name'] for n in nets);names=[n['name'] for n in nets if n['name']!=reference]
    if len(names)>200:raise OperationError('Linear solver is limited to 200 nodes; use ngspice for larger circuits.')
    if len(names)==len(nets):raise OperationError('Connect a ground (GND or 0) net before simulation.')
    idx={name:i for i,name in enumerate(names)};connections={}
    for net in nets:
        for node in net['nodes']:connections[(node['ref'],node['pin'])]=idx.get(net['name'],-1)
    comps=graph['components'];branches=[c for c in comps if c['ref'][0] in 'VL'];branch_idx={c['ref']:len(names)+i for i,c in enumerate(branches)}
    size=len(names)+len(branches)
    if size==0:raise OperationError('No circuit nodes to simulate.')
    matrix=np.zeros((size,size));capacitors=[];inductors=[];sources=[]
    def conductance(a,b,g):
        if a>=0:matrix[a,a]+=g
        if b>=0:matrix[b,b]+=g
        if a>=0 and b>=0:matrix[a,b]-=g;matrix[b,a]-=g
    for c in comps:
        ref=c['ref'];kind=ref[0];a=connections.get((ref,'1'));b=connections.get((ref,'2'))
        if a is None or b is None:raise OperationError(f'Unresolved pins on {ref}.')
        if kind in 'RCL':
            value=number(c['value'])
            if value<=0:raise OperationError(f'{ref} must have a positive value.')
        if kind=='R':conductance(a,b,1/value)
        elif kind=='C':conductance(a,b,value/step);capacitors.append((a,b,value/step))
        elif kind in 'VL':
            k=branch_idx[ref]
            if a>=0:matrix[a,k]+=1;matrix[k,a]+=1
            if b>=0:matrix[b,k]-=1;matrix[k,b]-=1
            if kind=='L':matrix[k,k]-=value/step;inductors.append((k,value/step))
            else:sources.append((kind,a,b,k,c['value']))
        elif kind=='I':sources.append((kind,a,b,None,c['value']))
        else:raise OperationError(f'{ref} requires ngspice with an explicit device model.')
    try:
        from scipy.linalg import lu_factor,lu_solve
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('error');factor=lu_factor(matrix)
    except Exception as e:raise OperationError('Circuit is singular: check floating nodes, voltage-source loops, and missing ground.') from e
    previous=np.zeros(size);rows=[];count=math.ceil(stop/step-1e-9)
    for i in range(count+1):
        t=i*step;rhs=np.zeros(size)
        for a,b,g in capacitors:
            current=g*((previous[a] if a>=0 else 0)-(previous[b] if b>=0 else 0))
            if a>=0:rhs[a]+=current
            if b>=0:rhs[b]-=current
        for k,g in inductors:rhs[k]-=g*previous[k]
        for kind,a,b,k,value in sources:
            v=source(value,t)
            if kind=='V':rhs[k]+=v
            else:
                if a>=0:rhs[a]-=v
                if b>=0:rhs[b]+=v
        previous=lu_solve(factor,rhs)
        if not np.isfinite(previous).all():raise OperationError('Simulation did not converge.')
        if i%max(1,count//1000)==0:
            signals={n:float(previous[j]) for j,n in enumerate(names)}
            rows.append({'t_us':t*1e6,'signals':signals,'vin':signals.get('VIN',next(iter(signals.values()),0)),'vout':signals.get('VOUT',list(signals.values())[-1] if signals else 0)})
    return {'title':'Linear circuit transient','solver':'modified_nodal_analysis_backward_euler','signals':names,'data':rows}
