"""Workspace library store for OrCAD generation, shared by every project of one workspace.

Holds what a team adds to the tool:
  symbols/     Capture symbol libraries (.OLB), uploaded or extracted from existing designs
  designs/     existing Capture designs (.DSN): kept with a preview; their parts become <name>_parts.OLB
  footprints/  PCB footprints (Allegro / OrCAD PCB .psm .dra .pad ..., KiCad .kicad_mod)
  partmap.json part number / reference / package -> PCB footprint and optional Capture symbol

Generated designs prefer these libraries over the installed ones, and every placed part gets a PCB
Footprint: the part map first, then the library package's own footprint, then a standard footprint
from the OrCAD PCB library chosen by package type and pin count.
"""
import contextvars, csv, io, json, re, shutil, zipfile
from pathlib import Path
from .engine import OperationError

ACTIVE = contextvars.ContextVar('decad_library_store', default=None)

SYMBOL_EXT = {'.olb'}
DESIGN_EXT = {'.dsn'}
FOOTPRINT_EXT = {'.psm', '.dra', '.pad', '.bsm', '.fsm', '.ssm', '.osm', '.mdd', '.kicad_mod'}
MAP_EXT = {'.csv'}
ARCHIVE_EXT = {'.zip'}
ACCEPTED = SYMBOL_EXT | DESIGN_EXT | FOOTPRINT_EXT | MAP_EXT | ARCHIVE_EXT
# Footprint files that describe a placeable footprint (the others are padstacks/shapes it uses).
PLACEABLE = {'.psm', '.dra', '.kicad_mod'}
MAX_ARCHIVE_FILES, MAX_ARCHIVE_BYTES = 5000, 400 * 1024 * 1024


def store(user_root):
    st = Path(user_root) / '.libraries'
    for sub in ('symbols', 'designs', 'footprints'):
        (st / sub).mkdir(parents=True, exist_ok=True)
    return st


def activate(user_root):
    """Use this workspace's libraries for OrCAD work in the current request (and threads it starts)."""
    ACTIVE.set(store(user_root))


def active():
    return ACTIVE.get()


def symbol_libraries(st=None):
    st = st or active()
    return sorted((st / 'symbols').glob('*.olb'), key=lambda p: p.name.lower()) if st else []


def is_user_library(path):
    st = active()
    return bool(st) and Path(path).resolve().parent == (st / 'symbols').resolve()


def safe_name(name):
    name = Path(str(name).replace('\\', '/')).name
    name = re.sub(r'[^A-Za-z0-9 ._+\-()]', '_', name).strip(' .')
    if not name or name.startswith('.'):
        raise OperationError(f'Unusable file name: {name!r}')
    return name[:120]


# ---------------------------------------------------------------- part map

def part_map(st=None):
    st = st or active()
    path = st and st / 'partmap.json'
    return json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else []


def save_part_map(st, rows):
    (st / 'partmap.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')


def set_mapping(st, key, footprint='', symbol=''):
    key = (key or '').strip()
    if not key:
        raise OperationError('Give the part number, reference or package to map.')
    if symbol and ':' not in symbol:
        raise OperationError("A symbol is written 'Library.olb:Package'.")
    rows = [r for r in part_map(st) if r['key'].upper() != key.upper()]
    rows.append({'key': key, 'footprint': (footprint or '').strip(), 'symbol': (symbol or '').strip()})
    save_part_map(st, sorted(rows, key=lambda r: r['key'].upper()))
    return rows


def delete_mapping(st, key):
    rows = part_map(st)
    keep = [r for r in rows if r['key'].upper() != key.upper()]
    if len(keep) == len(rows):
        raise OperationError(f'No mapping for {key}.')
    save_part_map(st, keep)


