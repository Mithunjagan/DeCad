"""Permission, stale-source, mapping and provider boundaries of unified reuse."""
import hashlib
import json
import os
from pathlib import Path
import httpx
import pytest
from app.component_library import ComponentLibrary
from app.component_providers import acquire, configure
from app.engine import OperationError

SYMBOL='''(kicad_symbol_lib (version 20231120) (generator "test")
 (symbol "TwoPin" (property "MPN" "TEST-001") (symbol "TwoPin_1_1"
 (pin passive line (at -5.08 0 0) (length 2.54) (name "A") (number "1"))
 (pin passive line (at 5.08 0 180) (length 2.54) (name "B") (number "2")))))'''
FOOTPRINT='''(footprint "TwoPad" (version 20240108) (layer "F.Cu")
 (pad "1" smd rect (at -2 0) (size 1.2 1.4) (layers "F.Cu"))
 (pad "2" smd rect (at 2 0) (size 1.2 1.4) (layers "F.Cu")))'''
POLICY={'name':'CC0-1.0','allow_import':True,'allow_redistribute':True}


@pytest.fixture
def assets(tmp_path):
    source=tmp_path/'original';source.mkdir()
    (source/'Test.kicad_sym').write_text(SYMBOL)
    (source/'Test.kicad_mod').write_text(FOOTPRINT)
    library=ComponentLibrary(tmp_path/'workspace')
    key=library.configure(source,source_license=POLICY)
    assert not library.scan(key)['errors']
    symbol=library.search('TEST-001')[0]
    footprint=library.search('TwoPad')[0]
    return library,source,key,symbol,footprint


def test_unknown_permissions_are_metadata_only_and_root_removal_is_readonly(assets):
    library,source,key,_,_=assets
    original={p.name:p.read_bytes() for p in source.iterdir()}
    library.configure(source,source_license={'name':'Unknown','allow_import':True,'allow_redistribute':True})
    library.scan(key)
    symbol=library.search('TwoPin')[0]
    assert not symbol['pins'] and not symbol['source_license']['allow_import']
    with pytest.raises(OperationError,match='license'):library.get(symbol['id'],True)
    library.remove_root(key)
    assert not library.search('')
    assert original=={p.name:p.read_bytes() for p in source.iterdir()}


def test_pin_pad_mismatch_cannot_be_cached(assets):
    library,source,key,symbol,footprint=assets
    assert library.validate_pair(symbol['id'],footprint['id'])['cached']
    (source/'Test.kicad_mod').write_text(FOOTPRINT.replace('(pad "2"','(pad "3"'))
    library.scan(key)
    result=library.validate_pair(symbol['id'],footprint['id'])
    assert not result['cached'] and result['validation']['pin_to_pad']=='mismatch'
    assert library.verified(symbol['id']) is None


def test_same_stat_content_change_invalidates_cache_and_reindexes(assets):
    library,source,key,symbol,footprint=assets
    library.validate_pair(symbol['id'],footprint['id'])
    path=source/'Test.kicad_mod';stat=path.stat()
    path.write_text(path.read_text().replace('1.2 1.4','1.3 1.4'))
    os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert path.stat().st_size==stat.st_size
    assert library.verified(symbol['id']) is None
    with pytest.raises(OperationError,match='changed'):library.get(footprint['id'],True)
    library.scan(key)
    assert library.get(footprint['id'],True)['pads'][0]['width']==1.3


def test_continuation_crosses_directory_sort_boundaries(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'a').mkdir()
    (source/'z.kicad_mod').write_text(FOOTPRINT)
    (source/'a'/'first.kicad_mod').write_text(FOOTPRINT)
    library=ComponentLibrary(tmp_path/'workspace');key=library.configure(source,source_license=POLICY)
    first=library.scan(key,max_files=1)
    assert not first['complete'] and first['cursor']=='z.kicad_mod'
    second=library.scan(key,max_files=1,after=first['cursor'])
    assert second['complete'] and len(library.search('TwoPad'))==2


