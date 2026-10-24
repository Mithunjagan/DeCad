"""Native OrCAD Capture .DSN export through Capture's own database API (orDb_Dll_Tcl64).

The writer places reviewed components, routes visible wires, saves the design, then reopens it
with a separate reader. Export checks both the pin/net map and physical wire continuity;
net aliases cannot substitute for a missing wire between reviewed pins.
"""
import hashlib, io, json, os, re, shutil, subprocess, tempfile, time, zipfile
from pathlib import Path
from .engine import OperationError
from . import orcad_library

HERE = Path(__file__).resolve().parent
TIMEOUT = 600

# KiCad symbol -> Capture package for parts whose value is not a part number.
GENERIC = {
    'Device:R': ('Discrete.olb', 'R'), 'Device:R_Small': ('Discrete.olb', 'R'),
    'Device:C': ('Discrete.olb', 'CAP NP'), 'Device:C_Small': ('Discrete.olb', 'CAP NP'),
    'Device:C_Polarized': ('Discrete.olb', 'CAP NP'), 'Device:L': ('Discrete.olb', 'INDUCTOR'),
    'Device:D': ('Discrete.olb', 'DIODE'), 'Device:LED': ('Discrete.olb', 'LED'),
    'Device:Battery': ('Discrete.olb', 'BATTERY'), 'Device:R_Potentiometer': ('Discrete.olb', 'POT'),
    'Simulation_SPICE:VDC': ('source.olb', 'VDC'), 'Simulation_SPICE:VSIN': ('source.olb', 'VSRC'),
}
# Reference prefix -> KiCad symbol, for recognized parts that arrive without a library.
PREFIX_SYMBOLS = {'R': 'Device:R', 'C': 'Device:C', 'L': 'Device:L', 'D': 'Device:D', 'LED': 'Device:LED',
                  'BT': 'Device:Battery', 'RV': 'Device:R_Potentiometer', 'VR': 'Device:R_Potentiometer'}
# KiCad pin number -> Capture pin number where the generic symbols differ (PSpice sources use 0/1).
GENERIC_PINS = {'Simulation_SPICE:VDC': {'1': '0', '2': '1'}, 'Simulation_SPICE:VSIN': {'1': '0', '2': '1'}}
# Parts without an identically named Capture package. Each substitute was checked to be the
# same function and pinout family; the report flags them for review on the drawing.
SUBSTITUTES = {
    'TC514100': ('DRAM.OLB', 'HM514100JP_20SOJ'),
    'AM2910': ('Misc3.olb', 'AM2910A'), 'AM2910A': ('Misc3.olb', 'AM2910A'),
    'IDT7210': ('Arithmetic.olb', 'IDT7210L'), 'IDT7216': ('Arithmetic.olb', 'IDT7216L'),
}
# Preferred libraries when one package name exists in several.
PREFERENCE = ['74f.olb', '74ls.olb', '74hc.olb', 'discrete.olb', 'connector.olb', 'gate.olb',
              'arithmetic.olb', 'dram.olb', 'misc3.olb', 'muxdecoder.olb', 'latch.olb']


def orcad_root():
    candidates = [os.getenv('ORCAD_ROOT', ''), 'D:\\', 'C:\\Cadence\\OrCADX_26.1']
    candidates += sorted(str(p) for p in Path('C:/Cadence').glob('*')) if Path('C:/Cadence').is_dir() else []
    for c in candidates:
        if c and (Path(c) / 'tools/bin/orDb_Dll_Tcl64.dll').is_file() and (Path(c) / 'tools/bin/tclsh.exe').is_file():
            return Path(c)
    return None


def available():
    return orcad_root() is not None


def _run(root, script, *args):
    env = {**os.environ, 'PATH': str(root / 'tools/bin') + os.pathsep + os.environ.get('PATH', ''), 'CDSROOT': str(root)}
    for attempt in range(3):
        try:
            r = subprocess.run([str(root / 'tools/bin/tclsh.exe'), str(HERE / script), str(root / 'tools/bin/orDb_Dll_Tcl64.dll'),
                                *(str(a.resolve()) if isinstance(a, Path) else str(a) for a in args)],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT, env=env, cwd=str(root / 'tools/bin'))
        except subprocess.TimeoutExpired as e:
            raise OperationError('OrCAD Capture database operation timed out.') from e
        errors = [l[6:] for l in r.stdout.splitlines() if l.startswith('ERROR ')]
        if not r.returncode and not errors:
            return r.stdout
        diagnostic = r.stderr + r.stdout
        # Checkout can fail briefly between native sessions. Only retry failure at session
        # creation, before a script can write a design; never replay a partly executed write.
        if attempt < 2 and 'License not found' in diagnostic and 'DboTclHelper_sCreateSession' in diagnostic:
            time.sleep(1)
            continue
        raise OperationError('OrCAD Capture: ' + ('; '.join(errors) or (r.stderr or r.stdout)[-1500:]))


# (library path lower-case, PACKAGE) -> PCB footprint stored on the library package
PACKAGE_FOOTPRINTS = {}


def _read_index(cache, index):
    for line in Path(cache).read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) < 3:continue
        lib, pkg = parts[0], parts[1]
        index.setdefault(pkg.upper(), []).append(lib)
        if len(parts) > 3 and parts[3].strip():PACKAGE_FOOTPRINTS[(lib.lower(), pkg.upper())] = parts[3].strip()


def library_index(cache):
    """Package name -> list of library paths, built once from every installed .olb, plus the
    workspace's own libraries (uploaded or extracted from designs), which take precedence."""
    root = orcad_root()
    cache = Path(cache)
    if cache.name == 'orcad-lib-index.tsv':cache = cache.with_name('orcad-lib-index-v2.tsv')  # v2 adds footprints
    if not cache.exists():
        libs = sorted(str(p) for p in (root / 'tools/capture/library').rglob('*') if p.suffix.lower() == '.olb')
        tmp = cache.with_suffix('.tmp')
        _run(root, 'orcad_index.tcl', tmp, *libs)
        tmp.replace(cache)
    index = {}
    for lib in orcad_library.symbol_libraries():
        try:index_library(lib)
        except OperationError:continue
        _read_index(_lib_cache(lib), index)
    _read_index(cache, index)
    return index


def _lib_cache(lib):
    return Path(lib).parent / '.index' / (Path(lib).stem + '.tsv')


def index_library(lib):
    """[(package, PCB footprint)] of one library, cached next to it until the library changes."""
    lib = Path(lib)
    cache = _lib_cache(lib)
    if not cache.is_file() or cache.stat().st_mtime < lib.stat().st_mtime:
        cache.parent.mkdir(exist_ok=True)
        tmp = cache.with_suffix('.tmp')
        _run(orcad_root(), 'orcad_index.tcl', tmp, lib)
        tmp.replace(cache)
    out = []
    for line in cache.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) >= 3:out.append((parts[1], parts[3].strip() if len(parts) > 3 else ''))
    return out


