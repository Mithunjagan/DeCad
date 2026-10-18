"""Explicit application adapters, portable bundles, and host launch jobs."""
from __future__ import annotations
import hashlib
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from .engine import OperationError, Schematic, atomic_text
from .formats import spice
from .simulation import number

TOOLS={
 'kicad':{'name':'KiCad','formats':['kicad_sch','kicad_pro'],'license':'GPL-3.0-or-later','download':'https://www.kicad.org/download/'},
 'ngspice':{'name':'ngspice','formats':['cir'],'license':'BSD','download':'https://ngspice.sourceforge.io/download.html'},
 'ltspice':{'name':'LTspice','formats':['cir'],'license':'Free of charge; proprietary vendor EULA','download':'https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html'},
 'qucs-s':{'name':'Qucs-S','formats':['sch','lib'],'license':'GPL-2.0-or-later','download':'https://github.com/ra3xdh/qucs_s/releases'},
}

def check_tool(tool):
 if tool not in TOOLS:raise OperationError('Unknown application. Supported: '+', '.join(TOOLS))
 return tool

def qucs_files(name,graph,controls):
 """Qucs-S native wrapper around a SPICE subcircuit, with labeled monitor ports."""
 text=spice(graph,controls)
 mapping=json.loads(text.splitlines()[1].split(': ',1)[1])
 nodes=[(k,v) for k,v in mapping.items() if v!='0']
 if not nodes:raise OperationError('Qucs-S export needs non-ground circuit nodes.')
 body=[line for line in text.splitlines() if not line.startswith('*') and not line.lower().startswith(('.tran ','.end'))]
 library='* Schematic2SDN exported graph\n.subckt S2SDN '+ ' '.join(v for _,v in nodes)+'\n'+'\n'.join(body)+'\n.ends S2SDN\n'
 ports=','.join('_net'+v for _,v in nodes);h=30*((len(nodes)-1)//2)+15;x=300;y=200+h
 comp=[f'<SPICE X1 1 {x} {y} -26 {-h-45} 0 0 "circuit.lib" 1 "{ports}" 0 "no" 0 "none" 0 "" 0>',f'<GND * 1 {x} {y+h+15} 0 0 0 0>']
 wires=[]
 for i,(_,net) in enumerate(nodes):
  py=y+15-h+60*(i//2);px=x+(-30 if i%2==0 else 30);outer=px+(-90 if i%2==0 else 90)
  wires.append(f'<{min(px,outer)} {py} {max(px,outer)} {py} "{net}" {min(px,outer)} {py-20} 0 "">')
 step=number(controls.get('step','10u'));stop=number(controls.get('stop','10m'))
 if step<=0 or stop<=0 or stop/step>20000:raise OperationError('Invalid transient controls.')
 count=int(round(stop/step))+1
 comp.append(f'<.TR TR1 1 550 100 0 81 0 0 "lin" 1 "0" 1 "{stop}" 1 "{count}" 0 "Trapezoidal" 0 "2" 0 "1 ns" 0 "1e-16" 0 "150" 0 "0.001" 0 "1 pA" 0 "1 uV" 0 "26.85" 0 "1e-3" 0 "1e-6" 0 "1" 0 "CroutLU" 0 "no" 0 "yes" 0 "0" 0>')
 sch='<Qucs Schematic 26.1.1>\n<Properties>\n<View=0,0,1200,900,1,0,0>\n<Grid=10,10,1>\n<DataSet=circuit.dat>\n<OpenDisplay=0>\n<RunScript=0>\n</Properties>\n<Symbol>\n</Symbol>\n<Components>\n'+'\n'.join(comp)+'\n</Components>\n<Wires>\n'+'\n'.join(wires)+'\n</Wires>\n<Diagrams>\n</Diagrams>\n<Paintings>\n</Paintings>\n'
 return {'circuit.sch':sch.encode(),'circuit.lib':library.encode(),'node-map.json':json.dumps(mapping,indent=2).encode()}

def artifacts(tool,project,controls=None):
 check_tool(tool);controls=controls or {};sch=Schematic(project);graph=sch.graph()
 if tool=='kicad':
  result={sch.path.name:sch.path.read_bytes()}
  for p in project.glob('*.kicad_pro'):result[p.name]=p.read_bytes()
 elif tool=='qucs-s':result=qucs_files(project.name,graph,controls)
 else:
  text=spice(graph,controls)
  if tool=='ltspice':text=text.replace('.end',''.join(['.options plotwinsize=0\n','.end']))
  result={'circuit.cir':text.encode()}
 result['circuit.json']=json.dumps(graph,indent=2).encode()
 result['README.txt']=(f'Application: {TOOLS[tool]["name"]}\n'+('Open circuit.sch with Qucs-S. The SPICE wrapper exposes each node for plotting. Keep circuit.lib beside the schematic. Select ngspice as the simulator.\n' if tool=='qucs-s' else 'Open the native schematic files.\n' if tool=='kicad' else 'Open circuit.cir in the simulator.\n')+'Component and pin mapping is in circuit.json. Unsupported device models are rejected.\n').encode()
 result['manifest.json']=json.dumps({'format_version':1,'tool':tool,'project':project.name,'files':{n:hashlib.sha256(v).hexdigest() for n,v in result.items()}},indent=2).encode()
 return result

def bundle(tool,project,controls=None):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for n,value in artifacts(tool,project,controls).items():z.writestr(n,value)
 return out.getvalue()

def bridge_status(state):
 path=state/'bridge-status.json'
 try:
  data=json.loads(path.read_text())
  return {**data,'ready':time.time()-data.get('updated_at',0)<15}
 except (OSError,ValueError):return {'ready':False,'applications':{},'message':'Run the desktop bridge to open host applications.'}

def enqueue(state,user,tool,project,controls=None):
 check_tool(tool)
 status=bridge_status(state)
 if not status['ready']:raise OperationError('Desktop bridge is not running. Start the launcher or download an application bundle.')
 if not status.get('applications',{}).get(tool,{}).get('installed'):raise OperationError(f'{TOOLS[tool]["name"]} is not installed on the host. Install it or download the portable bundle.')
 jid=uuid.uuid4().hex;folder=state/'bridge-jobs'/jid;folder.mkdir(parents=True)
 exported=artifacts(tool,project,controls)
 for n,data in exported.items(): (folder/n).write_bytes(data)
 main=next(n for n in exported if n.endswith('.kicad_sch')) if tool=='kicad' else 'circuit.sch' if tool=='qucs-s' else 'circuit.cir'
 atomic_text(folder/'request.json',json.dumps({'id':jid,'owner':user,'tool':tool,'action':'open','file':main,'created_at':time.time()}))
 return {'id':jid,'status':'queued','tool':tool}

def job_result(state,user,jid):
 if len(jid)!=32 or any(c not in '0123456789abcdef' for c in jid):raise OperationError('Invalid job ID.')
 folder=state/'bridge-jobs'/jid
 try:request=json.loads((folder/'request.json').read_text())
 except (OSError,ValueError):raise OperationError('No such application job.')
 if request.get('owner')!=user:raise OperationError('No such application job.')
 response=folder/'response.json'
 return json.loads(response.read_text()) if response.exists() else {'id':jid,'status':'queued','tool':request['tool']}


def simulate_qucs(project,controls=None):
 """Compile a native Qucs-S schematic, then solve the emitted SPICE circuit."""
 import os,shutil,subprocess,tempfile,re
 from .simulation import run_ngspice
 if not shutil.which('qucs-s') or not shutil.which('ngspice'):raise OperationError('Qucs-S and ngspice are required for this operation.')
 controls=controls or {};graph=Schematic(project).graph()
 with tempfile.TemporaryDirectory() as directory:
  folder=Path(directory)
  for name,data in qucs_files(project.name,graph,controls).items():(folder/name).write_bytes(data)
  try:
   process=subprocess.run(['qucs-s','-n','--ngspice','-i',str(folder/'circuit.sch'),'-o',str(folder/'compiled.cir')],cwd=folder,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=45)
  except subprocess.TimeoutExpired as e:raise OperationError('Qucs-S compilation timed out.') from e
  output=folder/'compiled.cir'
  if process.returncode or not output.exists():raise OperationError('Qucs-S compilation failed: '+(process.stderr or process.stdout)[-1500:])
  compiled=output.read_text()
  compiled=re.sub(r'(?ims)^\s*\.control\b.*?^\s*\.endc\b[^\n]*','',compiled)
  # Resolve generated include paths before the solver uses its isolated directory.
  compiled=re.sub(r'(?im)^\s*\.include\s+.*circuit\.lib.*$',(folder/'circuit.lib').read_text(),compiled)
  result=run_ngspice(compiled,graph,controls);result['solver']='qucs-s + ngspice';result['title']='Qucs-S transient';return result
