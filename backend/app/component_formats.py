"""Format adapters for the unified library. Coordinates are millimetres.

Native binary data is never guessed. Unsupported constructs remain visible in
validation; native source trees are kept for lossless KiCad symbol exports.
"""
import copy
import hashlib
import math
import re
from pathlib import Path
from .engine import OperationError
from .sexpr import Atom, child, children, dump, expr, num, parse


def base_record(name, kind, path, version='unknown'):
    return dict(schema_version=1, name=name, kind=kind, manufacturer_part_number='',
                description='', package='', symbol_geometry=[], pins=[],
                footprint_identifier='', footprint_geometry=[], pads=[], models=[],
                datasheets=[], source_format=Path(path).suffix.lower(),
                original_library_path=str(Path(path).resolve()), source_version=str(version),
                source_license={}, validation={'status': 'metadata_only', 'issues': []})


def value(node, key, default=''):
    item = child(node, key)
    return item[1] if item and len(item) > 1 else default


def properties(node):
    return {str(p[1]): str(p[2]) for p in children(node, 'property') if len(p) > 2}


def resolve_symbol(tree, name, seen=(), loader=None):
    if name in seen:
        raise OperationError('Cyclic KiCad symbol inheritance.')
    source = next((s for s in children(tree, 'symbol') if s[1] == name), None)
    if source is None and loader:
        tree = loader(name)
        source = next((s for s in children(tree, 'symbol') if s[1] == name), None)
    if source is None:
        raise OperationError(f'KiCad parent symbol {name} is missing.')
    result = copy.deepcopy(source)
    parent = value(source, 'extends')
    if parent:
        ancestor = resolve_symbol(tree, parent, (*seen, name), loader)
        inherited = properties(result)
        for item in ancestor[2:]:
            if not isinstance(item, list) or item[0] == 'extends':
                continue
            if item[0] == 'property' and item[1] in inherited:
                continue
            if item[0] == 'symbol':
                item[1] = name + str(item[1])[len(parent):]
            if item[0] in ('property', 'symbol') or child(result, item[0]) is None:
                result.append(item)
        result = [i for i in result if not isinstance(i, list) or i[0] != 'extends']
    return result


def symbol_records(path, metadata_only=False):
    path = Path(path)
    tree = parse(Path(path).read_text(encoding='utf-8-sig'))
    if tree[0] != 'kicad_symbol_lib':
        raise OperationError('Not a KiCad symbol library.')
    version = value(tree, 'version')
    for source in children(tree, 'symbol'):
        dependencies = {}
        def load_parent(name):
            if path.parent.suffix != '.kicad_symdir':
                raise OperationError(f'KiCad parent symbol {name} is missing.')
            parent = (path.parent/(name+'.kicad_sym')).resolve()
            if not parent.is_relative_to(path.parent.resolve()) or not parent.is_file():
                raise OperationError(f'KiCad parent symbol {name} is missing.')
            data = parent.read_bytes()
            dependencies[str(parent)] = hashlib.sha256(data).hexdigest()
            return parse(data.decode('utf-8-sig'))
        definition = resolve_symbol(tree, source[1], loader=load_parent)
        props = properties(definition)
        record = base_record(str(source[1]), 'symbol', path, version)
        library = path.parent.stem if path.parent.suffix == '.kicad_symdir' else path.stem
        record['symbol_identifier'] = f'{library}:{source[1]}'
        record['dependencies'] = dependencies
        record.update(manufacturer_part_number=props.get('MPN', props.get('Manufacturer Part Number', '')),
                      description=props.get('Description', props.get('ki_description', '')),
                      footprint_identifier=props.get('Footprint', ''),
                      package=props.get('Package', ''),
                      datasheets=[props['Datasheet']] if props.get('Datasheet') and props['Datasheet'] != '~' else [])
        if not metadata_only:
            record['kicad_definition'] = dump(definition)
            for unit in children(definition, 'symbol'):
                match = re.search(r'_(\d+)_(\d+)$', str(unit[1]))
                unit_id, style = (int(match[1]), int(match[2])) if match else (1, 1)
                for pin in children(unit, 'pin'):
                    at = child(pin, 'at', ['at', 0, 0, 0])
                    record['pins'].append(dict(number=str(value(pin, 'number')), name=str(value(pin, 'name')),
                        electrical_type=str(pin[1]), x=float(at[1]), y=float(at[2]),
                        angle=float(at[3]), length=float(value(pin, 'length', 0)), unit=unit_id, style=style))
                for graphic in unit[2:]:
                    if isinstance(graphic, list) and graphic[0] in ('rectangle', 'polyline', 'circle', 'arc', 'text', 'bezier'):
                        record['symbol_geometry'].append(dict(unit=unit_id, style=style, sexpr=dump(graphic)))
            record['validation'] = validate(record)
        yield record


