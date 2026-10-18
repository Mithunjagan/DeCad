"""Supported Cadence adapters; binary Allegro geometry is explicitly unavailable."""
import math
import ctypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from . import orcad_capture as oc
from .component_formats import base_record, validate
from .engine import OperationError
from .sexpr import Atom, expr, num, dump


def capture_runtime():
    root = oc.orcad_root()
    version = 'unknown'
    if root and os.name == 'nt':
        try:
            api = ctypes.windll.version
            file = str(root/'tools/bin/orDb_Dll_Tcl64.dll')
            size = api.GetFileVersionInfoSizeW(file, None)
            buffer = ctypes.create_string_buffer(size)
            if size and api.GetFileVersionInfoW(file,0,size,buffer):
                pointer, length = ctypes.c_void_p(), ctypes.c_uint()
                if api.VerQueryValueW(buffer,'\\',ctypes.byref(pointer),ctypes.byref(length)):
                    fixed = ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint32))
                    version = f'{fixed[2]>>16}.{fixed[2]&65535}.{fixed[3]>>16}.{fixed[3]&65535}'
                # Cadence's DLL fixed-file version may be 6.0 while ProductVersion
                # identifies the supported EDA release (26.1.0 d001 on this host).
                if api.VerQueryValueW(buffer,'\\VarFileInfo\\Translation',ctypes.byref(pointer),ctypes.byref(length)):
                    translation = ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint16))
                    query = f'\\StringFileInfo\\{translation[0]:04x}{translation[1]:04x}\\ProductVersion'
                    if api.VerQueryValueW(buffer,query,ctypes.byref(pointer),ctypes.byref(length)):
                        version = ctypes.wstring_at(pointer.value).strip()
        except (OSError,ValueError):
            pass
    return dict(installed=bool(root),version=version,supported=bool(root) and version.startswith('26.1.'),
                license='checked by native operation; presence alone does not establish license availability')


def require_capture():
    runtime = capture_runtime()
    if not runtime['supported']:
        raise OperationError(f"Unified Capture adapter is verified for 26.1; detected {runtime['version']}. Metadata cataloging remains available.")
    return runtime


def capture_packages(path):
    require_capture()
    for line in oc._run(oc.orcad_root(), 'component_capture.tcl', Path(path)).splitlines():
        fields = oc._tcl_list(line)
        if fields and fields[0] == 'PACKAGE':
            yield fields[1], fields[2]


def capture_symbol(path, name):
    runtime = require_capture()
    record = base_record(name, 'symbol', path, 'Capture API '+runtime['version'])
    issues = []
    found = False
    for line in oc._run(oc.orcad_root(), 'component_capture.tcl', Path(path), name).splitlines():
        f = oc._tcl_list(line)
        if not f:
            continue
        if f[0] == 'PACKAGE':
            found = True
            record['footprint_identifier'] = f[2]
        elif f[0] == 'PROPERTY':
            if f[1] in ('MPN','Manufacturer Part Number'):
                record['manufacturer_part_number'] = f[2]
            elif f[1] == 'Description':record['description'] = f[2]
            elif f[1] == 'Package':record['package'] = f[2]
            elif f[1] in ('Datasheet','Data Sheet') and f[2] not in record['datasheets']:
                record['datasheets'].append(f[2])
        elif f[0] == 'PIN':
            hx, hy, sx, sy = (float(x)*0.254 for x in f[4:8])
            record['pins'].append(dict(unit=int(f[1]), number=f[2], name=f[3],
                x=hx, y=-hy, length=math.hypot(sx-hx, sy-hy),
                angle=math.degrees(math.atan2(hy-sy, sx-hx)) % 360, electrical_type=f[8],source_electrical_type=f[9]))
        elif f[0] == 'VECTOR':
            x1, y1, x2, y2 = (float(x)*0.254 for x in f[3:7])
            if f[2] == 'BOX':
                node = expr('rectangle', expr('start', num(x1), num(-y1)), expr('end', num(x2), num(-y2)))
            else:
                node = expr('polyline', expr('pts', expr('xy', num(x1), num(-y1)), expr('xy', num(x2), num(-y2))))
            node.extend([expr('stroke', expr('width', num(0)), expr('type', Atom('default'))),
                         expr('fill', expr('type', Atom('none')))])
            record['symbol_geometry'].append(dict(unit=int(f[1]), style=1, sexpr=dump(node)))
        elif f[0] == 'UNSUPPORTED_VECTOR':
            issues.append(f'Capture vector type {f[2]} is not converted.')
    if not found:
        raise OperationError(f'Package {name} not found in Capture library.')
    record['validation'] = validate(record)
    if issues:
        record['validation']['status'] = 'partial'
        record['validation']['issues'] += sorted(set(issues))
    return record


def project_metadata(path):
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    if not text.lstrip().startswith('('):
        raise OperationError('Unrecognized Capture project metadata.')
    record = base_record(Path(path).stem, 'project', path)
    record['references'] = sorted(set(re.findall(r'"([^"\r\n]+\.(?:dsn|olb|brd))"', text, re.I)))
    record['validation'] = dict(status='metadata_only', issues=['Project references only; no implicit file access.'])
    return record


def capture_export(record, cache):
    """Native OLB -> native package-only OLB, independently reopened and checked.

    Does not claim KiCad -> OLB or any Allegro binary writer. All intermediate
    designs and locks are confined to an application-owned temporary directory.
    """
    require_capture()
    cache = Path(cache);cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        folder = Path(temporary)
        design, library = folder/'component.DSN', folder/'component.olb'
        # Capture's design writer may lock an opened library. Give it a private
        # licensed copy, so native export cannot create locks in an installation.
        source = folder/'source.olb'
        shutil.copyfile(record['original_library_path'],source)
        name = record['name']
        graph = {'components':[{'ref':'U1','value':name}], 'nets':[]}
        oc._write(oc.orcad_root(),folder,design,folder/'unused.olb',graph,
                  {'U1':(str(source),name,'native source')}, {}, {})
        oc.extract_parts(design,library)
        reopened = capture_symbol(library,name)
        pin_fields = ('unit','number','name','x','y','angle','length')
        signature = lambda c: sorted(tuple(p[k] for k in pin_fields) for p in c['pins'])
        if signature(record) != signature(reopened) or record['symbol_geometry'] != reopened['symbol_geometry']:
            raise OperationError('Native component export did not pass independent pin/geometry readback.')
        return library.read_bytes()