def extract_parts(dsn, olb):
    """Copy every package placed in an existing design into a symbol library; returns the packages."""
    try:
        out = _run(orcad_root(), 'orcad_extract.tcl', dsn, olb)
    finally:
        for lock in Path(dsn).parent.glob('*lck'):lock.unlink(missing_ok=True)
    parts = []
    for line in out.splitlines():
        if line.startswith('PKG '):
            w = _tcl_list(line)
            parts.append({'package': w[1], 'source': Path(w[2].replace('\\', '/')).name if len(w) > 2 else '',
                          'footprint': w[3] if len(w) > 3 else ''})
    return parts


def _pick(libs):
    rank = lambda p: -1 if orcad_library.is_user_library(p) else PREFERENCE.index(Path(p).name.lower()) if Path(p).name.lower() in PREFERENCE else len(PREFERENCE)
    return sorted(libs, key=lambda p: (rank(p), p))[0]


def apply_symbol_overrides(components, index):
    """Part-map rows that name a Capture symbol ('Library.olb:Package') pin those parts to it."""
    out, notes = [], []
    for c in components:
        row = orcad_library.lookup(c)
        if row and row.get('symbol') and not c.get('orcad'):
            lib, _, pkg = row['symbol'].partition(':')
            if any(Path(p).name.lower() == lib.lower() for p in index.get(pkg.upper(), [])):
                c = {**c, 'orcad': row['symbol']}
            else:
                notes.append(f"{c['ref']}: part map names {row['symbol']}, which is not in any library; ignored.")
        out.append(c)
    return out, notes


def assign_footprints(graph, resolved, generate, used, cache_dir, root):
    """ref -> (PCB footprint, source) for every component (see orcad_library.footprint_for)."""
    catalog = orcad_library.footprint_catalog(root)
    lib_parts = [(lib, pkg) for lib, pkg, how in resolved.values() if how != 'generated symbol']
    try:
        pins = package_pins(cache_dir, lib_parts) if lib_parts else {}
    except OperationError:
        pins = {}
    out = {}
    for c in graph['components']:
        lib, pkg, how = resolved[c['ref']]
        if how == 'generated symbol':
            count = len(generated_pins(generate.get(pkg, [None, set()])[1]))
        else:
            count = len(pins.get((lib, pkg), {})) or len(set(used.get(c['ref'], ())))
        own = PACKAGE_FOOTPRINTS.get((str(lib).lower(), pkg.upper()), '')
        out[c['ref']] = orcad_library.footprint_for(c, pkg, count, own, catalog)
    return out


def footprint_summary(footprints, placed, root):
    catalog = orcad_library.footprint_catalog(root)
    sources = {}
    for fp, src in footprints.values():
        if fp:sources[src] = sources.get(src, 0) + 1
    return {'assigned': sum(1 for fp, _ in footprints.values() if fp), 'total': len(footprints),
            'placed': len(placed), 'sources': sources,
            'without': sorted(r for r, (fp, _) in footprints.items() if not fp),
            'placeholder': sorted(r for r, (fp, src) in footprints.items() if fp and src == orcad_library.GENERIC_SOURCE),
            'not_in_library': sorted({fp for fp, _ in footprints.values() if fp and fp.lower() not in catalog})}


def physical_netlist(dump, mapping):
    """The physical netlist of the saved design, read back from the reopened .DSN: every part with its
    PCB footprint, every net with its part.pin connections (including the parts' implicit power pins)."""
    parts, nets = {}, {}
    for line in dump.splitlines():
        if not line.startswith(('PART ', 'PIN ')):continue
        w = _tcl_list(line)
        if w[0] == 'PART':
            m = mapping.get(w[1], {})
            parts.setdefault(w[1], {'ref': w[1], 'value': w[3] if len(w) > 3 else '', 'footprint': w[4] if len(w) > 4 else '',
                                    'library': m.get('library', ''), 'package': m.get('package', '')})
        elif len(w) > 3 and w[3]:
            nets.setdefault(w[3], set()).add((w[1], w[2]))
    key = lambda n: (int(n) if n.isdigit() else 10 ** 6, n)
    return {'parts': sorted(parts.values(), key=lambda p: (re.sub(r'\d', '', p['ref']), int(re.sub(r'\D', '', p['ref']) or 0), p['ref'])),
            'nets': [{'name': n, 'nodes': [{'ref': r, 'pin': p} for r, p in sorted(m, key=lambda rp: (rp[0], key(rp[1])))]}
                     for n, m in sorted(nets.items())]}


def netlist_csv(net):
    import csv as _csv
    fp = {p['ref']: p['footprint'] for p in net['parts']}
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(['Net', 'Reference', 'Pin', 'PCB Footprint'])
    for n in net['nets']:
        for node in n['nodes']:w.writerow([n['name'], node['ref'], node['pin'], fp.get(node['ref'], '')])
    return buf.getvalue()


def telesis_netlist(net, title):
    """OrCAD PCB Editor / Allegro third-party (Telesis) netlist: File > Import > Logic/Netlist > Other."""
    q = lambda t: t if re.fullmatch(r'[A-Za-z0-9_+\-./]+', t) else "'" + t.replace("'", '') + "'"
    out = ['$PACKAGES']
    groups = {}
    for p in net['parts']:
        groups.setdefault((p['footprint'] or 'NO_FOOTPRINT', p['value'] or p['package'] or 'PART'), []).append(p['ref'])
    for (fp, val), refs in sorted(groups.items()):
        out.append(f'{q(fp)} ! {q(val)} ; ' + ' '.join(refs))
    out.append('$NETS')
    for n in net['nets']:
        nodes = [f"{node['ref']}.{node['pin']}" for node in n['nodes']]
        lines = [nodes[i:i + 8] for i in range(0, len(nodes), 8)]
        for i, chunk in enumerate(lines):
            text = (f'{q(n["name"])} ; ' if i == 0 else '  ') + ' '.join(chunk)
            out.append(text + (',' if i < len(lines) - 1 else ''))
    out.append('$END')
    return '\n'.join(out) + '\n'


def footprint_csv(graph, mapping):
    import csv as _csv
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(['Reference', 'Value', 'Library', 'Package', 'PCB Footprint', 'Footprint source'])
    for c in graph['components']:
        m = mapping[c['ref']]
        w.writerow([c['ref'], c.get('value', ''), m['library'], m['package'], m['footprint'], m['footprint_source']])
    return buf.getvalue()


def _in_lib(index, lib, pkg):
    return next((p for p in index.get(pkg.upper(), []) if Path(p).name.lower() == lib.lower()), None)


