import io,json,zipfile
from pathlib import Path
import pytest
from app.specctra import export
from app.engine import OperationError

@pytest.fixture
def data():
 return {'components':[{'ref':'R1','value':'10k'}],'nets':[{'name':'A','nodes':[{'ref':'R1','pin':'1'}]},{'name':'GND','nodes':[{'ref':'R1','pin':'2'}]}]},{'width_mm':40,'height_mm':30,'placements':{'R1':{'footprint':'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal','x_mm':10,'y_mm':10}}}

def test_native_specctra_pin_mapping_and_invalid_pad(data):
 if not Path('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3').is_file():
  try:
   import subprocess
   subprocess.run(['/usr/bin/python3','-c','import pcbnew'],check=True,capture_output=True)
  except Exception:pytest.skip('Native pcbnew unavailable')
 graph,plan=data;plan['track_width_mm']=.5;plan['clearance_mm']=.4
 with zipfile.ZipFile(io.BytesIO(export(graph,plan))) as z:
  text=z.read('board.dsn').decode();assert '(pcb ' in text and '(network' in text and 'R1-1' in text and 'R1-2' in text
  assert '(width 500)' in text
  assert json.loads(z.read('verification.json'))['dsn_pin_net_equivalence']
 graph['nets'][0]['nodes'][0]['pin']='999'
 with pytest.raises(OperationError,match='no physical pad'):export(graph,plan)
 plan['placements']['R1']['footprint']='../escape:bad'
 with pytest.raises(OperationError,match='Invalid footprint'):export(graph,plan)
