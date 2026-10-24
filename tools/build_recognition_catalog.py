"""Build local reference metadata without rendering, training or uploading assets.

Streams installed KiCad definitions and the existing native OrCAD name/pin cache.
No component instances, source-net names or circuit connectivity are imported.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.sexpr import TOKEN


def library_parts(path):
    """Extract only top-level symbol names, aliases, inheritance and pin facts.

    A token stack avoids building graphic trees for large MCU/FPGA libraries.
    """
    stack=[];current=None;pin=None
    for match in TOKEN.finditer(path.read_text(encoding='utf-8-sig')):
        token=match.group(1)
        if token=='(':
            stack.append([])
            continue
        if token==')':
            node=stack.pop()
            if node and node[0]=='pin' and pin is not None:
                if pin.get('number'):
                    current['pins'][pin['number']].add(pin.get('name',''))
                pin=None
            if len(stack)==1 and node and node[0]=='symbol' and current:
                current['pins']={number:sorted(names) for number,names in current['pins'].items()}
                yield current
                current=None
            continue
        if not stack:
            continue
        node=stack[-1]
        value=json.loads(re.sub(r'[\x00-\x1f]',lambda m:json.dumps(m.group())[1:-1],token)) if token.startswith('"') else token
        # Only a few leading atoms matter; graphics coordinate lists are ignored.
        if len(node)<4:
            node.append(value)
        if len(stack)==1 and len(node)==1 and node[0]!='kicad_symbol_lib':
            raise ValueError('Expected an original KiCad symbol library.')
        if len(stack)==2 and len(node)==2 and node[0]=='symbol':
            current={'name':str(value),'aliases':set(),'parent':None,'pins':defaultdict(set)}
        elif current and len(node)==1 and node[0]=='pin':
            pin={}
        elif current and len(stack)==3 and len(node)==2 and node[0]=='extends':
            current['parent']=str(value)
        elif current and len(stack)==3 and len(node)==3 and node[0]=='property' and node[1] in ('Value','MPN','Manufacturer Part Number'):
            current['aliases'].add(str(value))
        elif pin is not None and len(node)==2 and node[0] in ('number','name'):
            pin[node[0]]=str(value)
    if stack or current is not None or pin is not None:
        raise ValueError('Unbalanced library definition.')


def build(args):
    if args.output.exists():
        raise ValueError('Use a new catalog path; preserve the existing snapshot.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.output.with_suffix(args.output.suffix+'.building')
    if temporary.exists():
        raise ValueError('A prior partial build exists; use a new snapshot path.')
    connection=sqlite3.connect(temporary)
    connection.executescript('CREATE TABLE packages(id INTEGER PRIMARY KEY,source TEXT,name TEXT,pins TEXT,parent TEXT);'
                             'CREATE TABLE names(normalized TEXT,package INTEGER,UNIQUE(normalized,package));'
                             'CREATE INDEX name_lookup ON names(normalized);'
                             'CREATE INDEX source_name ON packages(source,name);'
                             'CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);')
    counts=defaultdict(int);sources=[]
    def insert(source,name,pins,parent=None,aliases=()):
        cursor=connection.execute('INSERT INTO packages(source,name,pins,parent) VALUES(?,?,?,?)',
                                   (source,name,json.dumps(pins),parent))
        for alias in {name,*aliases}:
            if alias:
                connection.execute('INSERT OR IGNORE INTO names VALUES(?,?)',(alias.upper(),cursor.lastrowid))
    for root in args.kicad_root:
        for path in sorted(root.rglob('*.kicad_sym')):
            if not path.resolve().is_relative_to(root.resolve()):
                continue
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            total=0
            namespace=path.parent if path.parent.suffix=='.kicad_symdir' else path
            for part in library_parts(path):
                insert(str(namespace.resolve()),part['name'],part['pins'],part['parent'],part['aliases'])
                total+=1
            connection.commit();counts['kicad_packages']+=total
            sources.append({'path':str(path.resolve()),'sha256':checksum,'packages':total})
            if len(sources)%20==0:
                print(json.dumps({'libraries':len(sources),'kicad_packages':counts['kicad_packages']}),flush=True)
    cached=json.loads(args.orcad_pins.read_text()) if args.orcad_pins and args.orcad_pins.is_file() else {}
    if args.orcad_index:
        for line in args.orcad_index.read_text().splitlines():
            fields=line.split('\t')
            if len(fields)<2:
                continue
            library,name=fields[:2]
            path=Path(library)
            if not path.is_file() or not path.resolve().is_relative_to(args.orcad_root.resolve()):
                continue
            facts=cached.get(library+'|'+name,{})
            insert(str(path.resolve()),name,{number:[function] for number,function in facts.items()})
            counts['orcad_packages']+=1
        connection.commit()
        sources.append({'path':str(args.orcad_index.resolve()),'sha256':hashlib.sha256(args.orcad_index.read_bytes()).hexdigest(),'scope':'Existing native package-name index; cached pin facts only, no generated symbols.'})
    counts['unique_names']=connection.execute('SELECT COUNT(DISTINCT normalized) FROM names').fetchone()[0]
    counts['packages_with_direct_pin_facts']=connection.execute("SELECT COUNT(*) FROM packages WHERE pins!='{}'").fetchone()[0]
    connection.execute("INSERT INTO metadata VALUES('complete','1')");connection.commit()
    connection.close()
    temporary.rename(args.output)
    audit={'reference_metadata_only':True,'training_performed':False,'assets_rendered':False,'assets_uploaded':False,
           'instance_references_or_net_names_imported':False,'counts':dict(counts),'sources':sources,
           'catalog_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
           'inherited_pin_facts_resolved_on_read':True}
    args.output.with_suffix('.audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps({'counts':dict(counts),'catalog_sha256':audit['catalog_sha256']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kicad-root',type=Path,nargs='+',default=[])
    parser.add_argument('--orcad-index',type=Path)
    parser.add_argument('--orcad-pins',type=Path)
    parser.add_argument('--orcad-root',type=Path,default=Path('D:/tools/capture/library'))
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args())