def connector_package(pins):
    """Board connectors: lettered rows (A1..C32) are a DIN 41612 96-way; numbered pins a header."""
    pins = [str(p).upper() for p in pins]
    if any(re.fullmatch(r'[A-C]\d{1,2}', p) for p in pins):
        return 'Connector.olb', 'DIN96'
    nums = [int(p) for p in pins if p.isdigit()]
    top = max(nums, default=0)
    return ('Connector.olb', 'CON40A') if top <= 40 else ('Connector.olb', 'CON50A') if top <= 50 else (None, None)


def connector_pin(package, pin):
    """DIN96 pin names A1..C32 -> Capture pin numbers 1..96."""
    m = re.fullmatch(r'([A-C])(\d{1,2})', str(pin).upper())
    if package == 'DIN96' and m and 1 <= int(m.group(2)) <= 32:
        return str('ABC'.index(m.group(1)) * 32 + int(m.group(2)))
    return str(pin)


def correct_value(value, index):
    """Repair a one-character OCR slip in a part number (74508 -> 74F08) when exactly one
    installed package of the same family matches."""
    value = (value or '').upper()
    if value in index or value in SUBSTITUTES or len(value) < 5:
        return value
    # A pin number printed against a gate's part number reads as one token ("74F10" + pin 3 = "74F103"):
    # the installed library has the shorter name and not the longer one.
    if re.fullmatch(r'(74|54)[A-Z]{1,4}\d{2,4}\d', value) and value[:-1] in index:
        return value[:-1]
    # a digit read as another digit names a different part (74BCT2244 is not 74BCT8244): never "correct" it
    digit_swap = lambda k: len(k) == len(value) and any(a != b and a.isdigit() and b.isdigit() for a, b in zip(k, value))
    hits = [k for k in index if len(k) == len(value) and k[:2] == value[:2] and sum(a != b for a, b in zip(k, value)) == 1
            and not digit_swap(k)]
    families = [h for h in hits if re.match(r'(74|IDT|AM|HM|MC|TC)', h)]
    if len(families) == 1:
        return families[0]
    # OCR-aware match against logic/IC families (AM291C -> AM2910, 74F24U -> 74F240, 74BCI2244 -> 74BCT2244):
    # confusable characters are cheap, one inserted/dropped character costs 1; only a unique best match counts.
    from .digital_vision import _cost
    if not re.match(r'(74|IDT|AM|HM|MC|TC|T0|7A)', value):
        return value
    names = set(index) | set(SUBSTITUTES)
    scored = sorted((_cost(value, k), k) for k in names
                    if abs(len(k) - len(value)) <= 1 and re.match(r'(74|IDT|AM|HM|MC|TC)', k) and k[:1] == value[:1]
                    and not digit_swap(k))
    if scored and scored[0][0] <= 1.0 and (len(scored) == 1 or scored[1][0] - scored[0][0] >= 0.5):
        return scored[0][1]
    return value


def kicad_symbol(component):
    """The component's KiCad symbol, or the generic one implied by its reference prefix."""
    if component.get('library'):
        return component['library']
    m = re.match(r'[A-Za-z]+', component.get('ref') or '')
    return PREFIX_SYMBOLS.get(m.group(0).upper()) if m else None


def resolve(component, index, root, pins=(), generate=False):
    """Return (library path, package, how) for one component, or raise with a precise reason."""
    explicit = component.get('orcad') or ''
    if explicit:
        lib, _, pkg = explicit.partition(':')
        path = next((p for p in index.get(pkg.upper(), []) if Path(p).name.lower() == lib.lower()), None)
        if not path:raise OperationError(f"{component['ref']}: {explicit} is not an installed Capture package.")
        return path, pkg, 'explicit'
    value = (component.get('value') or '').strip().upper()
    if value in index:
        return _pick(index[value]), value, 'part number'
    if value in SUBSTITUTES:
        lib, pkg = SUBSTITUTES[value]
        path = next((p for p in index.get(pkg.upper(), []) if Path(p).name.lower() == lib.lower()), None)
        if path:return path, pkg, f'substitute for {value} (review pinout)'
    if value in ('CONNECTOR', 'CONN', 'HEADER') or (component['ref'][:1] in 'PJ' and value not in index):
        lib, pkg = connector_package(pins)
        path = lib and _in_lib(index, lib, pkg)
        if path:return path, pkg, 'connector by pin names'
    generic = GENERIC.get(kicad_symbol(component) or '')
    if generic:
        lib, pkg = generic
        path = next((p for p in index.get(pkg.upper(), []) if Path(p).name.lower() == lib.lower()), None)
        if path:return path, pkg, 'generic symbol'
    if generate:
        return GENERATED_LIB, generated_name(component), 'generated symbol'
    raise OperationError(f"{component['ref']}: no Capture package for value '{component.get('value')}' "
                         f"({component.get('library')}). Set an explicit 'orcad': 'Library.olb:Package'.")


GENERATED_LIB = 'DECAD_GENERATED.OLB'
POWER_NAME = re.compile(r'(A|D)?(GND|VCC|VDD|VSS|VEE|VBB|PWR)\d*|V[+-]')


def generated_name(component):
    """Package name for a generated symbol: the part number when one was read, else the reference."""
    value = re.sub(r'[^A-Z0-9_+\-]', '_', (component.get('value') or '').strip().upper()).strip('_')
    return value if value and value not in ('UNKNOWN', 'IC', 'U') else 'PART_' + component['ref']


def generated_pins(pins):
    """All pins of a numbered package up to the highest used one (even, as on a DIP); otherwise the used pins."""
    pins = sorted(set(map(str, pins)), key=lambda p: (not p.isdigit(), int(p) if p.isdigit() else 0, p))
    nums = sorted(int(p) for p in pins if p.isdigit())
    if pins and len(nums) == len(pins):
        # a stray misread number (pin 96 on a 24-pin PROM) must not inflate the package: keep the
        # pins below the first large jump, and add every pin only when the package stays plausible
        keep = [nums[0]]
        for n in nums[1:]:
            if n - keep[-1] > 12:break
            keep.append(n)
        top = keep[-1] + keep[-1] % 2
        if top <= 64 and top <= max(2 * len(nums), 16):
            return [str(i) for i in range(1, max(top, 2) + 1)] + [str(n) for n in nums if n > top]
        return [str(n) for n in nums]
    return pins or ['1', '2']


def net_aliases(graph):
    """Capture alias names: no spaces/brackets (brackets mean buses). Keeps names unique."""
    used, out = set(), {}
    for net in graph.get('nets', []):
        base = re.sub(r'[^A-Za-z0-9_+\-./]', '_', net['name'].strip()) or 'NET'
        if base[0].isdigit():base = 'N' + base
        name, i = base, 2
        while name.upper() in used:name, i = f'{base}_{i}', i + 1
        used.add(name.upper()); out[net['name']] = name
    return out


def tcl_word(text):
    """Brace-quote safely for Tcl source (balanced or escaped)."""
    text = str(text)
    if not text:return '{}'
    if re.fullmatch(r'[A-Za-z0-9_+\-./:\\]+', text) and '\\' not in text:return text
    return '"' + re.sub(r'([\\$\[\]"{}])', r'\\\1', text) + '"'