def import_csv(st, data):
    """CSV with a key column (part number / value / reference / package) and a footprint and/or symbol column."""
    text = data.decode('utf-8-sig', errors='replace')
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise OperationError('The CSV is empty.')
    head = [h.strip().lower() for h in rows[0]]
    def col(*names):
        return next((i for i, h in enumerate(head) for n in names if n in h), None)
    k = col('part number', 'part_number', 'partnumber', 'mpn', 'part', 'value', 'key', 'reference', 'ref', 'package')
    f = col('footprint', 'pcb')
    s = col('symbol', 'orcad', 'library')
    if k is None or (f is None and s is None):
        k, f, s, body = 0, 1, (2 if len(rows[0]) > 2 else None), rows
    else:
        body = rows[1:]
    added = 0
    current = {r['key'].upper(): r for r in part_map(st)}
    for r in body:
        if len(r) <= k or not r[k].strip():
            continue
        fp = r[f].strip() if f is not None and len(r) > f else ''
        sym = r[s].strip() if s is not None and len(r) > s else ''
        if sym and ':' not in sym:
            sym = ''
        if fp or sym:
            current[r[k].strip().upper()] = {'key': r[k].strip(), 'footprint': fp, 'symbol': sym}
            added += 1
    save_part_map(st, sorted(current.values(), key=lambda r: r['key'].upper()))
    return added


def lookup(component, package=''):
    """The part-map row for a component: by reference, then part number/value, then package name."""
    rows = {r['key'].upper(): r for r in part_map()}
    for key in (component.get('ref'), component.get('value'), package):
        if key and str(key).upper() in rows:
            return rows[str(key).upper()]
    return None


# ---------------------------------------------------------------- footprints

def installed_footprint_dirs(root):
    if not root:
        return []
    return [d for d in (root / 'share/pcb/pcb_lib/symbols',) if d.is_dir()]


def footprint_catalog(root, st=None):
    """{lower-case footprint name: source} over the installed OrCAD PCB library and uploaded footprints."""
    st = st or active()
    out = {}
    for d in installed_footprint_dirs(root):
        for p in d.glob('*.psm'):
            out[p.stem.lower()] = 'OrCAD PCB library'
    if st:
        for p in (st / 'footprints').iterdir():
            if p.suffix.lower() in PLACEABLE:
                out[p.stem.lower()] = 'uploaded'
    return out


def standard_footprint(component, package, pin_count, catalog):
    """A standard OrCAD PCB footprint by package type and pin count, when the catalog has it."""
    pkg = (package or '').upper()
    ref = re.match(r'[A-Za-z]*', component.get('ref') or '').group(0).upper()
    named = {'R': 'res400', 'CAP NP': 'cap196', 'CAP POL': 'capck05', 'DIODE': 'dio400', 'POT': 'resadj',
             'INDUCTOR': 'res500', 'DIN96': 'din96abcv', 'CON50A': 'conn50'}
    choice = named.get(pkg)
    if not choice and ref in ('R', 'RN') and pin_count <= 2:
        choice = 'res400'
    if not choice and ref == 'C' and pin_count <= 2:
        choice = 'cap196'
    if not choice and ref == 'D' and pin_count <= 2:
        choice = 'dio400'
    if not choice and ref in ('Q',) and pin_count == 3:
        choice = 'to92'
    if not choice and ref in ('Y', 'X') and pin_count <= 2:
        choice = 'crys14'
    if not choice and (ref in ('P', 'J', 'CN', 'CON') or pkg.startswith('CON')) and pin_count:
        # a connector: the matching connN, else a 2-row 0.1" header with the same pin count
        choice = f'conn{pin_count}' if f'conn{pin_count}' in catalog else f'blkcon100vhtm2oew200{pin_count + pin_count % 2}'
    if not choice and pin_count >= 4:
        n = pin_count + pin_count % 2
        choice = f'dip{n}_3' if n <= 24 and f'dip{n}_3' in catalog else f'dip{n}_6'
    return choice if choice and choice.lower() in catalog else ''


def footprint_for(component, package, pin_count, package_footprint, catalog):
    """(footprint, source) for one placed part."""
    if component.get('footprint'):
        return component['footprint'], 'component'
    row = lookup(component, package)
    if row and row.get('footprint'):
        return row['footprint'], 'part map'
    if package_footprint:
        return package_footprint, 'symbol library'
    fp = standard_footprint(component, package, pin_count, catalog)
    if fp:
        return fp, 'standard (by package and pin count)'
    # Capture's PCB netlister stops (ORCAP-36002) at any part without a footprint, so an unmatched part gets a
    # generic 0.1" header with its pin count, reported as a placeholder to review.
    n = max(2, pin_count + pin_count % 2)
    fp = f'blkcon100vhtm2oew200{n}'
    return (fp, GENERIC_SOURCE) if fp in catalog else ('', 'none')


