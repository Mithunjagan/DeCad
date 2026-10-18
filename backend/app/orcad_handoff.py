"""Truthful OrCAD handoff. Connectivity EDIF is not an editable Capture schematic."""
import hashlib,io,json,zipfile
from .formats import edif

def bundle(name,graph):
 files={'connectivity.edf':edif(name,graph).encode(),'circuit.json':json.dumps(graph,indent=2).encode(),
 'README.txt':b'''OrCAD handoff: native DSN generation is not implemented or validated.
connectivity.edf preserves component/pin/net data, but contains NETLIST views,
not graphical schematic views or Capture library symbols. It must not be
advertised as an editable OrCAD schematic or renamed to .DSN.

Use circuit.json as the reviewed source of truth. On a licensed OrCAD Capture
Windows machine, map each library symbol and physical pin, create schematic
pages, place symbols and wires, save a native DSN, reopen it, and compare its
exported netlist against circuit.json. Retain results before enabling native
DSN conversion. No guessed Tcl API or executable source content is included.
For an editable design now, use this product's native KiCad export.
'''}
 manifest={'format':'orcad-handoff','native_dsn_supported':False,'graphical_edif_supported':False,
 'source_review_required':True,'files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}}
 files['manifest.json']=json.dumps(manifest,indent=2).encode();out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in files.items():z.writestr(n,v)
 return out.getvalue()
