"""Native KiCad project operations. Connectivity always comes from KiCad XML."""
from __future__ import annotations
import copy
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections import OrderedDict
import xml.etree.ElementTree as ET
from pathlib import Path
from .sexpr import Atom as A, child, children, dump, expr as E, num as N, parse

class OperationError(ValueError):
    pass

LOCKS = {}
LOCK_GUARD = threading.Lock()
CLI_LIMIT = threading.BoundedSemaphore(2)
CACHE_LOCK = threading.Lock()
EXPORT_CACHE = OrderedDict()

def project_lock(path):
    with LOCK_GUARD:
        return LOCKS.setdefault(str(path), threading.RLock())

def uid():
    return str(uuid.uuid4())

def atomic_text(path, text):
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf-8') as f:
        f.write(text)
        temp = Path(f.name)
    temp.replace(path)
    if path.suffix == '.kicad_sch':
        # Fingerprint of DeCad's own write: the desktop shell reloads the docked KiCad editor when the file on disk
        # matches it, and treats any other change as a save made in KiCad.
        import hashlib
        (path.parent / f'.{path.name}.decad-sha').write_text(hashlib.sha256(path.read_bytes()).hexdigest())

def find_cli():
    return os.getenv('KICAD_CLI') or shutil.which('kicad-cli') or '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def run_cli(*args):
    if not CLI_LIMIT.acquire(timeout=10):raise OperationError('KiCad is busy. Retry after the current checks finish.')
    try:
        result = subprocess.run([find_cli(), *map(str, args)], stdin=subprocess.DEVNULL,capture_output=True, text=True, timeout=90)
    except FileNotFoundError as e:
        raise OperationError('KiCad CLI is unavailable. Start the Docker package or configure KICAD_CLI.') from e
    except subprocess.TimeoutExpired as e:
        raise OperationError('KiCad operation timed out.') from e
    finally:CLI_LIMIT.release()
    if result.returncode:
        raise OperationError((result.stderr or result.stdout or 'KiCad operation failed').strip()[-3000:])
    return result

LIBRARY_CACHE = {}

def library_dir():
    candidates = [
        os.getenv('KICAD_SYMBOL_DIR',''),
        str(Path(__file__).resolve().parents[2] / 'libraries' / 'kicad' / 'official' / 'symbols'),
        '/usr/share/kicad/symbols',
        '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols'
    ]
    return next((Path(p) for p in candidates if p and Path(p).is_dir()), None)

def find_symbol_library_path(name):
    if not name or any(x in name for x in ['/', '\\', '..']):
        raise OperationError('Invalid symbol library identifier.')
    search_dirs = [
        library_dir(),
        Path(__file__).resolve().parents[2] / 'libraries' / 'kicad' / 'community' / 'digikey',
        Path(__file__).resolve().parents[2] / 'libraries' / 'kicad' / 'community' / 'sparkfun',
        Path(__file__).resolve().parents[2] / 'libraries' / 'kicad' / 'community' / 'seeed'
    ]
    for folder in search_dirs:
        if folder and folder.is_dir():
            target_sym = folder / f'{name}.kicad_sym'
            if target_sym.is_file():
                return target_sym
            target_dir = folder / f'{name}.kicad_symdir'
            if target_dir.is_dir():
                return target_dir
            for nested in folder.rglob(f'{name}.kicad_sym'):
                if nested.is_file():
                    return nested
            for nested_dir in folder.rglob(f'{name}.kicad_symdir'):
                if nested_dir.is_dir():
                    return nested_dir
    return None

def load_library(name):
    target = find_symbol_library_path(name)
    if not target:
        raise OperationError(f'KiCad symbol library {name} is unavailable.')
    if name not in LIBRARY_CACHE:
        catalog = {}
        if target.is_dir():
            for f in target.glob('*.kicad_sym'):
                try:
                    tree = parse(f.read_text())
                    for s in children(tree, 'symbol'):
                        if len(s) > 1 and isinstance(s[1], str):
                            catalog[s[1]] = s
                except Exception:
                    pass
        else:
            tree = parse(target.read_text())
            catalog = {s[1]: s for s in children(tree, 'symbol')}
        LIBRARY_CACHE[name] = catalog
    return LIBRARY_CACHE[name]

