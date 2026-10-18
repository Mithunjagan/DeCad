"""Workspace-local, license-aware component database with lazy native extraction.

Installation directories are read only. SQLite and all generated exports live
under the workspace's .libraries/unified directory, never beside source assets.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from .component_formats import base_record, footprint_record, kicad_symbol, symbol_records, validate
from .engine import OperationError
from .sexpr import dump

FORMATS = {
    '.kicad_sym': ('KiCad', 'symbol', 'symbols, modular inheritance, units, pins and graphics', ['20231120','20251024']),
    '.kicad_mod': ('KiCad', 'footprint', 'pads, geometry and model references', ['20240108','20260206']),
    '.olb': ('OrCAD Capture', 'symbol_library', 'native package index; on-demand pins and line/box graphics', ['26.1']),
    '.dsn': ('OrCAD Capture', 'design', 'native schematic drawing and pins; not Specctra routing DSN', ['26.1']),
    '.opj': ('OrCAD Capture', 'project', 'text project references', ['26.1']),
    '.dra': ('Allegro', 'footprint', 'catalog only; geometry adapter not verified', []),
    '.psm': ('Allegro', 'footprint', 'catalog only; compiled geometry adapter not verified', []),
    '.pad': ('Allegro', 'padstack', 'catalog only; pad geometry adapter not verified', []),
    '.brd': ('Allegro', 'board', 'catalog only; board geometry adapter not verified', []),
    '.step': ('Mechanical', 'model', 'model reference only; no solid geometry parser', []),
    '.stp': ('Mechanical', 'model', 'model reference only; no solid geometry parser', []),
    '.wrl': ('Mechanical', 'model', 'model reference only; no mesh geometry parser', []),
}


def support_status():
    from .component_native import capture_runtime
    runtime = capture_runtime()
    return [dict(extension=ext, ecosystem=v[0], kind=v[1], support=v[2], tested_versions=v[3],
                 requires_native=ext in ('.olb', '.dsn'), native_available=runtime['supported'] if ext in ('.olb', '.dsn') else None,
                 installed_version=runtime['version'] if ext in ('.olb','.dsn') else None,
                 export='native package OLB, independently reopened; KiCad for complete line/box symbols' if ext=='.olb' else
                        'KiCad library' if ext in ('.kicad_sym', '.kicad_mod') else
                        'Capture DSN through existing verified design exporter' if ext == '.dsn' else 'not implemented')
            for ext, v in FORMATS.items()]


def discover():
    """Accessible standard locations, environment overrides and shipped libraries."""
    from . import engine, orcad_capture as oc
    paths = []
    def add(path, ecosystem):
        if path and Path(path).is_dir():
            resolved = str(Path(path).resolve())
            if not any(p['path'].casefold() == resolved.casefold() for p in paths):
                paths.append(dict(path=resolved, ecosystem=ecosystem))
    add(engine.library_dir(), 'KiCad')
    for key, val in os.environ.items():
        if re.match(r'KICAD(?:\d+)?_(?:SYMBOL|FOOTPRINT|3DMODEL)_DIR$', key):
            add(val, 'KiCad')
    cli = os.getenv('KICAD_CLI')
    if cli:
        for folder in ('symbols', 'footprints', '3dmodels'):
            add(Path(cli).parent.parent / 'share/kicad' / folder, 'KiCad')
    for base in (Path('D:/KICAD'), Path('/usr/share/kicad'), Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport')):
        for folder in ('symbols', 'footprints', '3dmodels'):
            add(base / folder, 'KiCad')
            add(base / 'share/kicad' / folder, 'KiCad')
    program_files = Path(os.getenv('ProgramFiles', 'C:/Program Files'))
    for base in (program_files / 'KiCad').glob('*') if (program_files/'KiCad').is_dir() else []:
        for folder in ('symbols', 'footprints', '3dmodels'):
            add(base / 'share/kicad' / folder, 'KiCad')
    # Allegro can be installed without Capture's DLL. Directory discovery must
    # remain independent of the schematic automation availability check.
    cadence_roots = [oc.orcad_root(),os.getenv('CDSROOT'),os.getenv('ORCAD_ROOT'),os.getenv('ALLEGRO_ROOT'),Path('D:/')]
    cadence_base = Path('C:/Cadence')
    if cadence_base.is_dir():cadence_roots.extend(cadence_base.iterdir())
    for root in cadence_roots:
        if root:
            root = Path(root)
            add(root / 'tools/capture/library', 'OrCAD Capture')
            add(root / 'share/pcb/pcb_lib/symbols', 'Allegro')
            add(root / 'share/pcb/pcb_lib/padstacks', 'Allegro')
    # Common Allegro search paths may also point to team libraries.
    for key in ('PSMPATH', 'PADPATH'):
        for entry in os.getenv(key, '').split(os.pathsep):
            add(entry, 'Allegro')
    return paths


def identifier(*parts):
    return hashlib.sha256('\0'.join(map(str, parts)).encode()).hexdigest()[:32]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def license_policy(value=None):
    value = value or {}
    name = str(value.get('name', 'Unknown')).strip()[:300] or 'Unknown'
    known = name.casefold() not in ('unknown', 'unspecified', '')
    return dict(name=name, allow_import=known and value.get('allow_import') is True,
                allow_redistribute=known and value.get('allow_redistribute') is True,
                evidence=str(value.get('evidence', ''))[:2000],
                license_text=str(value.get('license_text',''))[:100000],
                attribution=str(value.get('attribution',''))[:4000])


class ComponentLibrary:
    def __init__(self, workspace):
        self.root = Path(workspace) / '.libraries/unified'
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'components.sqlite3'
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS roots(id TEXT PRIMARY KEY,path TEXT UNIQUE,ecosystem TEXT,license TEXT);
              CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,root TEXT,path TEXT UNIQUE,size INTEGER,mtime INTEGER,sha256 TEXT,status TEXT,detail TEXT);
              CREATE TABLE IF NOT EXISTS components(id TEXT PRIMARY KEY,asset TEXT,name TEXT,kind TEXT,format TEXT,mpn TEXT,description TEXT,record TEXT);
              CREATE INDEX IF NOT EXISTS component_name ON components(name COLLATE NOCASE);
              CREATE INDEX IF NOT EXISTS component_asset ON components(asset);
              CREATE TABLE IF NOT EXISTS verified(id TEXT PRIMARY KEY,signature TEXT,record TEXT);
            ''')

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def roots(self):
        with self.connect() as db:
            return [dict(id=r['id'], path=r['path'], ecosystem=r['ecosystem'], source_license=json.loads(r['license']))
                    for r in db.execute('SELECT * FROM roots ORDER BY ecosystem,path')]

    def configure(self, path, ecosystem='Mixed', source_license=None):
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            raise OperationError('Library directory does not exist or is inaccessible.')
        key = identifier(str(path).casefold())
        policy = license_policy(source_license)
        with self.connect() as db:
            old = db.execute('SELECT * FROM roots WHERE id=?', (key,)).fetchone()
            if old and old['license'] != json.dumps(policy):
                db.execute('DELETE FROM verified WHERE id IN (SELECT c.id FROM components c JOIN assets a ON a.id=c.asset WHERE a.root=?)', (key,))
                db.execute('DELETE FROM components WHERE asset IN (SELECT id FROM assets WHERE root=?)', (key,))
                db.execute('DELETE FROM assets WHERE root=?', (key,))
            db.execute('INSERT OR REPLACE INTO roots VALUES(?,?,?,?)', (key, str(path), ecosystem, json.dumps(policy)))
        return key

    def index_file(self, path, source_license=None, ecosystem='Mixed'):
        """Index one requested asset without scanning unrelated library files."""
        path = Path(path).resolve()
        if not path.is_file() or path.suffix.lower() not in FORMATS:
            raise OperationError('Unsupported or missing component asset.')
        configs = [r for r in self.roots() if path.is_relative_to(Path(r['path']))]
        config = max(configs,key=lambda r:len(r['path'])) if configs else None
        if config:
            key,policy = config['id'],config['source_license']
        else:
            policy = license_policy(source_license)
            key = self.configure(path.parent,ecosystem,policy)
        self._index(path,key,policy,identifier(str(path).casefold()),path.stat())
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT record FROM components WHERE asset=?',
                    (identifier(str(path).casefold()),))]

    def remove_root(self, key):
        with self.connect() as db:
            db.execute('DELETE FROM verified WHERE id IN (SELECT c.id FROM components c JOIN assets a ON a.id=c.asset WHERE a.root=?)', (key,))
            db.execute('DELETE FROM components WHERE asset IN (SELECT id FROM assets WHERE root=?)', (key,))
            db.execute('DELETE FROM assets WHERE root=?', (key,))
            db.execute('DELETE FROM roots WHERE id=?', (key,))

    def _save(self, db, asset, record, policy):
        record['source_license'] = policy
        record['id'] = identifier(asset, record['kind'], record['name'])
        db.execute('INSERT OR REPLACE INTO components VALUES(?,?,?,?,?,?,?,?)',
                   (record['id'], asset, record['name'], record['kind'], record['source_format'],
                    record['manufacturer_part_number'], record['description'], json.dumps(record)))
        return record

    def scan(self, key, max_files=2000, after=''):
        config = next((r for r in self.roots() if r['id'] == key), None)
        if not config:
            raise OperationError('Unknown library location.')
        path, policy = Path(config['path']), config['source_license']
        if not path.is_dir():
            raise OperationError('Library source directory is unavailable.')
        result = dict(indexed=0, unchanged=0, errors=[], cursor=None, complete=True)
        count, seen, started = 0, set(), not after
        # Deterministic traversal supports bounded continuation on low-memory machines.
        for directory, folders, files in os.walk(path, followlinks=False):
            folders[:] = sorted(d for d in folders if not d.startswith('.') and not (Path(directory)/d).is_symlink())
            for filename in sorted(files):
                file = Path(directory)/filename
                if file.suffix.lower() not in FORMATS or file.is_symlink():
                    continue
                relative = str(file.relative_to(path)).replace('\\', '/')
                seen.add(str(file))
                if not started:
                    if relative == after:
                        started = True
                    continue
                if count >= max_files:
                    result.update(complete=False)
                    return result
                count += 1
                result['cursor'] = relative
                asset = identifier(str(file).casefold())
                try:
                    stat = file.stat()
                    with self.connect() as db:
                        old = db.execute('SELECT * FROM assets WHERE id=?', (asset,)).fetchone()
                        dependencies = [json.loads(r[0]).get('dependencies',{}) for r in
                                        db.execute('SELECT record FROM components WHERE asset=?',(asset,))] if old else []
                    dependencies_current = all(Path(p).is_file() and digest(p)==sha for group in dependencies for p,sha in group.items())
                    if (old and old['size'] == stat.st_size and old['mtime'] == stat.st_mtime_ns
                        and old['status'] != 'error' and old['detail'] == self._adapter(path=file)
                        and dependencies_current and old['sha256'] == digest(file)):
                        result['unchanged'] += 1
                        continue
                    self._index(file, key, policy, asset, stat)
                    result['indexed'] += 1
                except (OSError, ValueError, RuntimeError) as exc:
                    # Invalidate stale records, including on loss of native availability.
                    with self.connect() as db:
                        db.execute('DELETE FROM verified WHERE id IN (SELECT id FROM components WHERE asset=?)', (asset,))
                        db.execute('DELETE FROM components WHERE asset=?', (asset,))
                        db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?,?,?)',
                                   (asset,key,str(file),0,0,'','error',str(exc)[:2000]))
                    result['errors'].append(dict(path=str(file), error=str(exc)[:500]))
        if not started:
            raise OperationError('Scan cursor no longer exists. Restart the scan.')
        # Only full traversal can identify removed files. Continuations don't prune.
        if not after:
            with self.connect() as db:
                for row in db.execute('SELECT id,path FROM assets WHERE root=?', (key,)).fetchall():
                    if row['path'] not in seen:
                        db.execute('DELETE FROM verified WHERE id IN (SELECT id FROM components WHERE asset=?)', (row['id'],))
                        db.execute('DELETE FROM components WHERE asset=?', (row['id'],))
                        db.execute('DELETE FROM assets WHERE id=?', (row['id'],))
        result['cursor'] = None
        return result

    def _adapter(self, path):
        from .component_native import capture_runtime
        return 'component-v1-native='+str(capture_runtime() if path.suffix.lower() in ('.olb','.dsn') else False)

    def _index(self, path, root, policy, asset, stat):
        ext = path.suffix.lower()
        metadata = not policy['allow_import']
        if ext == '.kicad_sym':
            records = symbol_records(path, metadata)
        elif ext == '.kicad_mod':
            records = [footprint_record(path, metadata)]
        elif ext == '.olb':
            from .component_native import capture_packages,capture_runtime
            runtime = capture_runtime()
            if runtime['supported']:
                records = []
                for name, footprint in capture_packages(path):
                    record = base_record(name, 'symbol', path, 'Capture API '+runtime['version'])
                    record['footprint_identifier'] = footprint
                    records.append(record)
            else:
                records = [base_record(path.stem, 'symbol_library', path)]
        elif ext == '.opj':
            from .component_native import project_metadata
            records = [project_metadata(path)]
        else:
            record = base_record(path.stem, FORMATS[ext][1], path)
            record['validation']['issues'] = [FORMATS[ext][2]]
            if record['kind'] == 'model':
                record['models'] = [dict(path=str(path), source='independent asset')]
            records = [record]
        sha = digest(path)
        with self.connect() as db:
            db.execute('DELETE FROM verified WHERE id IN (SELECT id FROM components WHERE asset=?)', (asset,))
            db.execute('DELETE FROM components WHERE asset=?', (asset,))
            db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?,?,?)',
                       (asset,root,str(path),stat.st_size,stat.st_mtime_ns,sha,'indexed',self._adapter(path)))
            for record in records:
                self._save(db, asset, record, policy)

    def search(self, query='', limit=50):
        query = query.strip()[:200]
        # Escape SQL wildcard characters: component names are literal search text.
        pattern = '%' + query.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        with self.connect() as db:
            rows = db.execute("SELECT record FROM components WHERE name LIKE ? ESCAPE '!' OR mpn LIKE ? ESCAPE '!' OR description LIKE ? ESCAPE '!' ORDER BY CASE WHEN name=? COLLATE NOCASE THEN 0 ELSE 1 END,name LIMIT ?",
                              (pattern,pattern,pattern,query,max(1,min(int(limit),200)))).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, key, materialize=False):
        with self.connect() as db:
            row = db.execute('SELECT c.*,a.size,a.mtime,a.sha256,a.path,a.root FROM components c JOIN assets a ON a.id=c.asset WHERE c.id=?', (key,)).fetchone()
        if not row:
            raise OperationError('Component is not indexed.')
        path = Path(row['path'])
        try:
            stat = path.stat()
        except OSError as exc:
            raise OperationError('Component source is unavailable; reindex this location.') from exc
        if stat.st_size != row['size'] or stat.st_mtime_ns != row['mtime'] or (materialize and digest(path) != row['sha256']):
            raise OperationError('Component source changed; reindex before reuse.')
        record = json.loads(row['record'])
        if materialize:
            for dependency,expected in record.get('dependencies',{}).items():
                if not Path(dependency).is_file() or digest(dependency)!=expected:
                    raise OperationError('Inherited symbol source changed; reindex before reuse.')
        if materialize and not record['source_license']['allow_import']:
            raise OperationError('Source license has no recorded permission for import. Configure its license first.')
        if materialize and record['validation']['status'] == 'metadata_only' and record['source_format'] == '.olb':
            from .component_native import capture_symbol
            record = capture_symbol(path, record['name'])
            with self.connect() as db:
                record = self._save(db, row['asset'], record, json.loads(row['record'])['source_license'])
        return record

    def verified(self, key):
        with self.connect() as db:
            cached = db.execute('SELECT * FROM verified WHERE id=?', (key,)).fetchone()
        if not cached:
            return None
        record = json.loads(cached['record'])
        sources = record['validation']['sources']
        try:
            current = [self.get(k, True) for k in sources]
            signature = identifier(*(digest(Path(c['original_library_path'])) for c in current))
            if signature == cached['signature']:
                record['cached'] = True
                return record
        except (OperationError, OSError):
            pass
        with self.connect() as db:
            db.execute('DELETE FROM verified WHERE id=?', (key,))
        return None

    def resolve(self, query, search_installed=False, external=False):
        """Local-first resolver; discovery and downloads run only when requested."""
        trace = [dict(stage='unified database', matches=len(self.search(query)))]
        matches = self.search(query)
        if not matches and search_installed:
            existing = {r['path']: r for r in self.roots()}
            for ecosystem in ('KiCad', 'OrCAD Capture', 'Allegro'):
                for location in discover():
                    if location['ecosystem'] != ecosystem:
                        continue
                    key = existing.get(location['path'], {}).get('id') or self.configure(**location)
                    scan = self.scan(key)
                    trace.append(dict(stage=ecosystem, **scan))
                    matches = self.search(query)
                    if matches:
                        break
                if matches:
                    break
        for component in matches:
            cached = self.verified(component['id'])
            if cached:
                trace.append(dict(stage='verified cache', component=component['id']))
                return dict(items=[cached], trace=trace)
        if not matches and external:
            from .component_providers import acquire
            trace += acquire(self, query)
            matches = self.search(query)
        return dict(items=matches, trace=trace,
                    limitation='Review source license and validate a symbol/footprint pair before verified caching and placement.')

    def validate_pair(self, key, footprint_key):
        record, footprint = self.get(key, True), self.get(footprint_key, True)
        if record['kind'] != 'symbol' or footprint['kind'] != 'footprint':
            raise OperationError('Choose an electrical symbol and a physical footprint.')
        record['pads'] = footprint['pads']
        record['footprint_geometry'] = footprint['footprint_geometry']
        record['kicad_footprint'] = footprint.get('kicad_footprint')
        record['models'] += footprint['models']
        record['footprint_identifier'] = footprint['footprint_identifier']
        record['linked_sources'] = [{k:footprint[k] for k in ('id','original_library_path','source_license','source_format','source_version')}]
        record['validation'] = validate(record, footprint)
        record['validation']['sources'] = [key, footprint_key]
        if record['validation']['status'] == 'structurally_valid' and record['validation']['pin_to_pad'] == 'verified':
            signature = identifier(digest(Path(record['original_library_path'])), digest(Path(footprint['original_library_path'])))
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO verified VALUES(?,?,?)', (key,signature,json.dumps(record)))
            record['cached'] = True
        else:
            with self.connect() as db:
                db.execute('DELETE FROM verified WHERE id=?', (key,))
            record['cached'] = False
        return record

    def export(self, key, target='internal'):
        record = self.get(key, True)
        if not record['source_license']['allow_redistribute']:
            raise OperationError('Source license has no recorded permission for redistribution/export.')
        if target == 'internal':
            record = self.verified(key) or record
            if any(not source['source_license']['allow_redistribute'] for source in record.get('linked_sources', [])):
                raise OperationError('Linked footprint license has no recorded permission for redistribution/export.')
            return json.dumps(record, indent=2).encode(), '.json'
        if target == 'orcad' and record['source_format'] == '.olb' and record['kind'] == 'symbol':
            from .component_native import capture_export
            return capture_export(record,self.root/'native-export'), '.olb'
        if target == 'kicad':
            if record['validation']['status'] != 'structurally_valid':
                raise OperationError('KiCad export requires a structurally valid, complete component.')
            if record['kind'] == 'symbol':
                return self._licensed_export(record,dump(kicad_symbol(record)).encode(),'.kicad_sym')
            if record.get('kicad_footprint'):
                return self._licensed_export(record,record['kicad_footprint'].encode(),'.kicad_mod')
        raise OperationError('This component/target has no verified exporter. Allegro binary export is not implemented; use the native Capture design workflow for supported DSN exports.')

    def _licensed_export(self, record, data, extension):
        policy=record['source_license']
        if 'CC-BY' not in policy['name'].upper():return data,extension
        if not policy.get('license_text') or not policy.get('attribution'):
            raise OperationError('Library redistribution requires the source license text and attribution.')
        result=io.BytesIO()
        with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('component'+extension,data)
            archive.writestr('LICENSE.md',policy['license_text'])
            archive.writestr('ATTRIBUTION.json',json.dumps({'attribution':policy['attribution'],
                'original_library_path':record['original_library_path'],'source_license':policy},indent=2))
        return result.getvalue(),'.zip'
