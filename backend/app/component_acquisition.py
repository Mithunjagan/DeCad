"""Find an exact part, acquire real assets, validate its footprint, and cache it.

No substitutions or invented packages. Public KiCad fallback uses a pinned
official library release; other providers must be explicitly configured.
"""
import json
import re
import sqlite3
import urllib.parse
from pathlib import Path
import httpx
from .component_library import discover, digest
from .engine import OperationError

PROJECT = Path(__file__).resolve().parents[2]
PUBLIC_VERSION = '10.0.5'
PUBLIC_BASE = 'https://gitlab.com/kicad/libraries/'


def exact(records, query):
    name = query.rsplit(':',1)[-1].casefold()
    return [r for r in records if r['kind']=='symbol' and
            (r['name'].casefold()==name or r.get('manufacturer_part_number','').casefold()==query.casefold()) and
            (':' not in query or r.get('symbol_identifier','').casefold()==query.casefold())]


def catalog_ids(query):
    ids = [query] if ':' in query else []
    database = PROJECT/'libraries/index/components.db'
    if database.is_file():
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
            ids += [r[0] for r in db.execute('SELECT lib_id FROM symbols WHERE name=? COLLATE NOCASE OR lib_id=? COLLATE NOCASE LIMIT 20',
                                            (query,query))]
    return list(dict.fromkeys(ids))


def policy_for(path):
    """Only an actual license in the source tree establishes automatic rights."""
    path = Path(path).resolve()
    for parent in list(path.parents)[:5]:
        license_file = parent/'LICENSE.md'
        if not license_file.is_file():continue
        text = license_file.read_text(encoding='utf-8-sig')
        if 'KiCad Libraries License' in text and 'CC-BY-SA 4.0' in text:
            return dict(name='CC-BY-SA-4.0 with KiCad libraries exception',allow_import=True,allow_redistribute=True,
                        evidence=str(license_file),license_text=text,attribution='KiCad library contributors')
    return None


def kicad_paths(query):
    name = query.rsplit(':',1)[-1]
    if any(c in name for c in '/\\') or '..' in name:return []
    roots = [Path(r['path']) for r in discover() if r['ecosystem']=='KiCad']
    bundled = PROJECT/'libraries/kicad/official/symbols'
    if bundled.is_dir() and bundled not in roots:roots.append(bundled)
    result = []
    ids = catalog_ids(query)
    for root in roots:
        for symbol_id in ids:
            if ':' not in symbol_id:continue
            library,symbol = symbol_id.split(':',1)
            if any(c in library+symbol for c in '/\\') or '..' in library+symbol:continue
            for candidate in (root/(library+'.kicad_symdir')/(symbol+'.kicad_sym'),root/(library+'.kicad_sym')):
                if candidate.is_file() and candidate not in result:result.append(candidate)
        if not result:
            result += [p for p in root.glob('*.kicad_symdir/'+name+'.kicad_sym') if p.is_file()]
    return result


def footprint_paths(identifier):
    if ':' not in identifier:return []
    library,name = identifier.split(':',1)
    if any(c in library+name for c in '/\\') or '..' in library+name:return []
    roots = [Path(r['path']) for r in discover() if r['ecosystem']=='KiCad']
    roots.append(PROJECT/'libraries/kicad/official/footprints')
    return list(dict.fromkeys(root/(library+'.pretty')/(name+'.kicad_mod') for root in roots
                             if (root/(library+'.pretty')/(name+'.kicad_mod')).is_file()))


def read_public(client, repository, relative):
    url = PUBLIC_BASE+repository+'/-/raw/'+PUBLIC_VERSION+'/'+urllib.parse.quote(relative,safe='/')
    data = bytearray()
    with client.stream('GET',url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data)>20*1024*1024:raise OperationError('Public library asset exceeds 20 MB.')
    return bytes(data),url


