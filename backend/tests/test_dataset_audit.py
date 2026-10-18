import importlib.util,json
from pathlib import Path
from PIL import Image
spec=importlib.util.spec_from_file_location('dataset_tools',Path(__file__).resolve().parents[2]/'training/dataset_tools.py')
tools=importlib.util.module_from_spec(spec);spec.loader.exec_module(tools)

def test_generated_pair_folder_is_auditable(tmp_path):
 Image.new('RGB',(20,20),'white').save(tmp_path/'circuit.png')
 data={'components':[{'ref':'R1','value':'10k'}],'nets':[{'name':'GND','nodes':[{'ref':'R1','pin':'2'}]},{'name':'N1','nodes':[{'ref':'R1','pin':'1'}]}]}
 (tmp_path/'circuit.json').write_text(json.dumps(data));(tmp_path/'circuit.cir').write_text('* test\nR1 N1 0 10k\n.end\n')
 result=tools.audit(tmp_path)
 assert result['accepted']==1 and result['samples'][0]['netlist_equivalence_verified']
 assert result['custom_training_ready'] is False

def test_ground_mismatch_rejected(tmp_path):
 Image.new('RGB',(20,20),'white').save(tmp_path/'circuit.png')
 data={'components':[{'ref':'R1','value':'10k'}],'nets':[{'name':'GND','nodes':[{'ref':'R1','pin':'1'}]},{'name':'N1','nodes':[{'ref':'R1','pin':'2'}]}]}
 (tmp_path/'circuit.json').write_text(json.dumps(data));(tmp_path/'circuit.cir').write_text('* test\nR1 N1 0 10k\n.end\n')
 result=tools.audit(tmp_path)
 assert result['accepted']==0 and 'disagree' in result['rejected'][0]['reason']

def test_reference_renumbering_stays_in_same_split_group():
 from app.assistant import template
 truth=template('divider');renamed=truth.model_copy(deep=True);mapping={'V1':'V7','R1':'R42','R2':'R9'}
 for component in renamed.components:component.ref=mapping[component.ref]
 for net in renamed.nets:
  for node in net.nodes:node.ref=mapping[node.ref]
 assert tools.topology_group(truth)==tools.topology_group(renamed)
