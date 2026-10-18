from pathlib import Path
import pytest
from app import footprints
from app.engine import OperationError
from app.specctra import export
from test_operations import client

@pytest.fixture
def library(tmp_path,monkeypatch):
 root=tmp_path/'footprints';lib=root/'Test.pretty';lib.mkdir(parents=True)
 (lib/'TwoPin.kicad_mod').write_text('(footprint "TwoPin" (descr "Two pin package") (pad "1" thru_hole circle) (pad "2" thru_hole circle) (pad "" np_thru_hole circle))')
 monkeypatch.setattr(footprints,'library_root',lambda:root)
 return root

def test_catalog_search_and_exact_physical_pads(library):
 assert footprints.search('test two')==['Test:TwoPin']
 assert footprints.details('Test:TwoPin')['pads']==['1','2']
 assert footprints.search('absent')==[]

@pytest.mark.parametrize('identifier',['../escape:bad','Test:../outside','Test/no:bad','Test:absent','Test:bad\x00name','Test:'+('x'*400)])
def test_catalog_rejects_unsafe_or_missing_footprints(library,identifier):
 with pytest.raises(OperationError):footprints.details(identifier)

def test_catalog_authentication_and_api(client,library):
 assert client.get('/libraries/footprints?q=two').json()['items']==['Test:TwoPin']
 assert client.get('/libraries/footprint?id=Test:TwoPin').json()['pads']==['1','2']
 assert client.get('/libraries/footprint?id=Test:missing').status_code==422
 client.post('/auth/logout')
 assert client.get('/libraries/footprints?q=two').status_code==401

@pytest.mark.parametrize('plan',[{}, {'width_mm':100,'height_mm':80,'placements':None}, {'width_mm':100,'height_mm':80,'placements':{'R1':{'footprint':'Test:TwoPin','x_mm':float('nan'),'y_mm':10}}}])
def test_invalid_board_plans_fail_before_native_process(plan):
 with pytest.raises(OperationError,match='Invalid PCB plan'):export({'components':[],'nets':[]},plan)

def test_symbol_library_paths_are_not_filesystem_paths():
 from app.engine import load_library
 with pytest.raises(OperationError,match='Invalid symbol library'):load_library('../outside')

def test_installed_footprint_catalog_returns_native_pad_numbers():
 try:footprints.library_root()
 except OperationError:pytest.skip('Native footprint library required')
 identifier='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'
 assert identifier in footprints.search(identifier)
 assert footprints.details(identifier)['pads']==['1','2']
