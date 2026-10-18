"""Explicit, content-aware application associations and confined launch jobs."""
import json,time,uuid,re
from pathlib import Path
from .engine import OperationError,atomic_text
from .integrations import TOOLS,bridge_status,check_tool

ASSOCIATIONS={
 '.kicad_sch':('kicad',['kicad'],'KiCad schematic'),
 '.kicad_pcb':('kicad',['kicad'],'KiCad PCB'),
 '.kicad_pro':('kicad',['kicad'],'KiCad project'),
 '.asc':('ltspice',['ltspice'],'LTspice schematic'),
 '.asy':('ltspice',['ltspice'],'LTspice symbol'),
 '.raw':('ltspice',['ltspice'],'Simulator waveform (dialect-specific)'),
 '.cir':('ngspice',['ngspice','ltspice'],'SPICE circuit'),
 '.spice':('ngspice',['ngspice','ltspice'],'SPICE circuit'),
 '.net':('ngspice',['ngspice','ltspice'],'SPICE netlist'),
}

def inspect(path):
 suffix=path.suffix.lower();recommended,compatible,kind=ASSOCIATIONS.get(suffix,(None,[],'Source document'))
 text=path.read_bytes()[:65536].decode('utf-8',errors='replace') if suffix in ('.sch','.lib') else ''
 if suffix=='.sch':
  if text.lstrip().startswith('<Qucs Schematic'):recommended,compatible,kind='qucs-s',['qucs-s'],'Qucs-S schematic'
  elif text.lstrip().startswith('EESchema Schematic File'):recommended,compatible,kind='kicad',['kicad'],'Legacy KiCad schematic'
  else:kind='Ambiguous .sch format — no application inferred'
 elif suffix=='.lib':
  if text.lstrip().startswith('<Qucs Library'):recommended,compatible,kind='qucs-s',['qucs-s'],'Qucs-S library'
  else:kind='Device library — import with its parent circuit'
 elif suffix=='.dsn':kind='DSN format is ambiguous (Specctra routing / OrCAD Capture)'
 return {'name':path.name,'extension':suffix,'kind':kind,'recommended':recommended,'compatible':compatible,'applications':[{'id':key,'name':value['name']} for key,value in TOOLS.items()],'can_open_original':bool(compatible),'can_convert_current_project':True}

def enqueue_file(state,user,tool,path):
 check_tool(tool);association=inspect(path)
 if tool not in association['compatible']:raise OperationError(f'{path.suffix} cannot be opened directly in {TOOLS[tool]["name"]}. Choose an associated application or explicitly export the current circuit to that application.')
 if path.suffix.lower() in ('.cir','.spice','.net'):
  # Prevent uploaded simulator control scripts / includes from executing on host.
  from .ingestion import parse_spice
  from .formats import spice
  source=path.read_text()
  first=source.splitlines()[0].strip() if source.splitlines() else ''
  if re.match(r'^[RCLVIDQMX]\d+\s',first,re.I):raise OperationError('SPICE treats the first line as a title. Add a title or comment line before opening this original file so the first component is not silently lost.')
  circuit,directives=parse_spice(source)
  spice({'components':[c.model_dump() for c in circuit.components],'nets':[n.model_dump() for n in circuit.nets]}, {'models':circuit.models})
 status=bridge_status(state)
 if not status.get('ready'):raise OperationError('Desktop bridge is not running. Start the launcher, then refresh application availability.')
 if not status.get('applications',{}).get(tool,{}).get('installed'):raise OperationError(f'{TOOLS[tool]["name"]} is not installed on the host.')
 jid=uuid.uuid4().hex;folder=state/'bridge-jobs'/jid;folder.mkdir(parents=True)
 # Copy only data files in the same project directory; never paths supplied by file content.
 for sibling in path.parent.iterdir():
  if sibling.is_file() and not sibling.is_symlink() and (sibling==path or sibling.suffix.lower() in ('.kicad_pro','.lib','.asy')) and sibling.stat().st_size<=25*1024*1024:
   (folder/sibling.name).write_bytes(sibling.read_bytes())
 atomic_text(folder/'request.json',json.dumps({'id':jid,'owner':user,'tool':tool,'action':'open','file':path.name,'created_at':time.time()}))
 return {'id':jid,'status':'queued','tool':tool,'file':path.name,'mode':'original'}
