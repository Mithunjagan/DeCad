import shutil
import pytest
from app.engine import Schematic
from app.ingestion import Circuit
from app.assistant import apply_circuit
from app.integrations import simulate_qucs
from app.simulation import simulate

def supply():
 return Circuit.model_validate({'components':[{'ref':'V1','value':'5'},{'ref':'V2','value':'5'},{'ref':'R1','value':'10k'},{'ref':'R2','value':'10k'}],'nets':[{'name':'GND','nodes':[{'ref':'V1','pin':'2'},{'ref':'V2','pin':'1'}]},{'name':'VIN','nodes':[{'ref':'V1','pin':'1'},{'ref':'R1','pin':'1'}]},{'name':'VOUT','nodes':[{'ref':'R1','pin':'2'},{'ref':'R2','pin':'1'}]},{'name':'VSS','nodes':[{'ref':'V2','pin':'2'},{'ref':'R2','pin':'2'}]}]})

@pytest.mark.parametrize('solver',['ngspice','qucs-s'])
def test_negative_supply_is_not_shorted_to_ground(tmp_path,solver):
 if not shutil.which(solver):pytest.skip('Native simulator is included in Docker')
 p=tmp_path/'SplitSupply';Schematic.create(p,p.name);sch=Schematic(p);apply_circuit(sch,supply());sch.save()
 result=simulate_qucs(p) if solver=='qucs-s' else simulate(sch.graph())
 assert result['data'][-1]['signals']['VSS']==pytest.approx(-5)
 assert result['data'][-1]['signals']['VOUT']==pytest.approx(0,abs=1e-9)