GENERIC_SOURCE = 'placeholder header (review)'


def footprint_files(names, st=None):
    """Uploaded footprint files for the given footprint names, plus every uploaded padstack/shape they may use."""
    st = st or active()
    if not st:
        return []
    want = {n.lower() for n in names if n}
    every = sorted(p for p in (st / 'footprints').iterdir() if p.is_file())
    used = [p for p in every if p.suffix.lower() in PLACEABLE and p.stem.lower() in want]
    return sorted(used + [p for p in every if p.suffix.lower() not in PLACEABLE]) if used else []


def search_footprints(root, q='', limit=60):
    cat = footprint_catalog(root)
    q = (q or '').lower().strip()
    names = sorted(n for n in cat if q in n) if q else sorted(n for n, s in cat.items() if s == 'uploaded')
    return {'total': len(cat), 'items': [{'name': n, 'source': cat[n]} for n in names[:limit]]}


# ---------------------------------------------------------------- uploads

def add_file(st, name, data, oc):
    """Add one uploaded file (or every usable file in a .zip). Returns a list of {kind, name, detail}."""
    name = safe_name(name)
    ext = Path(name).suffix.lower()
    if ext in ARCHIVE_EXT:
        return _add_archive(st, data, oc)
    if ext not in ACCEPTED:
        raise OperationError(f'{name}: not a library file. Use .OLB symbol libraries, .DSN designs, '
                             'footprints (.psm .dra .pad .kicad_mod), a part map .csv or a .zip of them.')
    if ext in SYMBOL_EXT:
        target = st / 'symbols' / name
        target.write_bytes(data)
        try:
            packages = oc.index_library(target)
        except OperationError:
            target.unlink(missing_ok=True); raise
        if not packages:
            target.unlink(missing_ok=True)
            raise OperationError(f'{name}: Capture found no parts in this library.')
        return [{'kind': 'symbols', 'name': name, 'detail': f'{len(packages)} parts'}]
    if ext in DESIGN_EXT:
        return [import_design(st, name, data, oc)]
    if ext in FOOTPRINT_EXT:
        (st / 'footprints' / name).write_bytes(data)
        return [{'kind': 'footprints', 'name': name, 'detail': 'footprint' if ext in PLACEABLE else 'padstack / shape'}]
    n = import_csv(st, data)
    return [{'kind': 'partmap', 'name': name, 'detail': f'{n} mappings'}]


def _add_archive(st, data, oc):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise OperationError('The .zip archive cannot be read.') from e
    members = [m for m in z.infolist() if not m.is_dir() and '__MACOSX' not in m.filename
               and not Path(m.filename).name.startswith('.')]
    if len(members) > MAX_ARCHIVE_FILES or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
        raise OperationError('The archive is too large (limit 5000 files / 400 MB).')
    added, skipped = [], []
    # symbols and part maps first so designs and footprints can refer to them
    order = lambda m: {'.olb': 0, '.csv': 1, '.dsn': 2}.get(Path(m.filename).suffix.lower(), 3)
    for m in sorted(members, key=order):
        ext = Path(m.filename).suffix.lower()
        if ext not in ACCEPTED - ARCHIVE_EXT:
            skipped.append(Path(m.filename).name); continue
        try:
            added += add_file(st, Path(m.filename).name, z.read(m), oc)
        except OperationError as e:
            skipped.append(f'{Path(m.filename).name} ({e})')
    if not added:
        raise OperationError('No usable library files in the archive. ' + '; '.join(skipped[:5]))
    if skipped:
        added.append({'kind': 'skipped', 'name': f'{len(skipped)} file(s)', 'detail': '; '.join(skipped[:8])})
    return added


