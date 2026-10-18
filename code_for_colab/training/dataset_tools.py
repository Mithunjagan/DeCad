#!/usr/bin/env python3
"""Normalize actual paired data and prepare reproducible, leak-resistant splits."""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.ingestion import Circuit,parse_json,parse_spice
from app.simulation import number
from app.ground import reference_name

def signature(circuit):
 components={c.ref:c.value for c in circuit.components}
 for ref,value in components.items():
  try:components[ref]=number(value.removeprefix('DC '))
  except Exception:pass
 edges=sorted(sorted(f'{n.ref}:{n.pin}' for n in net.nodes) for net in circuit.nets)
 return {'components':components,'partitions':edges,'ground':sorted(f'{n.ref}:{n.pin}' for net in circuit.nets if net.name==reference_name(n.name for n in circuit.nets) for n in net.nodes)}

def topology_group(circuit):
 # Reference-independent color refinement groups isomorphic pin graphs together.
 colors={};edges={}
 for component in circuit.components:
  key='c:'+component.ref;colors[key]='component:'+(component.library or component.ref[0]);edges[key]=[]
 reference=reference_name(net.name for net in circuit.nets)
 for i,net in enumerate(circuit.nets):
  key='n:'+str(i);colors[key]='ground' if net.name==reference else 'net';edges[key]=[]
  for node in net.nodes:
   other='c:'+node.ref;edges[key].append((other,node.pin));edges[other].append((key,node.pin))
 for _ in range(12):
  colors={key:hashlib.sha256(json.dumps([colors[key],sorted((colors[other],pin) for other,pin in edges[key])]).encode()).hexdigest() for key in colors}
 return hashlib.sha256(json.dumps(sorted(colors.values())).encode()).hexdigest()[:16]

def audit(root):
 samples=[];rejected=[];seen=set()
 for path in sorted(root.rglob('*.json')):
  try:
   data=json.loads(path.read_text());circuit=parse_json(json.dumps({'components':data['components'],'nets':data.get('nets',[])}))
   image=data.get('image_rel_path') or data.get('image_path') or data.get('image') or (str((path.parent/'circuit.png').relative_to(root)) if (path.parent/'circuit.png').exists() else None)
   if not image:raise ValueError('No paired raster image path.')
   candidate=(root/image).resolve()
   if not (candidate.is_relative_to(root.resolve()) and candidate.is_file()):candidate=(path.parent/image).resolve()
   if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():raise ValueError('Image is missing or escapes dataset root.')
   with Image.open(candidate) as raster:
    if raster.width*raster.height>16_000_000:raise ValueError('Image exceeds 16 million pixels.')
    raster.verify()
   digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
   if digest in seen:raise ValueError('Duplicate image.')
   verified=False
   netlist=data.get('spice_netlist') or ((path.parent/'circuit.cir').read_text() if (path.parent/'circuit.cir').is_file() else None)
   if netlist:
    parsed,_=parse_spice(netlist);verified=signature(parsed)==signature(circuit)
    if not verified:raise ValueError('JSON and SPICE disagree on values or pin connectivity.')
   seen.add(digest)
   topology=topology_group(circuit)
   samples.append({'sample_id':data.get('sample_id',path.stem),'source':data.get('source_dataset','user-provided'),'image':str(candidate),'image_sha256':digest,'group':data.get('group',topology),'circuit':circuit.model_dump(),'netlist_equivalence_verified':verified,'image_source_review':'verified' if data.get('image_source_review')=='verified' else 'required'})
  except Exception as e:rejected.append({'file':str(path.relative_to(root)),'reason':str(e)})
 groups=sorted({s['group'] for s in samples})
 return {'samples':samples,'accepted':len(samples),'rejected':rejected,'groups':len(groups),'custom_training_ready':len(samples)>=100 and len(groups)>=3 and all(s['netlist_equivalence_verified'] and s['image_source_review']=='verified' for s in samples),'note':'Counts are read from files. JSON/SPICE agreement does not prove source-image fidelity. Review image annotations before training.'}

def prepare(root,out):
 result=audit(root);out.mkdir(parents=True,exist_ok=True);(out/'images').mkdir(exist_ok=True)
 groups=sorted({s['group'] for s in result['samples']})
 n_val=max(1, len(groups)//10)
 n_test=max(1, len(groups)//10)
 group_split={g:('test' if i>=len(groups)-n_test else 'validation' if i>=len(groups)-n_test-n_val else 'train') for i,g in enumerate(groups)}
 records={s:[] for s in ['train','validation','test']}
 for sample in result['samples']:
  target=out/'images'/(sample['image_sha256']+Path(sample['image']).suffix.lower());shutil.copyfile(sample['image'],target)
  sample={**sample,'image':str(target.relative_to(out))};records[group_split[sample['group']]].append(sample)
 for split,rows in records.items():(out/f'{split}.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
 summary={k:v for k,v in result.items() if k!='samples'};summary['splits']={k:len(v) for k,v in records.items()};summary['custom_training_ready']=summary['custom_training_ready'] and len(records['train'])>=100 and bool(records['validation']) and bool(records['test']);(out/'audit.json').write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['audit','prepare']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 if a.command=='prepare' and not a.output:p.error('--output is required')
 result=prepare(a.input,a.output) if a.command=='prepare' else audit(a.input)
 if 'samples' in result:result={k:v for k,v in result.items() if k!='samples'}
 print(json.dumps(result,indent=2))