def footprint_record(path, metadata_only=False):
    tree = parse(Path(path).read_text(encoding='utf-8-sig'))
    if tree[0] not in ('footprint', 'module'):
        raise OperationError('Not a KiCad footprint.')
    record = base_record(str(tree[1]), 'footprint', path, value(tree, 'version'))
    record['description'] = str(value(tree, 'descr'))
    library = Path(path).parent.stem
    record['footprint_identifier'] = f'{library}:{tree[1]}'
    if not metadata_only:
        record['kicad_footprint'] = dump(tree)
        for pad in children(tree, 'pad'):
            at = child(pad, 'at', ['at', 0, 0])
            size = child(pad, 'size', ['size', 0, 0])
            drill = child(pad, 'drill', ['drill', 0])
            record['pads'].append(dict(number=str(pad[1]), type=str(pad[2]), shape=str(pad[3]),
                x=float(at[1]), y=float(at[2]), angle=float(at[3]) if len(at)>3 else 0,
                width=float(size[1]), height=float(size[2]),
                drill=[str(x) for x in drill[1:]], layers=list(child(pad, 'layers', ['layers'])[1:])))
        record['models'] = [dict(path=str(m[1]), source='footprint', transform=dump(m)) for m in children(tree, 'model')]
        record['footprint_geometry'] = [dump(g) for g in tree if isinstance(g, list) and str(g[0]).startswith('fp_')]
        record['validation'] = validate(record)
    return record


def validate(record, footprint=None):
    issues = []
    pins, pads = record.get('pins', []), record.get('pads', [])
    if record['kind'] == 'symbol' and not pins:
        issues.append('No electrical pins extracted.')
    if record['kind'] == 'footprint' and not pads:
        issues.append('No physical pads extracted.')
    for pin in pins:
        if not pin.get('number'):
            issues.append('Electrical pin without a physical number.')
        if any(not math.isfinite(float(pin.get(k, 0))) for k in ('x', 'y', 'length', 'angle')) or float(pin.get('length', 0)) < 0:
            issues.append('Non-finite symbol coordinates.')
    for pad in pads:
        if any(not math.isfinite(float(pad.get(k,0))) for k in ('x', 'y', 'width', 'height', 'angle')) or min(pad['width'], pad['height']) <= 0:
            issues.append('Invalid physical pad dimensions.')
    mapping = 'not_checked'
    if footprint:
        expected = {str(p['number']) for p in pins}
        actual = {str(p['number']) for p in footprint.get('pads', []) if p['number']}
        missing, extra = sorted(expected-actual), sorted(actual-expected)
        mapping = 'verified' if expected and actual and not missing and not extra else 'mismatch'
        if mapping != 'verified':
            issues.append(f'Pin/pad mismatch: missing pads {missing}; extra pads {extra}.')
        issues.extend(footprint.get('validation', {}).get('issues', []))
    # Structural checks cannot verify a manufacturer's mechanical tolerances.
    return dict(status='invalid' if issues else 'structurally_valid', issues=sorted(set(issues)),
                pin_to_pad=mapping, dimensions='structural_only')


def kicad_symbol(record, name=None):
    """A real library tree, retaining imported geometry and physical pin numbers."""
    name = name or re.sub(r'[^A-Za-z0-9_+-]', '_', record['name'])
    if record.get('kicad_definition'):
        node = parse(record['kicad_definition'])
        old = str(node[1]); node[1] = name
        for unit in children(node, 'symbol'):
            unit[1] = name + str(unit[1])[len(old):]
    else:
        node = expr('symbol', name, expr('pin_names', expr('offset', num(1.016))),
                    expr('in_bom', Atom('yes')), expr('on_board', Atom('yes')))
        for key, val in [('Reference', 'U'), ('Value', record['name']), ('Footprint', record.get('footprint_identifier', '')),
                         ('Datasheet', next(iter(record.get('datasheets', [])), ''))]:
            node.append(expr('property', key, val, expr('at', num(0), num(0), num(0)),
                             expr('effects', expr('font', expr('size', num(1.27), num(1.27))))))
        units = sorted({int(p.get('unit', 1)) for p in record['pins']})
        for unit_id in units:
            unit = expr('symbol', f'{name}_{unit_id}_1')
            for graphic in record.get('symbol_geometry', []):
                if graphic.get('unit', 1) == unit_id and graphic.get('sexpr'):
                    unit.append(parse(graphic['sexpr']))
            for pin in record['pins']:
                if pin.get('unit', 1) != unit_id:
                    continue
                unit.append(expr('pin', Atom(pin.get('electrical_type', 'passive')), Atom('line'),
                    expr('at', num(pin['x']), num(pin['y']), num(pin['angle'])), expr('length', num(pin['length'])),
                    expr('name', pin['name'], expr('effects', expr('font', expr('size', num(1.27), num(1.27))))),
                    expr('number', pin['number'], expr('effects', expr('font', expr('size', num(1.27), num(1.27)))))))
            node.append(unit)
    version = record.get('source_version', '')
    version = version if str(version).isdigit() and len(str(version)) == 8 else '20231120'
    return expr('kicad_symbol_lib', expr('version', Atom(str(version))), expr('generator', 'decad'), node)