def export(name, graph, cache_dir, *, preserve_connections=False):
    if preserve_connections or graph.get('image_metadata', {}).get('pin_anchors'):
        from .observed_export import orcad_bundle
        return orcad_bundle(name,graph,cache_dir)
    root = orcad_root()
    if root is None:
        raise OperationError('OrCAD Capture is not installed. Set ORCAD_ROOT to the OrCAD X installation folder.')
    if not graph.get('components'):
        raise OperationError('Add components before exporting an OrCAD design.')
    index = library_index(Path(cache_dir) / 'orcad-lib-index.tsv')
    components, override_notes = apply_symbol_overrides(graph['components'], index)
    graph = {**graph, 'components': components}
    aliases = net_aliases(graph)
    used = {}
    for net in graph.get('nets', []):
        for node in net['nodes']:used.setdefault(node['ref'], []).append(str(node['pin']))
    resolved = {c['ref']: resolve(c, index, root, used.get(c['ref'], ()), generate=True) for c in graph['components']}
    generate = {}
    for c in graph['components']:
        if resolved[c['ref']][2] == 'generated symbol':
            prefix = re.match(r'[A-Za-z]*', c['ref']).group(0) or 'U'
            generate.setdefault(resolved[c['ref']][1], [prefix, set()])[1].update(used.get(c['ref'], ()))
    pin_maps = {c['ref']: GENERIC_PINS.get(kicad_symbol(c) or '', {}) for c in graph['components']
                if resolved[c['ref']][2] == 'generic symbol'}
    pin_net, corrections = {}, []
    for net in graph.get('nets', []):
        for node in net['nodes']:
            pin = connector_pin(resolved[node['ref']][1], str(node['pin']))
            key = (node['ref'], pin_maps.get(node['ref'], {}).get(pin, pin))
            if key in pin_net and pin_net[key] != aliases[net['name']]:
                corrections.append(f"{key[0]} pin {key[1]} was on {pin_net[key]} and {aliases[net['name']]}; kept {pin_net[key]}.")
                continue
            pin_net[key] = aliases[net['name']]
    footprints = assign_footprints(graph, resolved, generate, used, cache_dir, root)
    mapping = {c['ref']: {'library': Path(resolved[c['ref']][0]).name, 'package': resolved[c['ref']][1],
                          'match': resolved[c['ref']][2], 'value': c.get('value', ''),
                          'footprint': footprints[c['ref']][0], 'footprint_source': footprints[c['ref']][1]} for c in graph['components']}
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)[:60] or 'design'
    with tempfile.TemporaryDirectory() as td:
        dsn = Path(td) / f'{safe}.DSN'
        genlib = Path(td) / GENERATED_LIB
        # Recognition noise (a misread pin number landing on a hidden power pin or a pin the part
        # does not have) must not block the design: drop exactly the pins verification rejects,
        # rebuild once, and report every dropped connection.
        # 1) Recognition noise (a misread pin on a fixed power pin or a pin the part lacks) must not
        #    block the design: drop exactly the pins verification rejects and rebuild (labelled stubs).
        for attempt in range(3):
            for f in Path(td).iterdir():f.unlink()
            _write(root, td, dsn, genlib, graph, resolved, generate, pin_net, footprints)
            dump = _run(root, 'orcad_dump.tcl', dsn)
            report = verify(dump, pin_net, mapping)
            if report['passed'] or attempt == 2:break
            bad = report.get('failed_pins', [])
            if not bad:break
            for key in bad:
                corrections.append(f"{key[0]} pin {key[1]} removed from {pin_net[key]}: " +
                                   ('the part has no such pin.' if key in report.get('missing_pins', []) else 'it is a fixed power/ground pin of the part.'))
                pin_net.pop(key, None)
        # 2) Require real wires between every reviewed group of pins. A label-only fallback would
        #    pass the electrical netlist check while failing the user's visible-wiring requirement.
        routing = None
        if report['passed']:
            for f in Path(td).iterdir():f.unlink()
            _write(root, td, dsn, genlib, graph, resolved, generate, pin_net, footprints, wiring=True)
            routing = _wire(root, td, dsn, pin_net, require_wires=True)
            dump = _run(root, 'orcad_dump.tcl', dsn)
            report = verify(dump, pin_net, mapping)
        report['routing'] = routing
        if not report['passed']:
            raise OperationError('OrCAD design failed reopen verification: ' + '; '.join(report['errors'][:10]))
        report['generated_symbols'] = sorted(generate)
        report['corrections'] = override_notes + corrections
        report['footprints'] = footprint_summary(footprints, report.get('placed_footprints', {}), root)
        user_libs = sorted({resolved[r][0] for r in resolved if orcad_library.is_user_library(resolved[r][0])})
        report['user_libraries'] = {Path(l).name: sorted(r for r in resolved if resolved[r][0] == l) for l in user_libs}
        files = {f'{safe}.DSN': dsn.read_bytes(), 'circuit.json': json.dumps(graph, indent=2).encode(),
                 'orcad-mapping.json': json.dumps(mapping, indent=2).encode(),
                 'verification.json': json.dumps(report, indent=2).encode()}
        if genlib.is_file():files[GENERATED_LIB] = genlib.read_bytes()
        libs = [GENERATED_LIB] if genlib.is_file() else []
        for lib in user_libs:
            files[f'libraries/{Path(lib).name}'] = Path(lib).read_bytes(); libs.append(f'libraries\\{Path(lib).name}')
        for f in orcad_library.footprint_files({fp for fp, _ in footprints.values()}):
            files[f'footprints/{f.name}'] = f.read_bytes()
        files['footprints.csv'] = footprint_csv(graph, mapping).encode()
        net = physical_netlist(dump, mapping)
        report['netlist'] = {'nets': len(net['nets']), 'connections': sum(len(n['nodes']) for n in net['nets']),
                             'parts': len(net['parts']), 'without_footprint': [p['ref'] for p in net['parts'] if not p['footprint']]}
        files['netlist.json'] = json.dumps(net, indent=1).encode()
        files['netlist.csv'] = netlist_csv(net).encode()
        files[f'{safe}.net'] = telesis_netlist(net, safe).encode()
        files[f'{safe}.opj'] = project_file(f'{safe}.DSN', libs).encode()
    files['manifest.json'] = json.dumps({'format': 'OrCAD Capture native design (.DSN)', 'orcad_root': str(root),
                                         'files': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}, indent=2).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, v in files.items():z.writestr(n, v)
    return out.getvalue(), report


SOURCE_SCALE = 6000   # Capture units per source-sheet width; positions already use width units
SOURCE_MARGIN = 300


