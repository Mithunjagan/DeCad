"""Render real KiCad symbol geometry, not placeholder boxes, for paired training data."""
import re,shutil,subprocess,tempfile,xml.etree.ElementTree as ET
from pathlib import Path
from .engine import OperationError
from .sexpr import child

def raster(sch,svg):
 if not shutil.which('rsvg-convert'):raise OperationError('Raster dataset rendering requires rsvg-convert (included in Docker).')
 root=ET.fromstring(svg);points=[]
 for symbol in sch.symbols():
  at=child(symbol,'at');points.append((float(at[1]),float(at[2])));points.extend(sch.pin_positions(symbol).values())
 if not points:raise OperationError('Cannot render an empty dataset circuit.')
 x0=min(x for x,y in points)-12;y0=min(y for x,y in points)-12;x1=max(x for x,y in points)+20;y1=max(y for x,y in points)+20
 root.set('viewBox',f'{x0} {y0} {x1-x0} {y1-y0}');root.set('width','1600');root.set('height',str(int(1600*(y1-y0)/(x1-x0))))
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'input.svg';out=Path(td)/'image.png';p.write_bytes(ET.tostring(root))
  try:r=subprocess.run(['rsvg-convert','-o',str(out),str(p)],capture_output=True,text=True,timeout=30)
  except subprocess.TimeoutExpired as e:raise OperationError('Dataset rasterization timed out.') from e
  if r.returncode or not out.exists():raise OperationError('Dataset rasterization failed: '+r.stderr[-500:])
  return out.read_bytes()
