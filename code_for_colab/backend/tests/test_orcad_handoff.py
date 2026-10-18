import asyncio,hashlib,io,json,zipfile
from app.orcad_handoff import bundle
from app import ingestion

def test_handoff_preserves_graph_and_does_not_claim_dsn():
 graph={'components':[{'ref':'R1','value':'10k','library':'Device:R'}],'nets':[{'name':'GND','nodes':[{'ref':'R1','pin':'2'}]}]}
 with zipfile.ZipFile(io.BytesIO(bundle('Example',graph))) as z:
  manifest=json.loads(z.read('manifest.json'))
  assert not manifest['native_dsn_supported'] and not manifest['graphical_edif_supported']
  assert not any(n.lower().endswith('.dsn') for n in z.namelist())
  assert json.loads(z.read('circuit.json'))==graph
  for n,h in manifest['files'].items():assert hashlib.sha256(z.read(n)).hexdigest()==h

def test_pdf_with_text_still_uses_visual_extraction(tmp_path,monkeypatch):
 p=tmp_path/'schematic.pdf';p.write_bytes(b'fixture')
 monkeypatch.setattr(ingestion,'extract_text',lambda path:'R1 10k labels but no netlist')
 expected=ingestion.Circuit(components=[{'ref':'R1','value':'10k'}])
 called=[]
 async def extract(path):called.append(path);return expected
 monkeypatch.setattr(ingestion,'extract_image',extract)
 circuit,_=asyncio.run(ingestion.ingest(p))
 assert called==[p] and circuit==expected
