import importlib.util,json,subprocess
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('desktop_bridge',Path(__file__).resolve().parents[2]/'bridge/desktop_bridge.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

@pytest.mark.parametrize('system,exe,expected',[('Darwin','/Applications/KiCad.app',['open','-a']),('Windows','C:/Program Files/KiCad/eeschema.exe',['C:/Program Files/KiCad/eeschema.exe']),('Linux','/usr/bin/eeschema',['/usr/bin/eeschema'])])
def test_launch_arguments_are_quoted_by_subprocess(tmp_path,monkeypatch,system,exe,expected):
 monkeypatch.setattr(bridge.platform,'system',lambda:system)
 (tmp_path/'circuit with spaces.kicad_sch').write_text('native test data')
 (tmp_path/'request.json').write_text(json.dumps({'id':'a'*32,'tool':'kicad','action':'open','file':'circuit with spaces.kicad_sch'}))
 calls=[]
 class Process:
  pid=123
  def wait(self,timeout):return 0
 def start(command,**kwargs):calls.append((command,kwargs));return Process()
 monkeypatch.setattr(bridge.subprocess,'Popen',start)
 assert bridge.process(tmp_path,{'kicad':{'installed':True,'path':exe}})['status']=='launched'
 command,options=calls[0]
 assert command[:len(expected)]==expected
 assert command[-1]==str((tmp_path/'circuit with spaces.kicad_sch').resolve())
 assert 'shell' not in options

@pytest.mark.parametrize('system',['Darwin','Windows','Linux'])
def test_explicit_installed_path_discovery(tmp_path,monkeypatch,system):
 path=tmp_path/'my app';path.write_text('fixture')
 monkeypatch.setattr(bridge.platform,'system',lambda:system)
 monkeypatch.setenv('S2SDN_QUCS_S_PATH',str(path))
 assert bridge.discover()['qucs-s']['path']==str(path)