def placement(components, *, scale=SOURCE_SCALE):
    """Source body centres on Capture's 10-unit grid; missing positions are handled by the writer.

    Keep both distances, including when only one part has a position. Both source coordinates
    are fractions of sheet width (not independent x/y normalization).
    """
    return {c['ref']: (round((SOURCE_MARGIN + c['x'] * scale) / 10) * 10,
                       round((SOURCE_MARGIN + c['y'] * scale) / 10) * 10)
            for c in components if c.get('x') is not None and c.get('y') is not None}


def _wire(root, td, dsn, pin_net, *, require_wires=False):
    """Route the saved page and add its wires and labels (orcad_wire.tcl). Returns the routing summary."""
    from . import orcad_route
    for lock in Path(td).glob('*lck'):lock.unlink(missing_ok=True)
    pages = drawing(dsn)
    if not pages:raise OperationError('the design has no page to wire')
    wires, summary = orcad_route.route(pages[0], pin_net, _place, require_wires=require_wires)
    data = Path(td) / 'wires.tcl'
    data.write_text(f'set design_path {tcl_word(str(dsn))}\nset wires {{\n' +
                    '\n'.join('{' + ' '.join(tcl_word(v) for v in w) + '}' for w in wires) + '\n}\n', encoding='utf-8')
    _run(root, 'orcad_wire.tcl', data)
    for lock in Path(td).glob('*lck'):lock.unlink(missing_ok=True)
    if require_wires:
        check = orcad_route.verify_visible_wires(drawing(dsn)[0], pin_net)
        summary['visible_wire_verification'] = check
        if not check['passed']:
            raise OperationError('Saved OrCAD wires failed physical continuity checks: ' + json.dumps(check))
    return summary


def _write(root, td, dsn, genlib, graph, resolved, generate, pin_net, footprints=None, wiring=False,literal_pins=False,source_symbols=None,source_scale=SOURCE_SCALE):
    lines = []
    where = placement(graph['components'],scale=source_scale)
    order = sorted(graph['components'], key=lambda c: (c['ref'] not in where,
                   where.get(c['ref'], (0, 0))[1], where.get(c['ref'], (0, 0))[0], c['ref'])) if where else graph['components']
    if source_symbols:
        # Place fixed measured bodies first. Ambiguous fallback symbols must avoid
        # them; otherwise a later fixed body can cover a fallback's terminal.
        order = sorted(order, key=lambda c: c['ref'] not in source_symbols)
    for c in order:
        lib, pkg, how = resolved[c['ref']]
        lib = str(genlib) if how == 'generated symbol' else lib
        pins = ' '.join(f'{tcl_word(p)} {tcl_word(n)}' for (r, p), n in sorted(pin_net.items()) if r == c['ref'])
        fp = (footprints or {}).get(c['ref'], ('', ''))[0]
        tx, ty = where.get(c['ref'], ('', ''))
        lines.append('{' + ' '.join([tcl_word(c['ref']), tcl_word(c.get('value', '')), tcl_word(lib), tcl_word(pkg), '{' + pins + '}', tcl_word(fp),
                                     tcl_word(tx), tcl_word(ty)]) + '}')
    gens = ['{' + ' '.join([tcl_word(str(genlib)), tcl_word(pkg), tcl_word(prefix),
                            '{' + ' '.join(tcl_word(p) for p in (sorted(pins) if literal_pins else generated_pins(pins))) + '}']) + '}'
            for pkg, (prefix, pins) in sorted(generate.items())]
    aspect = graph.get('sheet_aspect')
    if where and not aspect:
        # Legacy reviewed circuits lack source dimensions; estimate from their width-based y values.
        aspect = 1 / max(0.7, max(c['y'] for c in graph['components'] if c['ref'] in where) + 0.1)
    sheet = (f'set source_width {source_scale + 2 * SOURCE_MARGIN}\n'
             f'set source_height {round((source_scale / aspect + 2 * SOURCE_MARGIN) / 10) * 10}\n'
             f'set source_aspect {aspect}\n') if where else ''
    # Source arrangement, compacted: Capture symbols are far smaller than scanned bodies, so true source
    # distances leave the page mostly empty. DSN_LAYOUT=source keeps the exact source positions.
    if where and not source_symbols and os.getenv('DSN_LAYOUT', 'compact').lower() != 'source':
        sheet += 'set compact 1\n'
    if source_symbols:
        sheet += 'set source_exact 1\n'
        sheet += 'set source_symbols {\n'
        for ref, definition in source_symbols.items():
            vectors = ' '.join('{' + ' '.join(tcl_word(v) for v in vector) + '}' for vector in definition['vectors'])
            pins = ' '.join('{' + ' '.join(tcl_word(v) for v in pin) + '}' for pin in definition['pins'])
            sheet += tcl_word(resolved[ref][1]) + ' {{' + vectors + '} {' + pins + '}}\n'
        sheet += '}\n'
    data = Path(td) / 'data.tcl'
    if literal_pins:
        sheet += 'set generated_pin_pitch 30\n'
    data.write_text(sheet + f'set design_path {tcl_word(str(dsn))}\nset generate {{\n' + '\n'.join(gens) +
                    '\n}\nset components {\n' + '\n'.join(lines) + '\n}\n' +
                    ('set nostubs 1\n' if wiring else ''), encoding='utf-8')
    _run(root, 'orcad_writer.tcl', data)
    if not dsn.is_file():raise OperationError('OrCAD Capture did not write the design file.')


def verify(dump, expected, mapping):
    """Compare the reopened design's pin/net map with the source graph."""
    actual, parts, placed_fp = {}, set(), {}
    for line in dump.splitlines():
        if line.startswith(('PIN ', 'PART ')):
            words = _tcl_list(line)
            if words[0] == 'PART':
                parts.add(words[1])
                if len(words) > 4 and words[4]:placed_fp[words[1]] = words[4]
            else:actual[(words[1], words[2])] = words[3] if len(words) > 3 else ''
    errors, failed, missing = [], [], []
    missing_parts = sorted(set(mapping) - parts)
    errors += [f'{r} not placed' for r in missing_parts]
    for key, net in sorted(expected.items()):
        got = actual.get(key)
        if got is None:
            errors.append(f'{key[0]} pin {key[1]} does not exist on {mapping[key[0]]["package"]}'); failed.append(key); missing.append(key)
        elif got.upper() != net.upper():
            errors.append(f'{key[0]} pin {key[1]} on {got or "nothing"}, expected {net}'); failed.append(key)
    implicit = sorted(f'{r}.{p}={n}' for (r, p), n in actual.items() if (r, p) not in expected and n)
    return {'passed': not errors, 'errors': errors, 'failed_pins': failed, 'missing_pins': missing,
            'components': len(parts), 'checked_pins': len(expected),
            'implicit_power_pins': implicit, 'placed_footprints': placed_fp,
            'substitutions': {r: m for r, m in mapping.items() if m['match'].startswith('substitute')}}


