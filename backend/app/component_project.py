"""Transactional project placement of a validated, fully linked component."""
import copy
import json
import math
from pathlib import Path
from .component_formats import kicad_symbol
from .engine import OperationError, Schematic, atomic_text, project_lock
from .sexpr import children, child, dump, expr, num, parse


def geometry_bounds(tree):
    points=[]
    def visit(node):
        if not isinstance(node,list) or not node:return
        if node[0] in ('at','start','end','center','mid','xy') and len(node)>2:
            try:points.append((float(node[1]),float(node[2])))
            except (ValueError,TypeError):pass
        if node[0]=='circle':
            center=child(node,'center');radius=child(node,'radius')
            if center and radius:
                cx,cy=float(center[1]),float(center[2]);r=abs(float(radius[1]))
                points.extend([(cx-r,cy-r),(cx+r,cy+r)])
        for item in node[1:]:visit(item)
    visit(tree)
    if not points:return (-10,-10,10,10)
    return (min(p[0] for p in points)-5,min(p[1] for p in points)-5,
            max(p[0] for p in points)+5,max(p[1] for p in points)+5)


def automatic_position(sch,definition):
    bounds=geometry_bounds(definition);occupied=[]
    library=child(sch.tree,'lib_symbols')
    for symbol in sch.symbols():
        source=next((s for s in children(library,'symbol') if s[1]==child(symbol,'lib_id')[1]),None)
        box=geometry_bounds(source) if source else (-15,-15,15,15)
        at=child(symbol,'at');angle=math.radians(float(at[3]));cos,sin=math.cos(angle),math.sin(angle)
        mirror=child(symbol,'mirror')
        def transform(cx,cy):
            if mirror and mirror[1]=='x':cy=-cy
            if mirror and mirror[1]=='y':cx=-cx
            return float(at[1])+cx*cos-cy*sin,float(at[2])-cx*sin-cy*cos
        corners=[transform(cx,cy) for cx in (box[0],box[2]) for cy in (box[1],box[3])]
        occupied.append((min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)))
    for kind in ('wire','label','global_label','hierarchical_label','junction','no_connect'):
        for item in children(sch.tree,kind):occupied.append(geometry_bounds(item))
    paper=child(sch.tree,'paper',['paper','A4']);sizes={'A4':(297,210),'A3':(420,297),'A2':(594,420),'A1':(841,594),'A0':(1189,841),'A':(279.4,215.9),'Letter':(279.4,215.9),'Legal':(355.6,215.9)}
    width,height=sizes.get(str(paper[1]),(297,210))
    if str(paper[1])=='User' and len(paper)>3:width,height=float(paper[2]),float(paper[3])
    if 'portrait' in paper:width,height=height,width
    # Aligned to KiCad's 50 mil grid. Guard symbol bodies/pins and existing wires;
    # detailed text layout remains editable in the native editor.
    xs=[round(i*2.54,6) for i in range(20,int(width/2.54))]+[round(i*2.54,6) for i in range(4,20)]
    ys=[round(i*2.54,6) for i in range(20,int(height/2.54))]+[round(i*2.54,6) for i in range(4,20)]
    for y in ys:
        for x in xs:
            box=(x+bounds[0],y-bounds[3],x+bounds[2],y-bounds[1])
            if box[0]<10 or box[1]<10 or box[2]>width-10 or box[3]>height-20:continue
            if not any(box[0]<b[2] and box[2]>b[0] and box[1]<b[3] and box[3]>b[1] for b in occupied):return x,y
    raise OperationError('No automatic placement space remains on this sheet. Choose an explicit position or move components in KiCad.')


def place(project, record, reference, x=None, y=None, prepare=None):
    if not record.get('cached') or record['validation'].get('pin_to_pad')!='verified':
        raise OperationError('A current verified symbol/footprint pair is required.')
    if any(pin.get('unit',1)>1 for pin in record['pins']):
        raise OperationError('Multi-unit symbol libraries export, but placing all units is not implemented yet.')
    if not record.get('kicad_footprint'):
        raise OperationError('The linked footprint has no supported geometry for project placement.')
    project=Path(project)
    with project_lock(project):
        if prepare:prepare(project)
        sch=Schematic(project)
        if sch.get(reference):raise OperationError(f'{reference} already exists. Choose a new reference.')
        definition=children(kicad_symbol(record,record['id']),'symbol')[0]
        if (x is None)!=(y is None):raise OperationError('Specify both placement coordinates, or leave both automatic.')
        if x is None:x,y=automatic_position(sch,definition)
        lib_id='DeCad:'+record['id'];definition[1]=lib_id
        fp_key=record['validation']['sources'][1]
        fp_tree=parse(record['kicad_footprint']);fp_tree[1]=fp_key
        table_path=project/'fp-lib-table'
        table=parse(table_path.read_text()) if table_path.exists() else expr('fp_lib_table')
        if table[0]!='fp_lib_table':raise OperationError('Project footprint library table is invalid.')
        existing=next((item for item in children(table,'lib') if child(item,'name',['',''])[1]=='DeCadUnified'),None)
        uri='${KIPRJMOD}/DeCadUnified.pretty'
        if existing is not None and child(existing,'uri',['',''])[1]!=uri:
            raise OperationError('Project already uses a different DeCadUnified footprint library.')
        if existing is None:
            table.append(expr('lib',expr('name','DeCadUnified'),expr('type','KiCad'),expr('uri',uri),
                              expr('options',''),expr('descr','Verified DeCad component assets')))
        footprint_path=project/'DeCadUnified.pretty'/(fp_key+'.kicad_mod')
        provenance=project/'component-assets.json'
        assets=json.loads(provenance.read_text()) if provenance.exists() else {}
        assets[reference]=record
        content={table_path:dump(table),footprint_path:dump(fp_tree),provenance:json.dumps(assets,indent=1)}
        for source in [record,*record.get('linked_sources',[])]:
            policy=source['source_license']
            if policy.get('license_text'):
                content[project/'component-licenses'/(source['id']+'.md')]=policy['license_text']
        snapshot={path:path.read_bytes() if path.exists() else None for path in content}
        before=sch.path.read_text()
        try:
            for path,text in content.items():
                path.parent.mkdir(parents=True,exist_ok=True);atomic_text(path,text)
            result=sch.add(reference,record['manufacturer_part_number'] or record['name'],lib_id,
                           'DeCadUnified:'+fp_key,x,y,definition=definition)
            # Keep the library author's field placement. Generic resistor offsets
            # put IC reference/value text inside its body and over the pin labels.
            placed=sch.get(reference)
            for prop in children(placed,'property'):
                if prop[1] not in ('Reference','Value'):continue
                template=next((p for p in children(definition,'property') if p[1]==prop[1]),None)
                local=child(template,'at') if template else None
                if local and len(local)>=3:
                    at=child(prop,'at');at[1:]=[num(float(x)+float(local[1])),num(float(y)-float(local[2])),num(float(local[3]) if len(local)>3 else 0)]
                    effects=child(template,'effects')
                    if effects is not None:
                        old=child(prop,'effects')
                        if old is not None:prop.remove(old)
                        prop.append(copy.deepcopy(effects))
            sch.save();graph=sch.graph()
            from .assistant import remember
            remember(project,before,'Add acquired component '+reference)
        except Exception:
            atomic_text(sch.path,before)
            for path,old in snapshot.items():
                if old is None:path.unlink(missing_ok=True)
                else:path.write_bytes(old)
            raise
    return dict(edit=result,validation=record['validation'],circuit=graph,
                footprint='DeCadUnified:'+fp_key,source_component=record['id'],position={'x':x,'y':y})