def test_bad_dimensions_and_revoked_permission_reject_reuse(assets):
    library,source,key,symbol,footprint=assets
    (source/'Test.kicad_mod').write_text(FOOTPRINT.replace('1.2 1.4','nan 1.4'))
    library.scan(key)
    assert not library.validate_pair(symbol['id'],footprint['id'])['cached']
    library.configure(source,source_license={'name':'CC0-1.0','allow_import':False})
    library.scan(key)
    with pytest.raises(OperationError):library.get(symbol['id'],True)


def test_linked_footprint_export_permission_is_enforced(assets):
    library,source,key,symbol,footprint=assets
    separate=source.parent/'private';separate.mkdir()
    (separate/'Private.kicad_mod').write_text(FOOTPRINT)
    private=library.configure(separate,source_license={'name':'Private use permission','allow_import':True})
    library.scan(private)
    private_fp=next(c for c in library.search('TwoPad') if Path(c['original_library_path']).parent==separate)
    library.validate_pair(symbol['id'],private_fp['id'])
    with pytest.raises(OperationError,match='Linked footprint'):library.export(symbol['id'],'internal')
    with pytest.raises(OperationError,match='no verified exporter'):library.export(symbol['id'],'allegro')


def test_authorized_provider_download_is_hashed_then_imported(tmp_path):
    library=ComponentLibrary(tmp_path/'workspace')
    configure(library,'Test provider','https://library.example/api',True,POLICY)
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        if request.url.path.endswith('/search'):
            return httpx.Response(200,json={'items':[{'assets':[{'url':'assets/test.kicad_sym','sha256':hashlib.sha256(SYMBOL.encode()).hexdigest()}]}]})
        return httpx.Response(200,content=SYMBOL.encode())
    result=acquire(library,'TEST-001',transport=httpx.MockTransport(respond))
    assert result[0]['downloaded']==1 and len(calls)==2
    assert library.search('TEST-001')[0]['pins'][1]['number']=='2'


@pytest.mark.parametrize('bad_asset',[{'url':'https://elsewhere.example/part.kicad_sym'},
                                      {'url':'assets/test.kicad_sym','sha256':'bad'}])
def test_provider_origin_and_integrity_boundaries(tmp_path,bad_asset):
    library=ComponentLibrary(tmp_path/'workspace')
    configure(library,'Test provider','https://library.example/api',True,POLICY)
    def respond(request):
        return httpx.Response(200,json={'items':[{'assets':[bad_asset]}]}) if request.url.path.endswith('/search') else httpx.Response(200,content=SYMBOL.encode())
    result=acquire(library,'TEST-001',transport=httpx.MockTransport(respond))
    assert result[0]['status']=='failed' and not library.search('')
    assert not list(library.root.rglob('*.kicad_sym'))


def test_provider_without_authorization_never_uses_network(tmp_path):
    library=ComponentLibrary(tmp_path/'workspace')
    configure(library,'Disabled','https://library.example/api',False,POLICY)
    def unexpected(request):raise AssertionError('Unauthorized network request')
    result=acquire(library,'TEST-001',transport=httpx.MockTransport(unexpected))
    assert 'permission missing' in result[0]['status']


def test_kicad_and_allegro_discovery_work_without_capture(assets,monkeypatch,tmp_path):
    from app import orcad_capture as oc
    from app.component_library import discover,support_status
    library,source,key,symbol,footprint=assets
    monkeypatch.setattr(oc,'orcad_root',lambda:None)
    allegro=tmp_path/'allegro'
    symbols=allegro/'share/pcb/pcb_lib/symbols';symbols.mkdir(parents=True)
    monkeypatch.setenv('ALLEGRO_ROOT',str(allegro))
    assert any(r['path']==str(symbols.resolve()) and r['ecosystem']=='Allegro' for r in discover())
    assert all(not f['native_available'] for f in support_status() if f['requires_native'])
    assert library.validate_pair(symbol['id'],footprint['id'])['cached']
    content,extension=library.export(symbol['id'],'kicad')
    assert extension=='.kicad_sym' and b'TwoPin' in content