def _tcl_list(line):
    """Parse one Tcl list line printed by orcad_dump.tcl (words, {braced words}, backslashes)."""
    out, i, n = [], 0, len(line)
    while i < n:
        while i < n and line[i] == ' ':i += 1
        if i >= n:break
        if line[i] == '{':
            depth, j = 1, i + 1
            while j < n and depth:
                depth += {'{': 1, '}': -1}.get(line[j], 0); j += 1
            out.append(line[i + 1:j - 1]); i = j
        else:
            j, word = i, []
            while j < n and line[j] != ' ':
                if line[j] == '\\' and j + 1 < n:word.append(line[j + 1]); j += 2
                else:word.append(line[j]); j += 1
            out.append(''.join(word)); i = j
    return out


def package_pins(cache_dir, wanted):
    """{(library path, package): {pin number: pin name}} for the requested packages, cached on disk."""
    cache = Path(cache_dir) / 'orcad-pins.json'
    known = json.loads(cache.read_text()) if cache.exists() else {}
    missing = [(lib, pkg) for lib, pkg in set(wanted) if f'{lib}|{pkg}' not in known]
    if missing:
        args = [x for pair in missing for x in pair]
        out = _run(orcad_root(), 'orcad_pins.tcl', *args)
        found = {f'{lib}|{pkg}': {} for lib, pkg in missing}
        names = {pkg: f'{lib}|{pkg}' for lib, pkg in missing}
        for line in out.splitlines():
            parts = line.split('\t')
            if len(parts) == 3 and parts[0] in names:
                found[names[parts[0]]][parts[1]] = parts[2]
        known.update(found)
        cache.write_text(json.dumps(known))
    return {(lib, pkg): known.get(f'{lib}|{pkg}', {}) for lib, pkg in wanted}


def check(graph, cache_dir):
    """Library-guided cleanup of a recognized circuit: fix one-character part-number misreads,
    drop pins the part does not have, and say what changed. Returns (graph, warnings)."""
    index = library_index(Path(cache_dir) / 'orcad-lib-index.tsv')
    root = orcad_root()
    warnings, comps = [], []
    used = {}
    for net in graph.get('nets', []):
        for node in net['nodes']:used.setdefault(node['ref'], []).append(str(node['pin']))
    overridden, notes = apply_symbol_overrides(graph['components'], index)
    warnings += notes
    for c in overridden:
        c = dict(c)
        fixed = correct_value(c.get('value'), index)
        if fixed != (c.get('value') or '').upper():
            warnings.append(f"{c['ref']}: part number read as {c.get('value')}, corrected to {fixed} (library match).")
            c['value'] = fixed
        comps.append(c)
    resolved, generated = {}, []
    for c in comps:
        r = resolve(c, index, root, used.get(c['ref'], ()), generate=True)
        if r[2] == 'generated symbol':generated.append(f"{c['ref']} ({c.get('value')})")
        else:resolved[c['ref']] = r
    # One part number, several packages (IDT7210L: DIP, /PGA, /LCC, /FP) number their pins differently.
    # The drawing's package is the one its connections fit: fewest used pins missing or fixed power/ground.
    for c in comps:
        r = resolved.get(c['ref'])
        if not r or r[2] != 'part number' or c.get('orcad'):
            continue
        options = [(p, k) for k in index if k == r[1] or k.startswith(r[1] + '/') for p in index[k][:1]]
        if len(options) < 2:
            continue
        table = package_pins(cache_dir, options)
        def conflicts(option):
            names = table.get(option, {})
            return sum(1 for pin in used.get(c['ref'], ()) if pin not in names or POWER_NAME.fullmatch(names[pin].upper()))
        best = min(options, key=lambda o: (conflicts(o), o[1] != r[1]))
        if best[1] != r[1] and conflicts(best) < conflicts((r[0], r[1])):
            warnings.append(f"{c['ref']}: package {best[1]} chosen over {r[1]} - its pin numbers fit the drawn connections "
                            f"({conflicts(best)} vs {conflicts((r[0], r[1]))} conflicts).")
            c['orcad'] = f'{Path(best[0]).name}:{best[1]}'
            resolved[c['ref']] = (best[0], best[1], 'explicit')
    if generated:
        warnings.append('Not in the installed Capture libraries; a matching symbol will be generated with the used pins: ' + ', '.join(generated))
    pins = package_pins(cache_dir, [(lib, pkg) for lib, pkg, _ in resolved.values()]) if resolved else {}
    nets, dropped = [], []
    for net in graph.get('nets', []):
        nodes = []
        for node in net['nodes']:
            r = resolved.get(node['ref'])
            if r:
                valid = pins.get((r[0], r[1]), {})
                if valid and connector_pin(r[1], node['pin']) not in valid:
                    dropped.append(f"{node['ref']}.{node['pin']}"); continue
            nodes.append(node)
        if nodes:nets.append({**net, 'nodes': nodes})
    if dropped:
        warnings.append('Removed pins that do not exist on the identified part (likely misread numbers): ' + ', '.join(dropped[:40]))
    return {**graph, 'components': comps, 'nets': nets}, warnings


# ---------------------------------------------------------------- showcase: preview, open, project store

def drawing(dsn):
    """Read the saved design back from Capture's database: parts with symbol vectors, pins, wires, labels."""
    out = _run(orcad_root(), 'orcad_render.tcl', dsn)
    pages, part = [], None
    for line in out.splitlines():
        w = _tcl_list(line)
        if not w:continue
        k = w[0]
        if k == 'PAGE':pages.append({'name': w[1], 'width': int(w[2]), 'height': int(w[3]), 'parts': [], 'wires': [], 'aliases': [], 'globals': []})
        elif not pages:continue
        elif k == 'PART':
            part = {'ref': w[1], 'value': w[2], 'x': int(w[3]), 'y': int(w[4]), 'rotation': int(w[5]), 'mirror': int(w[6]),
                    'base': w[7] if len(w) > 7 else w[1], 'vectors': [], 'pins': []}
            pages[-1]['parts'].append(part)
        elif k == 'V' and part:part['vectors'].append([w[1]] + [int(v) for v in w[2:]])
        elif k == 'PIN' and part:
            part['pins'].append({'number': w[2], 'name': w[3], 'hx': int(w[4]), 'hy': int(w[5]), 'sx': int(w[6]), 'sy': int(w[7]),
                                 'dot': w[8] == '1', 'clock': w[9] == '1'})
        elif k == 'WIRE':pages[-1]['wires'].append([int(v) for v in w[1:5]])
        elif k == 'ALIAS':pages[-1]['aliases'].append({'name': w[1], 'x': int(w[2]), 'y': int(w[3])})
        elif k == 'GLOBAL':pages[-1]['globals'].append({'name': w[1], 'x': int(w[2]), 'y': int(w[3])})
    return pages


