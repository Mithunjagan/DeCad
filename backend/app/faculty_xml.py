"""TD9-style XML interchange. No vendor acceptance or recognition accuracy implied.

Unknown electrical types map to NodeType='Unknown', unknown power/used flags to
FALSE, with unknowns retained in the canonical inventory. No power is inferred
from names. Imported attributes (including absent versus empty) are preserved.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import xml.etree.ElementTree as ET
from pydantic import BaseModel, Field

from .engine import OperationError


class Element(BaseModel):
    tag: str
    attributes: dict[str,str] = Field(default_factory=dict)
    text: str | None = None
    children: list['Element'] = Field(default_factory=list)

    @classmethod
    def read(cls, element):
        return cls(tag=element.tag,attributes=dict(element.attrib),
                   text=element.text if element.text and element.text.strip() else None,
                   children=[cls.read(c) for c in element])

    def write(self):
        element=ET.Element(self.tag,self.attributes);element.text=self.text
        element.extend(c.write() for c in self.children)
        return element


class NodeRecord(BaseModel):
    attributes: dict[str,str]

    @property
    def identity(self):return self.attributes.get('DeviceLocation'),self.attributes.get('PinNumber')


class NetRecord(BaseModel):
    section: str
    attributes: dict[str,str]


class Document(BaseModel):
    root: Element

    @property
    def nodes(self):return [NodeRecord(attributes=e.attrib) for e in self.root.write().findall('./NetList/Nodes/Node')]

    @property
    def nets(self):return [NetRecord(section=s,attributes=e.attrib) for s in ('PowerNets','UserNets')
                          for e in self.root.write().findall(f'./NetList/{s}/Net')]


def parse(data: bytes | str) -> Document:
    if len(data)>25*1024*1024:raise OperationError('Faculty XML exceeds 25 MB.')
    # Reject DTDs/entities even for UTF-16 input before handing it to ElementTree.
    raw=data if isinstance(data,str) else data.decode('utf-8',errors='ignore').replace('\x00','')
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
        raise OperationError('DTD/entity declarations are not supported in faculty XML.')
    try:root=ET.fromstring(data)
    except (ET.ParseError,ValueError) as exc:raise OperationError(f'Invalid faculty XML: {exc}') from exc
    stack=[(root,0)];count=0
    while stack:
        element,depth=stack.pop();count+=1
        if depth>64 or count>200000:raise OperationError('Faculty XML nesting or record limit exceeded.')
        stack.extend((child,depth+1) for child in element)
    document=Document(root=Element.read(root))
    errors=validate(document)
    if errors:raise OperationError('Invalid faculty XML: '+'; '.join(errors))
    return document


def validate(document: Document) -> list[str]:
    root=document.root.write();errors=[]
    if root.tag!='FileDescription':errors.append('Root must be FileDescription')
    for path in ('Application','Board','Version','Date','NetList','NetList/Nodes','NetList/PowerNets','NetList/UserNets'):
        if len(root.findall(path))!=1:errors.append(f'Exactly one {path} required')
    names=[n.attributes.get('NetName') for n in document.nets]
    if any(not name for name in names):errors.append('NetName required')
    if len(names)!=len(set(names)):errors.append('Duplicate net definitions')
    identities=[];node_names=[]
    if not document.nodes:errors.append('At least one physical pin record required')
    for node in document.nodes:
        a=node.attributes;identities.append(node.identity);node_names.append(a.get('NodeName'))
        if not all(node.identity) or not a.get('NodeName'):errors.append('Node identity required')
        for field in ('IsPinUsed','IsReadOnly','IsPowerPin'):
            if field in a and a[field] not in ('TRUE','FALSE'):errors.append(f'Invalid {field} on {a.get("NodeName")}')
        if a.get('NodeNetName') and a['NodeNetName'] not in names:errors.append(f'Undeclared net {a["NodeNetName"]}')
    if len(identities)!=len(set(identities)):errors.append('Duplicate physical pin')
    if len(node_names)!=len(set(node_names)):errors.append('Duplicate NodeName')
    return sorted(set(errors))


def serialize(document: Document) -> bytes:
    errors=validate(document)
    if errors:raise OperationError('; '.join(errors))
    root=document.root.write();ET.indent(root,space='  ')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def to_circuit(document: Document):
    from .ingestion import Circuit
    components={};pins=[];nets={}
    definitions={n.attributes['NetName']:n for n in document.nets}
    for node in document.nodes:
        a=node.attributes;ref,pin=node.identity
        components.setdefault(ref,{'ref':ref,'value':a.get('Marking') or 'Unknown'})
        pins.append({'ref':ref,'pin':pin,'used':{'TRUE':True,'FALSE':False}.get(a.get('IsPinUsed')),
                     'pin_function':a.get('LabelName'),'electrical_type':a.get('NodeType') or 'unknown',
                     'power':{'TRUE':True,'FALSE':False}.get(a.get('IsPowerPin')),
                     'metadata':{'td9_attributes':a}})
        name=a.get('NodeNetName')
        if name:nets.setdefault(name,[]).append({'ref':ref,'pin':pin})
    return Circuit(components=list(components.values()),physical_pins=pins,
                   nets=[{'name':name,'nodes':nodes,'metadata':{'td9_attributes':definitions[name].attributes,
                         'td9_section':definitions[name].section}} for name,nodes in nets.items()],
                   faculty_xml={'document':document.model_dump()},
                   warnings=['TD9-style interchange imported; vendor application acceptance NOT VERIFIED.'])


def from_circuit(circuit, board='Schematic2SDN') -> Document:
    """Serialize current graph memberships, never a cached answer document."""
    from .ingestion import Circuit
    from .catalog_pin_solver import normalize_graph
    circuit=Circuit.model_validate(normalize_graph(circuit))
    if circuit.faculty_xml.get('document'):
        root=Document.model_validate(circuit.faculty_xml['document']).root.write()
    else:
        root=ET.Element('FileDescription')
        for tag,attrs in [('Application',{'ApplicationName':'TD9 TestSequencer'}),('Board',{'BoardName':board}),
                          ('Version',{'Version':'FVER00001'}),('Date',{'FileModified':''})]:ET.SubElement(root,tag,attrs)
        netlist=ET.SubElement(root,'NetList')
        for tag in ('Nodes','PowerNets','UserNets'):ET.SubElement(netlist,tag)
    nodes=root.find('./NetList/Nodes');power=root.find('./NetList/PowerNets');user=root.find('./NetList/UserNets')
    originals={(e.get('DeviceLocation'),e.get('PinNumber')):e for e in nodes.findall('Node')}
    original_values={}
    for e in nodes.findall('Node'):original_values.setdefault(e.get('DeviceLocation'),e.get('Marking') or 'Unknown')
    old_members=Counter(e.get('NodeNetName') for e in nodes.findall('Node') if e.get('NodeNetName'))
    # Retain unknown children and section attributes, replacing records only.
    for e in list(nodes):
        if e.tag=='Node':nodes.remove(e)
    refs={c.ref:c for c in circuit.components}
    inventory={(p.ref,p.pin):p for p in circuit.physical_pins}
    assignments={(p.ref,p.pin):n.name for n in circuit.nets for p in n.nodes}
    order=list(inventory)+[key for key in assignments if key not in inventory]
    for key in order:
        ref,pin=key;p=inventory.get(key);old=originals.get(key)
        if old is not None:
            element=deepcopy(old);a=element.attrib
        else:
            a=deepcopy(p.metadata.get('td9_attributes',{})) if p else {}
            if not a:
                a={'NodeName':f'{ref}_{pin}','NodeDisName':f'{ref}_{pin}','PinNumber':pin,'DeviceLocation':ref,
                   'IsPinUsed':'TRUE' if key in assignments or (p and p.used is True) else 'FALSE',
                   'Marking':refs[ref].value,'NodeNetName':'','LabelName':p.pin_function or '' if p else '',
                   'AliaseNetName':'','IsReadOnly':'FALSE','PowerLevel':'',
                   'NodeType':p.electrical_type if p and p.electrical_type!='unknown' else 'Unknown',
                   'IsPowerPin':'TRUE' if p and p.power is True else 'FALSE'}
            element=ET.Element('Node',a);a=element.attrib
        if key in assignments or 'NodeNetName' in a:a['NodeNetName']=assignments.get(key,'')
        if ref not in original_values or refs[ref].value!=original_values[ref]:a['Marking']=refs[ref].value
        if p and old is not None:
            if p.pin_function!=old.get('LabelName'):
                if p.pin_function is None:a.pop('LabelName',None)
                else:a['LabelName']=p.pin_function
            if p.electrical_type!=(old.get('NodeType') or 'unknown'):
                a['NodeType']='Unknown' if p.electrical_type=='unknown' else p.electrical_type
            if p.power!={'TRUE':True,'FALSE':False}.get(old.get('IsPowerPin')):
                if p.power is None:a.pop('IsPowerPin',None)
                else:a['IsPowerPin']='TRUE' if p.power else 'FALSE'
        if key in assignments and (old is None or old.get('NodeNetName')!=assignments[key]):a['IsPinUsed']='TRUE'
        if p and p.used is not None and key not in assignments:a['IsPinUsed']='TRUE' if p.used else 'FALSE'
        nodes.append(element)
    definitions={e.get('NetName'):(section,deepcopy(e)) for section in (power,user) for e in section.findall('Net')}
    for section in (power,user):
        for e in list(section):
            if e.tag=='Net':section.remove(e)
    current={n.name:n for n in circuit.nets}
    # Original order plus new names; preserve originally empty declarations.
    for name in list(definitions)+[name for name in current if name not in definitions]:
        net=current.get(name)
        if net is None:
            if old_members[name]:continue
            section,element=definitions[name]
        elif name in definitions:section,element=definitions[name]
        else:
            attrs=deepcopy(net.metadata.get('td9_attributes',{}))
            if not attrs:attrs={'NodeTypeLevel':'Unknown','PowerLevel':'','IsReadOnly':'FALSE','IsPowerNet':'0'}
            attrs['NetName']=name;element=ET.Element('Net',attrs)
            section=power if net.metadata.get('td9_section')=='PowerNets' else user
        section.append(element)
    return Document(root=Element.read(root))


def graph_fidelity(circuit,document):
    """Compare graph facts against parsed XML, including extras and unresolved pins."""
    from .ingestion import Circuit
    circuit=Circuit.model_validate(circuit) if isinstance(circuit,dict) else circuit
    expected={(p.ref,p.pin):n.name for n in circuit.nets for p in n.nodes}
    inventory={(p.ref,p.pin) for p in circuit.physical_pins}|set(expected)
    actual={n.identity:n.attributes.get('NodeNetName','') for n in document.nodes}
    actual_assigned={key:name for key,name in actual.items() if name}
    refs={c.ref for c in circuit.components};output_refs={key[0] for key in actual}
    wrong=[str(key) for key in expected.keys()&actual_assigned.keys() if expected[key]!=actual_assigned[key]]
    missing=sorted(map(str,inventory-actual.keys()));extra=sorted(map(str,actual.keys()-inventory))
    missing_assignments=sorted(map(str,expected.keys()-actual_assigned.keys()))
    extra_assignments=sorted(map(str,actual_assigned.keys()-expected.keys()))
    return {'passed':not any((wrong,missing,extra,missing_assignments,extra_assignments,refs-output_refs,output_refs-refs)),
            'physical_pins':len(inventory),'assigned_pins':len(expected),'wrong_assignments':wrong,
            'missing_pins':missing,'extra_pins':extra,'missing_assignments':missing_assignments,
            'extra_assignments':extra_assignments,'missing_components':sorted(refs-output_refs),'extra_components':sorted(output_refs-refs)}


def semantic_diff(before: Document, after: Document) -> dict:
    """All attributes and unknown XML content; order of keyed records is immaterial."""
    def canonical(element):
        return (element.tag,tuple(sorted(element.attributes.items())),element.text,
                tuple(sorted((canonical(c) for c in element.children),key=repr)))
    def records(doc,kind):
        if kind=='nodes':return {n.identity:n.attributes for n in doc.nodes}
        return {(n.section,n.attributes.get('NetName')):n.attributes for n in doc.nets}
    report={'equal':canonical(before.root)==canonical(after.root),'nodes_before':len(before.nodes),
            'nodes_after':len(after.nodes),'nets_before':len(before.nets),'nets_after':len(after.nets)}
    for kind in ('nodes','nets'):
        a,b=records(before,kind),records(after,kind)
        report[kind+'_missing']=[str(k) for k in a.keys()-b.keys()]
        report[kind+'_extra']=[str(k) for k in b.keys()-a.keys()]
        report[kind+'_changed']=[str(k) for k in a.keys()&b.keys() if a[k]!=b[k]]
    return report