def library_symbol(lib_id):
    if ':' not in lib_id:
        raise OperationError('Symbol must be specified as Library:Name.')
    lib, name = lib_id.split(':',1)
    catalog = load_library(lib)
    def resolve(symbol_name, visited):
        if symbol_name in visited or symbol_name not in catalog:
            raise OperationError(f'Unknown or cyclic symbol {lib}:{symbol_name}')
        s = copy.deepcopy(catalog[symbol_name])
        ext = child(s,'extends')
        if ext:
            base = resolve(ext[1], visited | {symbol_name})
            overrides = {p[1]:p for p in children(s,'property')}
            result = [A('symbol'),symbol_name]
            for item in base[2:]:
                if isinstance(item,list) and item[0]=='property':
                    result.append(overrides.pop(item[1],item))
                elif isinstance(item,list) and item[0]=='symbol':
                    item[1] = symbol_name + item[1][len(base[1]):]
                    result.append(item)
                else:
                    result.append(item)
            result.extend(overrides.values())
            s = result
        return s
    s = resolve(name,set())
    s[1] = lib_id
    return s

DEFAULT_SYMBOLS = {'R':'Device:R','C':'Device:C','L':'Device:L','D':'Device:D','Q':'Transistor_BJT:Q_NPN_BCE','V':'Simulation_SPICE:VDC','I':'Simulation_SPICE:IDC','J':'Connector_Generic:Conn_01x02'}
CONNECTOR_PREFIXES = ('P','J','CN','CON','X')

def effects():
    return E('effects',E('font',E('size',N(1.27),N(1.27))))

def pin_key(pin):
    m = re.fullmatch(r'([A-Za-z]*)(\d*)(.*)', str(pin))
    return (m.group(1).upper(), int(m.group(2)) if m.group(2) else -1, m.group(3))

def connector_symbol(pins):
    """Connector_Generic symbol for a connector whose pins are numbered 1..N, else None."""
    if not pins or not all(str(p).isdigit() for p in pins):return None
    n = max(int(p) for p in pins)
    if n <= 60:return f'Connector_Generic:Conn_01x{n:02d}'
    if n <= 100:return f'Connector_Generic:Conn_02x{(n + 1) // 2:02d}_Odd_Even'
    return None