def _esc(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _place(part):
    """Symbol coordinates -> page coordinates (rotation in quarter turns, then optional mirror)."""
    r, m, ox, oy = part['rotation'] % 4, part['mirror'], part['x'], part['y']
    def t(x, y):
        if m:x = -x
        for _ in range(r):x, y = y, -x
        return ox + x, oy + y
    return t


def svg(pages, title='', subtitle='Generated by DeCad · verified by reopening', preserve_page=False):
    """Capture-style SVG of the busiest page: real symbol bodies, pins, wires and net aliases,
    framed to the drawn content (imported designs often use a large sheet with a small drawing)."""
    if not pages:return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><text x="4" y="20">Empty design</text></svg>'
    pg = max(pages, key=lambda p: sum(len(q['pins']) for q in p['parts']) + 20 * len({q['value'] for q in p['parts']}))
    X0, Y0, W, H = 0, 0, max(pg['width'], 600), max(pg['height'], 400)
    xs = [v for part in pg['parts'] for v in [part['x']] + [q for p in part['pins'] for q in (p['hx'], p['sx'])]]
    ys = [v for part in pg['parts'] for v in [part['y']] + [q for p in part['pins'] for q in (p['hy'], p['sy'])]]
    xs += [v for w in pg['wires'] for v in (w[0], w[2])]; ys += [v for w in pg['wires'] for v in (w[1], w[3])]
    if xs and not preserve_page:
        cx0, cy0, cx1, cy1 = min(xs) - 120, min(ys) - 120, max(xs) + 120, max(ys) + 230
        cw, ch = max(cx1 - cx0, 640), max(cy1 - cy0, 420)
        if cw * ch < 0.6 * W * H or cx1 > W or cy1 > H or cx0 < 0 or cy0 < 0:X0, Y0, W, H = cx0, cy0, cw, ch
    body, pinc, wirec, textc, labc = '#8c1d18', '#8c1d18', '#1a3fbf', '#14206b', '#0b0b0b'
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0} {Y0} {W} {H}" font-family="Arial, Helvetica, sans-serif">',
         '<defs><pattern id="g" width="10" height="10" patternUnits="userSpaceOnUse"><circle cx="0" cy="0" r=".55" fill="#c9c3a8"/></pattern></defs>',
         f'<rect x="{X0}" y="{Y0}" width="{W}" height="{H}" fill="#fffef4"/><rect x="{X0}" y="{Y0}" width="{W}" height="{H}" fill="url(#g)"/>',
         f'<rect x="{X0 + 20}" y="{Y0 + 20}" width="{W - 40}" height="{H - 40}" fill="none" stroke="#7a7356" stroke-width="2"/>']
    tb_w, tb_h = 520, 90
    tx, ty = X0 + W - 20 - tb_w, Y0 + H - 20 - tb_h
    nets = len({a['name'] for a in pg['aliases']})
    o.append(f'<g stroke="#7a7356" stroke-width="1.5" fill="#fffef4"><rect x="{tx}" y="{ty}" width="{tb_w}" height="{tb_h}"/>'
             f'<line x1="{tx}" y1="{ty + 40}" x2="{tx + tb_w}" y2="{ty + 40}"/><line x1="{tx + 330}" y1="{ty + 40}" x2="{tx + 330}" y2="{ty + tb_h}"/></g>'
             f'<text x="{tx + 10}" y="{ty + 28}" font-size="20" font-weight="bold" fill="{textc}">{_esc(title or "OrCAD Capture design")}</text>'
             f'<text x="{tx + 10}" y="{ty + 62}" font-size="13" fill="#4b4630">Native OrCAD Capture .DSN · {_esc(pg["name"])}</text>'
             f'<text x="{tx + 10}" y="{ty + 80}" font-size="13" fill="#4b4630">{_esc(subtitle)}</text>'
             f'<text x="{tx + 340}" y="{ty + 62}" font-size="13" fill="#4b4630">{len(pg["parts"])} parts</text>'
             f'<text x="{tx + 340}" y="{ty + 80}" font-size="13" fill="#4b4630">{nets} nets</text>')
    for part in pg['parts']:
        t = _place(part)
        o.append(f'<g class="part" data-ref="{_esc(part["ref"])}" stroke="{body}" stroke-width="1.6" fill="none">')
        for v in part['vectors']:
            kind, n = v[0], v[1:]
            if kind == 'LINE':
                (a, b), (c, d) = t(n[0], n[1]), t(n[2], n[3])
                o.append(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}"/>')
            elif kind in ('BOX', 'ELLIPSE'):
                (a, b), (c, d) = t(n[0], n[1]), t(n[2], n[3])
                x0, y0, x1, y1 = min(a, c), min(b, d), max(a, c), max(b, d)
                o.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="#fff9e6"/>' if kind == 'BOX' else
                         f'<ellipse cx="{(x0 + x1) / 2}" cy="{(y0 + y1) / 2}" rx="{(x1 - x0) / 2}" ry="{(y1 - y0) / 2}"/>')
            elif kind == 'ARC':
                (a, b), (c, d) = t(n[0], n[1]), t(n[2], n[3])
                rx, ry = abs(c - a) / 2, abs(d - b) / 2
                (sx, sy), (ex, ey) = t(n[4], n[5]), t(n[6], n[7])
                o.append(f'<path d="M{sx} {sy} A{rx} {ry} 0 0 0 {ex} {ey}"/>' if (sx, sy) != (ex, ey) else
                         f'<ellipse cx="{(a + c) / 2}" cy="{(b + d) / 2}" rx="{rx}" ry="{ry}"/>')
            elif kind == 'POLY':
                pts = ' '.join(f'{x},{y}' for x, y in (t(n[i], n[i + 1]) for i in range(1, len(n) - 1, 2)))
                o.append(f'<{"polygon" if n[0] else "polyline"} points="{pts}"/>')
        o.append('</g>')
        xs = [p['hx'] for p in part['pins']] + [p['sx'] for p in part['pins']] or [part['x']]
        ys = [p['hy'] for p in part['pins']] + [p['sy'] for p in part['pins']] or [part['y']]
        for p in part['pins']:
            o.append(f'<line x1="{p["hx"]}" y1="{p["hy"]}" x2="{p["sx"]}" y2="{p["sy"]}" stroke="{pinc}" stroke-width="1.4"/>')
            if p['dot']:o.append(f'<circle cx="{p["sx"] + (2.5 if p["hx"] > p["sx"] else -2.5)}" cy="{p["sy"]}" r="2.5" fill="#fffef4" stroke="{pinc}"/>')
            horiz = p['hy'] == p['sy']
            mx, my = (p['hx'] + p['sx']) / 2, (p['hy'] + p['sy']) / 2
            if horiz:o.append(f'<text x="{mx}" y="{my - 2}" font-size="6.5" text-anchor="middle" fill="#5d5d5d">{_esc(p["number"])}</text>')
            else:o.append(f'<text x="{mx + 2}" y="{my + 2}" font-size="6.5" fill="#5d5d5d">{_esc(p["number"])}</text>')
            if p['name'] and p['name'] != p['number'] and horiz and len(part['pins']) > 3:
                inward = 1 if p['hx'] < p['sx'] else -1
                o.append(f'<text x="{p["sx"] + 3 * inward}" y="{p["sy"] + 2.5}" font-size="6.5" text-anchor="{"start" if inward > 0 else "end"}" fill="{textc}">{_esc(p["name"])}</text>')
        x0, y0, y1 = min(xs), min(ys), max(ys)
        o.append(f'<text x="{x0}" y="{y0 - 6}" font-size="11" font-weight="bold" fill="{textc}">{_esc(part["ref"])}</text>')
        o.append(f'<text x="{x0}" y="{y1 + 14}" font-size="10" fill="{textc}">{_esc(part["value"])}</text>')
    ends = {}
    for x1, y1, x2, y2 in pg['wires']:
        o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{wirec}" stroke-width="1.6"/>')
        ends[(x2, y2)] = (x1, y1); ends.setdefault((x1, y1), (x2, y2))
    for a in pg['aliases']:
        fx, fy = ends.get((a['x'], a['y']), (a['x'] - 1, a['y']))
        if fy == a['y']:
            left = a['x'] < fx
            o.append(f'<text x="{a["x"] + (-2 if left else 2)}" y="{a["y"] + 3}" font-size="8" text-anchor="{"end" if left else "start"}" fill="{labc}">{_esc(a["name"])}</text>')
        else:
            up = a['y'] < fy
            o.append(f'<text x="{a["x"]}" y="{a["y"] + (-3 if up else 9)}" font-size="8" text-anchor="middle" fill="{labc}">{_esc(a["name"])}</text>')
    for g in pg['globals']:
        x, y = g['x'], g['y']
        o.append(f'<g stroke="{wirec}" stroke-width="1.6"><line x1="{x}" y1="{y}" x2="{x}" y2="{y + 8}"/><line x1="{x - 10}" y1="{y + 8}" x2="{x + 10}" y2="{y + 8}"/>'
                 f'<line x1="{x - 6}" y1="{y + 12}" x2="{x + 6}" y2="{y + 12}"/><line x1="{x - 2}" y1="{y + 16}" x2="{x + 2}" y2="{y + 16}"/></g>'
                 f'<text x="{x + 12}" y="{y + 12}" font-size="8" fill="{labc}">{_esc(g["name"])}</text>')
    o.append('</svg>')
    return '\n'.join(o)