def import_design(st, name, data, oc):
    """Keep an existing Capture design: extract its parts into <stem>_parts.OLB, render a preview, add a project file."""
    stem = re.sub(r'[^A-Za-z0-9_-]', '_', Path(name).stem)[:60] or 'design'
    folder = st / 'designs' / stem
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    dsn = folder / f'{stem}.DSN'
    dsn.write_bytes(data)
    lib = st / 'symbols' / f'{stem}_parts.olb'
    meta = {'name': stem, 'file': dsn.name, 'library': None, 'parts': [], 'preview': False, 'notes': []}
    try:
        meta['parts'] = oc.extract_parts(dsn, lib)
        saved = next((f for f in (st / 'symbols').iterdir() if f.name.lower() == lib.name.lower()), lib)
        if saved.name != lib.name:saved.rename(lib)  # Capture upper-cases the file name it creates
        meta['library'] = lib.name
        oc.index_library(lib)
    except OperationError as e:
        lib.unlink(missing_ok=True)
        if 'cannot open design' in str(e):
            shutil.rmtree(folder, ignore_errors=True)
            raise OperationError(f'{name}: not a readable OrCAD Capture design.') from e
        meta['notes'].append(f'Parts not extracted: {e}')
    try:
        (folder / 'preview.svg').write_text(oc.svg(oc.drawing(dsn), stem, 'Imported into the DeCad library'), encoding='utf-8')
        meta['preview'] = True
    except Exception as e:  # preview is a convenience; the design is still usable
        meta['notes'].append(f'No preview: {e}')
    (folder / f'{stem}.opj').write_text(oc.project_file(dsn.name), encoding='utf-8')
    for lock in folder.glob('*lck'):
        lock.unlink(missing_ok=True)
    (folder / 'design.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    detail = f"{len(meta['parts'])} parts extracted into {meta['library']}" if meta['library'] else '; '.join(meta['notes'])
    return {'kind': 'designs', 'name': stem, 'detail': detail}


def remove(st, kind, name):
    if kind == 'symbols':
        path = st / 'symbols' / safe_name(name)
        if not path.is_file():
            raise OperationError(f'No library {name}.')
        path.unlink()
        (st / 'symbols' / '.index' / (path.stem + '.tsv')).unlink(missing_ok=True)
    elif kind == 'designs':
        folder = st / 'designs' / safe_name(name)
        if not folder.is_dir():
            raise OperationError(f'No design {name}.')
        shutil.rmtree(folder)
        for lib in (st / 'symbols').glob('*.olb'):
            if lib.stem.lower() == f'{folder.name}_parts'.lower():
                lib.unlink(); (st / 'symbols' / '.index' / (lib.stem + '.tsv')).unlink(missing_ok=True)
    elif kind == 'footprints':
        path = st / 'footprints' / safe_name(name)
        if not path.is_file():
            raise OperationError(f'No footprint {name}.')
        path.unlink()
    else:
        raise OperationError(f'Unknown library section {kind}.')


def design_folder(st, name):
    folder = st / 'designs' / safe_name(name)
    if not (folder / 'design.json').is_file():
        raise OperationError(f'No design {name}.')
    return folder


def listing(st, oc):
    symbols = []
    for p in symbol_libraries(st):
        try:
            packages = oc.index_library(p)
        except OperationError:
            packages = []
        symbols.append({'name': p.name, 'size': p.stat().st_size, 'parts': len(packages),
                        'sample': [pk for pk, _ in packages[:12]],
                        'footprints': sum(1 for _, fp in packages if fp),
                        'from_design': p.stem.lower().endswith('_parts') and (st / 'designs' / p.stem[:-6]).is_dir()})
    designs = []
    for d in sorted((st / 'designs').iterdir()):
        if (d / 'design.json').is_file():
            designs.append(json.loads((d / 'design.json').read_text(encoding='utf-8')))
    feet = [{'name': p.name, 'kind': 'footprint' if p.suffix.lower() in PLACEABLE else 'padstack / shape', 'size': p.stat().st_size}
            for p in sorted((st / 'footprints').iterdir()) if p.is_file()]
    return {'symbols': symbols, 'designs': designs, 'footprints': feet, 'partmap': part_map(st)}
