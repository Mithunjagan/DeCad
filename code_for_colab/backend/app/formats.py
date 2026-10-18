"""Connectivity-preserving exports from the authoritative KiCad graph."""
from .ground import reference_name
import json
import re
from .engine import OperationError


def ident(value):
    return 'N_' + re.sub(r'[^A-Za-z0-9_]', '_', str(value))


def quoted(value):
    # EDIF string escape differs from JSON; KiCad identifiers have no embedded quotes.
    if any(c in str(value) for c in ['"','\\','\n','\r']):
        raise OperationError('EDIF names/values must not contain quotes, backslashes, or line breaks.')
    return '"'+str(value)+'"'


def edif(name, graph):
    cell_ids={c['ref']:ident('cell_'+c['ref']) for c in graph['components']}
    pins={c['ref']:set() for c in graph['components']}
    for net in graph['nets']:
        for node in net['nodes']:
            if node['ref'] not in pins:raise OperationError('Net refers to missing component.')
            pins[node['ref']].add(node['pin'])
    out=[f'(edif {ident(name)}', '  (edifVersion 2 0 0)','  (edifLevel 0)','  (keywordMap (keywordLevel 0))','  (library COMPONENTS (edifLevel 0) (technology (numberDefinition))']
    for c in graph['components']:
        out.append(f'    (cell {cell_ids[c["ref"]]} (cellType GENERIC) (view NETLIST (viewType NETLIST) (interface')
        for pin in sorted(pins[c['ref']]):out.append(f'      (port (rename {ident(pin)} {quoted(pin)}) (direction INOUT))')
        out.append('    )))')
    out += ['  )','  (library WORK (edifLevel 0) (technology (numberDefinition))',f'    (cell {ident(name)} (cellType GENERIC) (view NETLIST (viewType NETLIST) (interface) (contents']
    for c in graph['components']:
        out += [f'      (instance (rename {ident(c["ref"])} {quoted(c["ref"])}) (viewRef NETLIST (cellRef {cell_ids[c["ref"]]} (libraryRef COMPONENTS)))',f'        (property VALUE (string {quoted(c["value"])}))',f'        (property FOOTPRINT (string {quoted(c.get("footprint",""))}))',f'        (property KICAD_SYMBOL (string {quoted(c.get("library",""))}))', '      )']
    for i,net in enumerate(graph['nets']):
        out.append(f'      (net (rename {ident(str(i)+"_"+net["name"])} {quoted(net["name"])}) (joined')
        for node in net['nodes']:
            out.append(f'        (portRef {ident(node["pin"])} (instanceRef {ident(node["ref"])}))')
        out.append('      ))')
    out += ['    )))','  )',f'  (design {ident(name+"_design")} (cellRef {ident(name)} (libraryRef WORK)))',')']
    return '\n'.join(out)+'\n'


def spice(graph, controls=None):
    controls=controls or {}
    node_map={}
    reference=reference_name(n['name'] for n in graph['nets'])
    if reference is None:raise OperationError('SPICE export requires a GND or explicitly named reference net.')
    for i,net in enumerate(graph['nets'],1):
        label=net['name']
        name='0' if label==reference else f'n{i}'
        for n in net['nodes']:node_map[(n['ref'],n['pin'])]=name
    lines=['* Schematic2SDN: actual KiCad connectivity', '* Node mapping: '+json.dumps({n['name']:('0' if n['name']==reference else f'n{i}') for i,n in enumerate(graph['nets'],1)})]
    for c in graph['components']:
        ref=c['ref'];kind=ref[0].upper();value=c['value'].strip()
        if kind not in 'RCLVIDQ':
            raise OperationError(f'{ref} needs an explicit SPICE device model. Import a SPICE netlist with its .model/.subckt definition for simulation.')
        order=['2','1'] if kind=='D' else ['2','1','3'] if kind=='Q' and c.get('library','').endswith('Q_NPN_BCE') else ['1','2']
        if kind=='Q' and not c.get('library','').endswith('Q_NPN_BCE'):raise OperationError(f'Specify the SPICE pin mapping for {ref}; the simulator will not guess a transistor pinout.')
        pins=[node_map.get((ref,p)) for p in order]
        if any(n is None for n in pins):raise OperationError(f'{ref} has unresolved simulation pins.')
        if kind in 'DQ' and not controls.get('models'):
            # Query indexed SPICE model database
            db_path = Path(__file__).resolve().parents[2] / 'libraries' / 'index' / 'components.db'
            found_model = None
            if db_path.exists():
                try:
                    import sqlite3
                    with sqlite3.connect(str(db_path)) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT definition FROM spice_models WHERE name = ? COLLATE NOCASE LIMIT 1", (value,))
                        row = cur.fetchone()
                        if row: found_model = row[0]
                except Exception: pass
            if found_model:
                controls.setdefault('models', []).append(found_model)
            else:
                raise OperationError(f'{ref} ({value}) requires a .model definition imported from a SPICE netlist or library.')
        if re.search(r'[\r\n;]',value):raise OperationError('Invalid SPICE value.')
        lines.append(f'{ref} '+ ' '.join(pins) + ' '+value)
    for model in controls.get('models',[]):
        if not model.lower().startswith('.model ') or '\n' in model:raise OperationError('Invalid SPICE model declaration.')
        lines.append(model)
    lines += ['.tran '+controls.get('step','10u')+' '+controls.get('stop','10m'),'.end']
    return '\n'.join(lines)+'\n'