def capture_exe():
    root = orcad_root()
    exe = root and root / 'tools/bin/Capture.exe'
    return exe if exe and exe.is_file() else None


def project_file(dsn_name, libraries=None):
    """A Capture project (.opj) for the design. Opening a bare .DSN makes Capture stop at a
    'Select Project Type' dialog; the project opens straight into the design."""
    libraries = [libraries] if isinstance(libraries, str) else libraries or []
    lib = ''.join(f'\n      (File ".\\{l}"\n        (Type "Schematic Library"))' for l in libraries)
    return f'''(ExpressProject "{Path(dsn_name).stem}"
  (ProjectVersion "19981106")
  (ProjectType "PCB")
  (Folder "Design Resources"
    (Folder "Library"{lib})
    (File ".\\{dsn_name.lower()}"
      (Type "Schematic Design"))
    (BuildFileAddedOrDeleted "x")
    (CompileFileAddedOrDeleted "x"))
  (Folder "Layout")
  (Folder "Outputs")
  (Folder "Referenced Projects")
  (Folder "Logs"))
'''


def _capture_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Capture.exe', '/NH'], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return True  # unknown: leave lock files alone
    return 'capture.exe' in out.lower()


def launch(dsn):
    """Open the design's project in the installed OrCAD Capture on this computer's desktop."""
    exe = capture_exe()
    if not exe:raise OperationError('OrCAD Capture.exe was not found. Set ORCAD_ROOT to the OrCAD X folder.')
    dsn = Path(dsn)
    if not dsn.is_file():raise OperationError('Generate the OrCAD design first.')
    target = next(dsn.parent.glob('*.opj'), None) or dsn
    if not _capture_running():
        for lock in dsn.parent.glob('*lck'):lock.unlink(missing_ok=True)  # stale locks open the project read-only
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([str(exe), str(target)], cwd=str(dsn.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return str(target)


def save_to_project(project_dir, name, graph, cache_dir, source=None,*,preserve_connections=False):
    """Export, verify and keep the design in <project>/orcad with a rendered preview and a status record."""
    data, report = export(name, graph, cache_dir,**({'preserve_connections':True} if preserve_connections else {}))
    out = Path(project_dir) / 'orcad'
    out.mkdir(exist_ok=True)
    for old in out.iterdir():
        if old.is_file():old.unlink()
        elif old.is_dir():shutil.rmtree(old)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            (out / n).parent.mkdir(parents=True, exist_ok=True); (out / n).write_bytes(z.read(n))
    dsn = next(out.glob('*.DSN'))
    try:
        pages = drawing(dsn)
        (out / 'preview.svg').write_text(svg(pages, name, preserve_page=bool(placement(graph['components']))), encoding='utf-8')
        rendered, preview_error = sum(len(p['parts']) for p in pages), None
    except OperationError as e:
        rendered, preview_error = 0, str(e)
    for lock in out.glob('*.DSNlck'):lock.unlink(missing_ok=True)
    status = {'generated_symbols': report.get('generated_symbols', []), 'corrections': report.get('corrections', []),'design': dsn.name, 'size': dsn.stat().st_size, 'passed': report['passed'], 'components': report['components'],
              'checked_pins': report['checked_pins'], 'nets': len({n['name'] for n in graph.get('nets', []) if n.get('nodes')}),
              'rendered_parts': rendered, 'preview_error': preview_error,
              'implicit_power_pins': len(report.get('implicit_power_pins', [])), 'substitutions': report.get('substitutions', {}),
              'footprints': report.get('footprints'), 'user_libraries': report.get('user_libraries', {}), 'netlist': report.get('netlist'),
              'routing': report.get('routing'),
              'source_layout': report.get('source_layout'),
              'source': source, 'sha256': hashlib.sha256(dsn.read_bytes()).hexdigest()}
    (out / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return data, status


def project_status(project_dir):
    """The project's last generated OrCAD design, or None."""
    out = Path(project_dir) / 'orcad'
    if (out / 'status.json').is_file():return json.loads((out / 'status.json').read_text(encoding='utf-8'))
    dsn = next(out.glob('*.DSN'), None) if out.is_dir() else None
    if not dsn:return None
    ver = json.loads((out / 'verification.json').read_text()) if (out / 'verification.json').is_file() else {}
    return {'design': dsn.name, 'size': dsn.stat().st_size, 'passed': ver.get('passed', False), 'components': ver.get('components', 0),
            'checked_pins': ver.get('checked_pins', 0), 'nets': None, 'source': None}