def generated_symbol(ref, value, pins):
    """A box symbol carrying exactly the given pins, for parts that no KiCad library has (e.g. a DIN 41612 connector with
    pins A5, B26, C20). Embedded in the schematic as DeCad:<value>_<ref>."""
    name = re.sub(r'[^A-Za-z0-9_.+-]', '_', f'{value or "PART"}_{ref}')
    pins = sorted({str(p) for p in pins}, key=pin_key)
    left = pins[:(len(pins) + 1) // 2]; right = pins[len(left):]
    h = max(len(left), 1) * 2.54 / 2 + 1.27
    font = lambda: effects()
    body = [A('symbol'), f'{name}_0_1', E('rectangle',E('start',N(-7.62),N(round(h,2))),E('end',N(7.62),N(round(-h,2))),
            E('stroke',E('width',N(0.254)),E('type',A('default'))),E('fill',E('type',A('background'))))]
    unit = [A('symbol'), f'{name}_1_1']
    for side, column in ((-1, left), (1, right)):
        for i, pin in enumerate(column):
            y = round((len(left) - 1) * 1.27 - 2.54 * i, 2)
            unit.append(E('pin',A('passive'),A('line'),E('at',N(side*12.7),N(y),N(0 if side < 0 else 180)),E('length',N(5.08)),
                          E('name','~',font()),E('number',pin,font())))
    prefix = re.match(r'[A-Za-z]*', ref).group(0) or 'U'
    props = [E('property',key,val,E('at',N(0),N(round(h + 1.27 + 2.54 * i, 2)),N(0)),font()) for i,(key,val) in
             enumerate((('Reference',prefix),('Value',value or name),('Footprint',''),('Datasheet','')))]
    return [A('symbol'), f'DeCad:{name}', E('pin_names',E('offset',N(1.016))), E('in_bom',A('yes')), E('on_board',A('yes')), *props, body, unit]

class Schematic:
    def __init__(self, project):
        self.project = Path(project)
        self.path = next(self.project.glob('*.kicad_sch'),None)
        if not self.path:
            raise OperationError('Project has no KiCad schematic.')
        try:
            self.tree = parse(self.path.read_text())
        except (ValueError, OSError) as e:
            raise OperationError(f'Invalid schematic source: {e}') from e
        if not self.tree or self.tree[0] != 'kicad_sch':
            raise OperationError('Invalid KiCad schematic.')
        if not child(self.tree,'uuid'):
            self.tree.insert(3,E('uuid',uid()))

    @staticmethod
    def create(project, name):
        project.mkdir(parents=True)
        tree = E('kicad_sch', E('version',A('20231120')),E('generator',A('eeschema')),E('uuid',uid()), E('paper','A4'), E('lib_symbols'))
        atomic_text(project/f'{name}.kicad_sch',dump(tree)+'\n')
        atomic_text(project/f'{name}.kicad_pro',json.dumps({'meta':{'version':1}}))

    def save(self):
        atomic_text(self.path,dump(self.tree)+'\n')

    def symbols(self):
        return [s for s in children(self.tree,'symbol') if child(s,'lib_id')]

    def reference(self,s):
        return next((p[2] for p in children(s,'property') if p[1]=='Reference'),'')

    def get(self,ref):
        return next((s for s in self.symbols() if self.reference(s)==ref),None)

    def property(self,s,name):
        return next((p[2] for p in children(s,'property') if p[1]==name),'')

    def add(self, ref, value, lib_id=None, footprint=None, x=None,y=None, pins=None, definition=None):
        """pins: the pin numbers the circuit uses, when known (imports). A part with no library symbol then gets a
        generated one with exactly these pins instead of an error."""
        if self.get(ref):
            raise OperationError(f'{ref} already exists. Use change/set to update it.')
        if definition is not None and not lib_id:
            raise OperationError('An imported symbol definition needs a library identifier.')
        connector = re.match(r'[A-Za-z]*', ref).group(0).upper() in CONNECTOR_PREFIXES or 'CONN' in str(value).upper()
        if not lib_id and pins and connector:
            lib_id = connector_symbol(pins)
            if not lib_id:definition = generated_symbol(ref, value, pins); lib_id = definition[1]
        if not lib_id:
            if ref.startswith('U'):
                matches = []
                for library in ['74xx','Amplifier_Operational','Timer','MCU_ST_STM32F4','Memory_RAM']:
                    try:
                        if value in load_library(library): matches.append(f'{library}:{value}')
                    except OperationError: pass
                if not matches:
                    db_path = Path(__file__).resolve().parents[2] / 'libraries' / 'index' / 'components.db'
                    if db_path.exists():
                        try:
                            import sqlite3
                            with sqlite3.connect(str(db_path)) as conn:
                                cur = conn.cursor()
                                cur.execute("SELECT lib_id FROM symbols WHERE name = ? COLLATE NOCASE LIMIT 5", (value,))
                                rows = cur.fetchall()
                                matches.extend(r[0] for r in rows)
                        except Exception: pass
                if len(matches)>1 and pins:
                    # several libraries carry this part number: take the first whose pins cover the circuit's
                    fits = [m for m in matches if self._has_pins(m, pins)]
                    matches = fits[:1]
                if not matches and pins:
                    definition = generated_symbol(ref, value, pins); matches = [definition[1]]
                if len(matches)!=1:
                    raise OperationError(f'{ref} ({value}) has no unique KiCad symbol (found: {matches if matches else "none"}). '
                                         f'Enter it in the KiCad symbol column as Library:Symbol, or use "Generate verified OrCAD .DSN", which needs no KiCad symbols.')
                lib_id=matches[0]
            else:
                lib_id=DEFAULT_SYMBOLS.get(ref[0])
                if not lib_id and pins:definition = generated_symbol(ref, value, pins); lib_id = definition[1]
                if not lib_id: raise OperationError(f'{ref} ({value}) has no default KiCad symbol. Enter it in the KiCad symbol column as Library:Symbol '
                                                    f'(e.g. Connector_Generic:Conn_01x40), or use "Generate verified OrCAD .DSN", which needs no KiCad symbols.')
        definition=definition or library_symbol(lib_id)
        lib=child(self.tree,'lib_symbols')
        if lib is None:
            lib=E('lib_symbols');self.tree.append(lib)
        if not any(s[1]==lib_id for s in children(lib,'symbol')):lib.append(definition)
        idx=len(self.symbols())
        if x is None:
            col = idx % 6
            x = 38.0 + col * 36.0
        else:
            x = float(x)
        if y is None:
            row = (idx // 6) % 5
            y = 35.0 + row * 28.0
        else:
            y = float(y)
        symbol_id=uid()
        s=E('symbol',E('lib_id',lib_id),E('at',N(x),N(y),N(0)),E('unit',A('1')),E('in_bom',A('yes')),E('on_board',A('yes')),E('dnp',A('no')),E('uuid',symbol_id))
        props={'Reference':ref,'Value':value,'Footprint':footprint or next((p[2] for p in children(definition,'property') if p[1]=='Footprint'),''),'Datasheet':next((p[2] for p in children(definition,'property') if p[1]=='Datasheet'),'')}
        for i,(key,val) in enumerate(props.items()):
            e=effects()
            if i>1:e.append(E('hide',A('yes')))
            s.append(E('property',key,val,E('at',N(x+5.08),N(y+i*2.54),N(0)),e))
        for pin in self.definition_pins(definition,1):
            s.append(E('pin',child(pin,'number')[1],E('uuid',uid())))
        root_id=child(self.tree,'uuid')[1]
        s.append(E('instances',E('project',self.project.name,E('path','/'+root_id,E('reference',ref),E('unit',A('1'))))))
        self.tree.append(s)
        return {'ref':ref,'value':value,'library':lib_id,'action':'added'}

    def set_value(self,ref,value):
        s=self.get(ref)
        if not s:raise OperationError(f'{ref} does not exist.')
        prop=next(p for p in children(s,'property') if p[1]=='Value');prop[2]=value
        return {'ref':ref,'value':value,'action':'modified'}

    def remove(self,ref):
        s=self.get(ref)
        if not s:raise OperationError(f'{ref} does not exist.')
        # Remove labels anchored to this component's pins. Preserve other user geometry.
        positions={(round(x,4),round(y,4)) for x,y in self.pin_positions(s).values()}
        self.tree[:]=[n for n in self.tree if n is not s and not (isinstance(n,list) and n and n[0]=='label' and (round(float(child(n,'at')[1]),4),round(float(child(n,'at')[2]),4)) in positions)]
        return {'ref':ref,'action':'removed'}

    def _has_pins(self, lib_id, pins):
        try:have = {str(child(p,'number')[1]) for p in self.definition_pins(library_symbol(lib_id),1)}
        except OperationError:return False
        return {str(p) for p in pins} <= have

    def definition_pins(self,definition,unit):
        pins=[]
        for block in children(definition,'symbol'):
            suffix=block[1].rsplit('_',2)
            if len(suffix)==3 and suffix[1] in ('0',str(unit)) and suffix[2] in ('0','1'):
                pins.extend(children(block,'pin'))
        return pins

    def pin_positions(self,s):
        lib=child(self.tree,'lib_symbols');lib_id=child(s,'lib_id')[1]
        definition=next((d for d in children(lib,'symbol') if d[1]==lib_id),None)
        if definition is None:raise OperationError(f'Embedded symbol {lib_id} missing.')
        at=child(s,'at');cx,cy,angle=map(float,at[1:4]); theta=math.radians(angle)
        mirror=child(s,'mirror');result={}
        for p in self.definition_pins(definition,int(child(s,'unit',[None,1])[1])):
            a=child(p,'at');dx,dy=map(float,a[1:3])
            if mirror and mirror[1]=='x':dy=-dy
            if mirror and mirror[1]=='y':dx=-dx
            x=cx+dx*math.cos(theta)-dy*math.sin(theta)
            y=cy-(dx*math.sin(theta)+dy*math.cos(theta))
            result[str(child(p,'number')[1])]=(x,y)
        return result

    def connect(self,net,nodes):
        if not nodes:raise OperationError('Specify at least one component pin, for example connect net GND to R1 pin 2.')
        edits=[]
        pin_coords = []
        for ref,pin in nodes:
            s=self.get(ref)
            if not s:raise OperationError(f'Unknown component {ref}.')
            pos=self.pin_positions(s).get(str(pin))
            if not pos:raise OperationError(f'{ref} has no pin {pin}.')
            x,y=pos
            pin_coords.append((x,y))
            existing=next((l for l in children(self.tree,'label') if abs(float(child(l,'at')[1])-x)<1e-4 and abs(float(child(l,'at')[2])-y)<1e-4),None)
            if existing:existing[1]=net
            else:self.tree.append(E('label',net,E('at',N(x),N(y),N(0)),effects(),E('uuid',uid())))
            edits.append({'ref':ref,'pin':str(pin),'net':net,'action':'connected'})
        
        # Route orthogonal wires between pins on the same net. Labels already carry the
        # connectivity, so a wire is drawn only when it cannot touch another net.
        if len(pin_coords) >= 2:
            for i in range(len(pin_coords) - 1):
                x1, y1 = pin_coords[i]
                x2, y2 = pin_coords[i+1]
                if abs(x1 - x2) < 1e-4 or abs(y1 - y2) < 1e-4:
                    candidates = [[((x1, y1), (x2, y2))]]
                else:
                    candidates = [[((x1, y1), (cx, cy)), ((cx, cy), (x2, y2))] for cx, cy in ((x2, y1), (x1, y2))]
                route = next((c for c in candidates if self._route_clear(net, c, {(x1, y1), (x2, y2)})), None)
                if not route:
                    continue
                for a, b in route:
                    self.tree.append(E('wire', E('pts', E('xy', N(a[0]), N(a[1])), E('xy', N(b[0]), N(b[1]))),
                                       E('stroke', E('width', N(0)), E('type', A('default'))), E('uuid', uid())))
        return edits

    def _route_clear(self, net, segments, own):
        def on(p, a, b):
            (px, py), (ax, ay), (bx, by) = p, a, b
            if abs(ax - bx) < 1e-4:
                return abs(px - ax) < 1e-4 and min(ay, by) - 1e-4 <= py <= max(ay, by) + 1e-4
            return abs(py - ay) < 1e-4 and min(ax, bx) - 1e-4 <= px <= max(ax, bx) + 1e-4
        def mine(p):
            return any(abs(p[0] - o[0]) < 1e-4 and abs(p[1] - o[1]) < 1e-4 for o in own)
        labels = {(round(float(child(l, 'at')[1]), 4), round(float(child(l, 'at')[2]), 4)): l[1] for l in children(self.tree, 'label')}
        # Any foreign pin or label on the path would join a different net.
        points = [p for s in self.symbols() for p in self.pin_positions(s).values()]
        points += [(float(child(l, 'at')[1]), float(child(l, 'at')[2])) for l in children(self.tree, 'label')]
        for p in points:
            if mine(p) or labels.get((round(p[0], 4), round(p[1], 4))) == net:
                continue
            if any(on(p, a, b) for a, b in segments):
                return False
        # Existing wires connect wherever an endpoint of one lies on the other.
        for w in children(self.tree, 'wire'):
            xy = children(child(w, 'pts'), 'xy')
            wa, wb = (float(xy[0][1]), float(xy[0][2])), (float(xy[-1][1]), float(xy[-1][2]))
            for a, b in segments:
                touches = [p for p in (a, b) if on(p, wa, wb)] + [p for p in (wa, wb) if on(p, a, b)]
                if any(not mine(p) for p in touches):
                    return False
        return True

    def cached_export(self,operation,compute):
        # Include child sheets so a hierarchy edit invalidates every derived output.
        fingerprint=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted([*self.project.rglob('*.kicad_sch'),*self.project.rglob('*.kicad_pro')]) if '.history' not in p.parts and '.redo' not in p.parts)
        key=(str(self.project.resolve()),operation,fingerprint)
        with CACHE_LOCK:
            if key in EXPORT_CACHE:
                EXPORT_CACHE.move_to_end(key)
                return copy.deepcopy(EXPORT_CACHE[key])
        result=compute()
        with CACHE_LOCK:
            EXPORT_CACHE[key]=copy.deepcopy(result)
            while len(EXPORT_CACHE)>32:EXPORT_CACHE.popitem(last=False)
        return result

    def netlist(self):return self.cached_export('netlist',self._netlist)

    def _netlist(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'net.xml';run_cli('sch','export','netlist','--format','kicadxml','-o',out,self.path)
            if not out.exists():raise OperationError('KiCad did not produce a netlist.')
            return out.read_text()

    def graph(self):
        root=ET.fromstring(self.netlist());components=[];nets=[]
        for c in root.findall('./components/comp'):
            part=c.find('libsource');fields={f.attrib['name']:f.text or '' for f in c.findall('./fields/field')}
            components.append({'ref':c.attrib['ref'],'value':c.findtext('value',''),'footprint':c.findtext('footprint',''),'library':f"{part.attrib.get('lib','')}:{part.attrib.get('part','')}" if part is not None else '', 'fields':fields})
        for net in root.findall('./nets/net'):
            nets.append({'name':net.attrib['name'].lstrip('/') if net.attrib['name'].count('/')==1 else net.attrib['name'],'class':net.attrib.get('class','Default'),'nodes':[{'ref':n.attrib['ref'],'pin':n.attrib['pin']} for n in net.findall('node')]})
        return {'components':components,'nets':nets}

    def erc(self):return self.cached_export('erc',self._erc)

    def _erc(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'erc.json';run_cli('sch','erc','--format','json','-o',out,self.path)
            if not out.exists():raise OperationError('KiCad did not produce an ERC report.')
            report=json.loads(out.read_text())
            violations=[v for s in report.get('sheets',[]) for v in s.get('violations',[])]
            violations.extend(report.get('violations',[]))
            return {'status':'completed','passed':not any(v.get('severity')=='error' for v in violations),'violations':violations,'report':report}

    def preview(self):return self.cached_export('preview',self._preview)

    def _preview(self):
        with tempfile.TemporaryDirectory() as td:
            run_cli('sch','export','svg','-o',td+'/',self.path)
            pages=sorted(Path(td).glob('*.svg'))
            if not pages:raise OperationError('KiCad did not produce an SVG preview.')
            return pages[0].read_text()