def public_kicad(library, query, trace, transport=None):
    """Known exact library identifiers only; no unbounded web scraping."""
    from .sexpr import parse,children,child
    ids = catalog_ids(query)
    if not ids:
        trace.append(dict(stage='public KiCad',status='No exact library identifier in the local catalog; configured providers may supply this part.'))
        return
    with httpx.Client(timeout=30,follow_redirects=False,transport=transport) as client:
        for symbol_id in ids[:5]:
            try:
                lib,name = symbol_id.split(':',1)
                if any(c in lib+name for c in '/\\') or '..' in lib+name:continue
                license_bytes,license_url=read_public(client,'kicad-symbols','LICENSE.md')
                text=license_bytes.decode('utf-8-sig')
                if 'KiCad Libraries License' not in text or 'CC-BY-SA 4.0' not in text:
                    raise OperationError('Upstream license was not recognized; assets were not imported.')
                folder=library.root/'public-kicad'/PUBLIC_VERSION/'symbols'
                symdir=folder/(lib+'.kicad_symdir');symdir.mkdir(parents=True,exist_ok=True)
                pending=[name];seen=set()
                while pending:
                    current=pending.pop()
                    if current in seen or len(seen)>=16:raise OperationError('Unresolved or cyclic public symbol inheritance.')
                    seen.add(current)
                    if any(c in current for c in '/\\') or '..' in current:raise OperationError('Invalid inherited symbol name.')
                    data,url=read_public(client,'kicad-symbols',f'{lib}.kicad_symdir/{current}.kicad_sym')
                    tree=parse(data.decode('utf-8-sig'))
                    target=symdir/(current+'.kicad_sym')
                    target.write_bytes(data)
                    for symbol in children(tree,'symbol'):
                        parent=child(symbol,'extends')
                        if parent and parent[1] not in seen:pending.append(str(parent[1]))
                (folder/'LICENSE.md').write_bytes(license_bytes)
                policy=dict(name='CC-BY-SA-4.0 with KiCad libraries exception',allow_import=True,allow_redistribute=True,
                            evidence=license_url,license_text=text,attribution='KiCad library contributors')
                library.configure(folder,'Public KiCad',policy)
                records=library.index_file(symdir/(name+'.kicad_sym'),policy,'Public KiCad')
                record=next(r for r in records if r['name']==name)
                fp=record.get('footprint_identifier','')
                if ':' in fp:
                    fp_lib,fp_name=fp.split(':',1)
                    fp_data,_=read_public(client,'kicad-footprints',fp_lib+'.pretty/'+fp_name+'.kicad_mod')
                    fp_license,fp_license_url=read_public(client,'kicad-footprints','LICENSE.md')
                    if 'KiCad Libraries License' not in fp_license.decode():raise OperationError('Footprint license not recognized.')
                    fp_root=library.root/'public-kicad'/PUBLIC_VERSION/'footprints'
                    fp_folder=fp_root/(fp_lib+'.pretty');fp_folder.mkdir(parents=True,exist_ok=True)
                    (fp_root/'LICENSE.md').write_bytes(fp_license)
                    target=fp_folder/(fp_name+'.kicad_mod');target.write_bytes(fp_data)
                    fp_policy={**policy,'license_text':fp_license.decode(),'evidence':fp_license_url}
                    library.configure(fp_root,'Public KiCad',fp_policy)
                    library.index_file(target,fp_policy,'Public KiCad')
                trace.append(dict(stage='public KiCad',status='downloaded',symbol=symbol_id,version=PUBLIC_VERSION))
                return
            except (OSError,ValueError,httpx.HTTPError,StopIteration) as exc:
                trace.append(dict(stage='public KiCad',status='unavailable',symbol=symbol_id,error=type(exc).__name__))


def acquire_component(library, query, external=True, footprint_id=None, transport=None):
    query=query.strip()
    trace=[]
    records=exact(library.search(query.rsplit(':',1)[-1],200),query)
    trace.append(dict(stage='unified database',matches=len(records)))
    for record in records:
        cached=library.verified(record['id'])
        if cached:return dict(status='ready',component=cached,trace=trace+[dict(stage='verified cache',status='reused')])
    # Targeted reads avoid indexing unrelated hundreds of thousands of parts.
    for path in kicad_paths(query):
        try:library.index_file(path,policy_for(path),'KiCad')
        except (OSError,ValueError) as exc:trace.append(dict(stage='installed KiCad',status='unavailable',error=str(exc)[:300]))
    records=exact(library.search(query.rsplit(':',1)[-1],200),query)
    trace.append(dict(stage='installed KiCad',matches=len(records)))
    if not records:
        from . import orcad_capture as oc
        from .component_native import capture_runtime
        if capture_runtime()['supported']:
            try:
                index=oc.library_index(PROJECT/'backend/.state/orcad-lib-index.tsv')
                for path in index.get(query.upper(),[])[:5]:library.index_file(path,policy_for(path),'OrCAD Capture')
            except (OSError,ValueError) as exc:trace.append(dict(stage='installed OrCAD',status='unavailable',error=str(exc)[:300]))
        records=exact(library.search(query.rsplit(':',1)[-1],200),query)
        trace.append(dict(stage='installed OrCAD',matches=len(records)))
    usable=[];issues=[];queried_external=False
    def materialize():
        usable.clear()
        for record in exact(library.search(query.rsplit(':',1)[-1],200),query):
            try:
                detail=library.get(record['id'],True)
                if detail['validation']['status']=='structurally_valid':usable.append(detail)
                else:issues.append(dict(component=record['id'],issues=detail['validation']['issues']))
            except (OSError,ValueError) as exc:issues.append(dict(component=record['id'],error=str(exc)))
    materialize()
    if not usable and external:
        from .component_providers import acquire
        trace+=acquire(library,query,transport)
        queried_external=True
        materialize()
        if not usable:
            public_kicad(library,query,trace,transport)
            materialize()
    for symbol in usable:
        footprints=[library.get(footprint_id,True)] if footprint_id else []
        identifier=symbol.get('footprint_identifier','')
        if not footprints:
            footprints=[r for r in library.search(identifier.rsplit(':',1)[-1],200)
                        if r['kind']=='footprint' and (r.get('footprint_identifier')==identifier
                           or r['name']==identifier.rsplit(':',1)[-1])] if identifier else []
            for path in footprint_paths(identifier):
                try:footprints+=library.index_file(path,policy_for(path),'KiCad')
                except (OSError,ValueError):continue
        for footprint in footprints:
            try:
                result=library.validate_pair(symbol['id'],footprint['id'])
                if result['cached']:
                    return dict(status='ready',component=result,trace=trace+[dict(stage='validation',status='pin/pad mapping verified')])
                issues.append(dict(component=symbol['id'],issues=result['validation']['issues']))
            except (OSError,ValueError) as exc:issues.append(dict(component=symbol['id'],error=str(exc)))
    if external and not queried_external:
        from .component_providers import acquire
        trace+=acquire(library,query,transport)
        public_kicad(library,query,trace,transport)
        result=acquire_component(library,query,False,footprint_id,transport)
        result['trace']=trace+result['trace']
        return result
    status='needs_footprint' if usable else 'needs_license_or_supported_assets' if records else 'not_found'
    return dict(status=status,items=usable or records,trace=trace,issues=issues,
                message='No verified symbol/footprint pair is available. Choose a footprint or configure a permitted asset provider; the project was not changed.')
