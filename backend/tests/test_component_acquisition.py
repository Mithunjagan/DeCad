"""Find-and-add acceptance without image recognition or training."""
import json
from pathlib import Path
import httpx
import pytest
from test_component_boundaries import assets,SYMBOL,FOOTPRINT,POLICY
from app import component_acquisition as acq
from app.component_library import ComponentLibrary
from app.component_formats import symbol_records


def no_installed(monkeypatch):
    from app import component_native
    monkeypatch.setattr(acq,'kicad_paths',lambda query:[])
    monkeypatch.setattr(acq,'footprint_paths',lambda query:[])
    monkeypatch.setattr(component_native,'capture_runtime',lambda:{'supported':False})


def test_exact_local_acquisition_validates_and_reuses_cache(assets,monkeypatch):
    library,source,key,symbol,footprint=assets
    (source/'Test.kicad_sym').write_text(SYMBOL.replace('(property "MPN"', '(property "Footprint" "Test:TwoPad") (property "MPN"'))
    library.scan(key);no_installed(monkeypatch)
    result=acq.acquire_component(library,'TEST-001',False)
    assert result['status']=='ready' and result['component']['validation']['pin_to_pad']=='verified'
    second=acq.acquire_component(library,'TEST-001',False)
    assert second['trace'][-1]['stage']=='verified cache'


def test_external_provider_supplies_symbol_and_footprint(tmp_path,monkeypatch):
    from app.component_providers import configure
    library=ComponentLibrary(tmp_path/'workspace');no_installed(monkeypatch)
    configure(library,'Authorized','https://provider.example/api',True,POLICY)
    symbol=SYMBOL.replace('(property "MPN"', '(property "Footprint" "Test:TwoPad") (property "MPN"')
    def response(request):
        if request.url.path.endswith('/search'):
            return httpx.Response(200,json={'items':[{'assets':[{'url':'two.kicad_sym'},{'url':'two.kicad_mod'}]}]})
        return httpx.Response(200,content=(FOOTPRINT if request.url.path.endswith('.kicad_mod') else symbol).encode())
    result=acq.acquire_component(library,'TEST-001',True,transport=httpx.MockTransport(response))
    assert result['status']=='ready' and result['component']['cached']


def test_modular_kicad_inheritance_and_dependency_change(tmp_path):
    folder=tmp_path/'Test.kicad_symdir';folder.mkdir()
    parent=folder/'Parent.kicad_sym';parent.write_text(SYMBOL.replace('TwoPin','Parent'))
    child=folder/'Child.kicad_sym';child.write_text('(kicad_symbol_lib (version 20251024) (symbol "Child" (extends "Parent")))')
    library=ComponentLibrary(tmp_path/'workspace')
    record=library.index_file(child,POLICY)[0]
    assert {p['number'] for p in record['pins']}=={'1','2'} and record['dependencies']
    parent.write_text(parent.read_text().replace('5.08','6.08'))
    with pytest.raises(ValueError,match='Inherited symbol source changed'):library.get(record['id'],True)
    root=next(r for r in library.roots() if r['path']==str(folder.resolve()))
    assert library.scan(root['id'])['indexed']>=1
    assert library.get(record['id'],True)['pins'][0]['x']==-6.08


def test_public_kicad_fallback_fetches_inheritance_and_real_footprint(tmp_path,monkeypatch):
    library=ComponentLibrary(tmp_path/'workspace');no_installed(monkeypatch)
    monkeypatch.setattr(acq,'catalog_ids',lambda query:['Test:TwoPin'])
    license_text='KiCad Libraries License\nCC-BY-SA 4.0\nKiCad test license fixture'
    child='(kicad_symbol_lib (version 20251024) (symbol "TwoPin" (extends "Parent") (property "Footprint" "Test:TwoPad")))'
    def respond(request):
        name=request.url.path.rsplit('/',1)[-1]
        if name=='LICENSE.md':data=license_text
        elif name=='TwoPin.kicad_sym':data=child
        elif name=='Parent.kicad_sym':data=SYMBOL.replace('TwoPin','Parent')
        elif name=='TwoPad.kicad_mod':data=FOOTPRINT
        else:return httpx.Response(404)
        return httpx.Response(200,content=data.encode())
    result=acq.acquire_component(library,'Test:TwoPin',True,transport=httpx.MockTransport(respond))
    assert result['status']=='ready',result
    content,ext=library.export(result['component']['id'],'kicad')
    assert ext=='.zip'
    import io,zipfile
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert {'LICENSE.md','ATTRIBUTION.json','component.kicad_sym'}<=set(archive.namelist())


def test_unresolved_and_missing_footprint_are_explicit(assets,monkeypatch):
    library,source,key,symbol,footprint=assets;no_installed(monkeypatch)
    result=acq.acquire_component(library,'TEST-001',False)
    assert result['status']=='needs_footprint'
    result=acq.acquire_component(library,'NO-SUCH-COMPONENT',False)
    assert result['status']=='not_found' and not result['items']
