import io,json,os,sys,subprocess,tempfile,zipfile,hashlib
from pathlib import Path
from .engine import OperationError
from pydantic import BaseModel, Field, ConfigDict, ValidationError, model_validator

class Placement(BaseModel):
 model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
 footprint: str = Field(min_length=3,max_length=300,pattern=r'^[^:/\\]+:[^:/\\]+$')
 x_mm: float
 y_mm: float
 rotation_deg: float = Field(default=0,ge=-3600,le=3600)

class BoardPlan(BaseModel):
 model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
 width_mm: float = Field(ge=10,le=500)
 height_mm: float = Field(ge=10,le=500)
 track_width_mm: float = Field(default=.25,ge=.1,le=2)
 clearance_mm: float = Field(default=.2,ge=.1,le=2)
 placements: dict[str,Placement] = Field(min_length=1,max_length=200)

 @model_validator(mode='after')
 def check_positions(self):
  for ref,item in self.placements.items():
   if '..' in item.footprint:raise ValueError('Invalid footprint identifier.')
   if not 2<=item.x_mm<=self.width_mm-2 or not 2<=item.y_mm<=self.height_mm-2:
    raise ValueError(f'{ref}: footprint origin must lie within the 2 mm board margin.')
  return self


def export(graph,plan):
 try:plan=BoardPlan.model_validate(plan).model_dump()
 except ValidationError as e:
  if any('footprint' in issue['loc'] for issue in e.errors()):raise OperationError('Invalid footprint identifier. Choose an installed Library:Footprint.') from e
  raise OperationError('Invalid PCB plan: '+'; '.join('.'.join(map(str,issue['loc']))+': '+issue['msg'] for issue in e.errors())) from e
 if not graph.get('components') or not graph.get('nets'):raise OperationError('Add components and pin connections before exporting a PCB.')
 interpreter=os.getenv('KICAD_PYTHON','/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3' if sys.platform=='darwin' else '/usr/bin/python3')
 if not Path(interpreter).is_file():
  interpreter='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);source=root/'input.json';source.write_text(json.dumps({'graph':graph,'plan':plan}))
  r=subprocess.run([interpreter,str(Path(__file__).with_name('specctra_worker.py')),str(source),str(root)],capture_output=True,text=True,timeout=60)
  if r.returncode:raise OperationError('Specctra export: '+r.stderr[-1500:])
  files={n:(root/n).read_bytes() for n in ['board.kicad_pcb','board.kicad_pro','board.dsn','verification.json']}
  from .sexpr import parse,child,children
  parsed=parse(files['board.dsn'].decode().replace('(string_quote ")','(string_quote quote)'))
  network=child(parsed,'network')
  actual={n[1]:set(child(n,'pins')[1:]) for n in children(network,'net')}
  expected={n['name']:{node['ref']+'-'+node['pin'] for node in n['nodes']} for n in graph['nets']}
  if actual!=expected:raise OperationError('Specctra pin/net export mismatch.')
  report=json.loads(files['verification.json']);report['dsn_pin_net_equivalence']=True
  files['verification.json']=json.dumps(report,indent=2).encode()
  files['board-plan.json']=json.dumps(plan,indent=2).encode();files['circuit.json']=json.dumps(graph,indent=2).encode()
  files['manifest.json']=json.dumps({'format':'Specctra PCB autorouter DSN','files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}},indent=2).encode()
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   for n,v in files.items():z.writestr(n,v)
  return out.getvalue()
