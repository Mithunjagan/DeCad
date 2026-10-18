"""Run with KiCad's Python interpreter; inputs are JSON data only."""
import json,sys
from pathlib import Path
import pcbnew as p

def generate(data,out):
 board=p.BOARD();graph=data['graph'];plan=data['plan'];placements=plan['placements']
 refs={c['ref'] for c in graph['components']}
 if set(placements)!=refs:raise ValueError('Specify footprint and placement for every component.')
 width=float(plan['width_mm']);height=float(plan['height_mm'])
 if not 10<=width<=500 or not 10<=height<=500:raise ValueError('Board dimensions must be 10–500 mm.')
 roots=[Path('/usr/share/kicad/footprints'),Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')]
 root=next((r for r in roots if r.is_dir()),None)
 if root is None:raise ValueError('KiCad footprint library unavailable.')
 pads={}
 for c in graph['components']:
  item=placements[c['ref']];lib,name=item['footprint'].split(':')
  if any(not v or '/' in v or '\\' in v or '..' in v for v in [lib,name]):raise ValueError('Invalid footprint identifier.')
  fp=p.FootprintLoad(str(root/(lib+'.pretty')),name)
  if fp is None:raise ValueError('Missing footprint: '+item['footprint'])
  x=float(item['x_mm']);y=float(item['y_mm']);angle=float(item.get('rotation_deg',0))
  if not 2<=x<=width-2 or not 2<=y<=height-2:raise ValueError('Footprint origin must lie within board margin.')
  fp.SetReference(c['ref']);fp.SetValue(c['value']);fp.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));fp.SetOrientationDegrees(angle);board.Add(fp)
  for pad in fp.Pads():
   pos=pad.GetPosition()
   if not 0<p.ToMM(pos.x)<width or not 0<p.ToMM(pos.y)<height:raise ValueError('Footprint pad outside board: '+c['ref'])
   pads.setdefault((c['ref'],pad.GetNumber()),[]).append(pad)
 for i,net in enumerate(graph['nets'],1):
  ni=p.NETINFO_ITEM(board,net['name'],i);board.Add(ni)
  for node in net['nodes']:
   key=(node['ref'],node['pin'])
   if key not in pads:raise ValueError('Footprint has no physical pad for '+str(key))
   for pad in pads[key]:pad.SetNet(ni)
 for a,b in [((0,0),(width,0)),((width,0),(width,height)),((width,height),(0,height)),((0,height),(0,0))]:
  edge=p.PCB_SHAPE();edge.SetShape(p.SHAPE_T_SEGMENT);edge.SetLayer(p.Edge_Cuts);edge.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));edge.SetEnd(p.VECTOR2I(p.FromMM(b[0]),p.FromMM(b[1])));edge.SetWidth(p.FromMM(.05));board.Add(edge)
 settings=board.GetDesignSettings();track=float(plan.get('track_width_mm',.25));clearance=float(plan.get('clearance_mm',.2))
 if not .1<=track<=2 or not .1<=clearance<=2:raise ValueError('Track/clearance rules must be 0.1–2 mm.')
 settings.m_NetSettings.GetDefaultNetclass().SetTrackWidth(p.FromMM(track));settings.m_NetSettings.GetDefaultNetclass().SetClearance(p.FromMM(clearance))
 out=Path(out);out.mkdir(exist_ok=True);pcb=out/'board.kicad_pcb';dsn=out/'board.dsn'
 (out/'board.kicad_pro').write_text(json.dumps({'meta':{'filename':'board.kicad_pro','version':1},'net_settings':{'meta':{'version':3},'classes':[{'name':'Default','clearance':clearance,'track_width':track,'via_diameter':.8,'via_drill':.4}]}}))
 p.SaveBoard(str(pcb),board)
 reopened=p.LoadBoard(str(pcb))
 actual={(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in reopened.GetFootprints() for pad in f.Pads() if pad.GetNetname()}
 for net in graph['nets']:
  for node in net['nodes']:
   if actual.get((node['ref'],node['pin']))!=net['name']:raise ValueError('Board pin/net round-trip mismatch.')
 reopened.GetDesignSettings().m_NetSettings.GetDefaultNetclass().SetTrackWidth(p.FromMM(track))
 reopened.GetDesignSettings().m_NetSettings.GetDefaultNetclass().SetClearance(p.FromMM(clearance))
 if not p.ExportSpecctraDSN(reopened,str(dsn)) or not dsn.is_file():raise ValueError('KiCad Specctra export failed.')
 (out/'verification.json').write_text(json.dumps({'format':'Specctra DSN','native_kicad_export':True,'pcb_pin_net_roundtrip':True,'kicad_version':p.GetBuildVersion(),'manufacturing_approved':False,'note':'Unrouted board. Placement, courtyard overlap, DRC and routing require review.'},indent=2))
if __name__=='__main__':
 try:generate(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
