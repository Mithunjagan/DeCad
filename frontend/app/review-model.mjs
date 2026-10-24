export function renameComponent(circuit, index, ref) {
  const old = circuit.components[index].ref;
  return {...circuit, components:circuit.components.map((c,i)=>i===index?{...c,ref}:c),
    ...(circuit.physical_pins?{physical_pins:circuit.physical_pins.map(p=>p.ref===old?{...p,ref,confidence:null,source:null,metadata:{...p.metadata,td9_attributes:p.metadata?.td9_attributes?{...p.metadata.td9_attributes,DeviceLocation:ref,NodeName:`${ref}_${p.pin}`,NodeDisName:`${ref}_${p.pin}`}:undefined}}:p)}:{}),
    ...(circuit.review_hotspots?{review_hotspots:circuit.review_hotspots.map(h=>h.ref===old?{...h,ref,stale:true,reviewed:false}:h)}:{}),
    nets:circuit.nets.map(n=>n.nodes.some(p=>p.ref===old)?{...n,metadata:{...n.metadata,evidence_stale:true},confidence:null,source:null,nodes:n.nodes.map(p=>p.ref===old?{...p,ref,confidence:null,source:null}:p)}:n)};
}
export function removeComponent(circuit,index) {
  const ref=circuit.components[index].ref;
  return {...circuit,components:circuit.components.filter((_,i)=>i!==index),
    ...(circuit.physical_pins?{physical_pins:circuit.physical_pins.filter(p=>p.ref!==ref)}:{}),
    ...(circuit.review_hotspots?{review_hotspots:circuit.review_hotspots.filter(h=>h.ref!==ref)}:{}),
    nets:circuit.nets.map(n=>n.nodes.some(p=>p.ref===ref)?{...n,metadata:{...n.metadata,evidence_stale:true},confidence:null,source:null,nodes:n.nodes.filter(p=>p.ref!==ref)}:n).filter(n=>n.nodes.length)};
}
export function editNetEvidence(circuit,index,value){
  const old=circuit.nets[index],pins=new Set(old.nodes.map(p=>JSON.stringify([p.ref,p.pin])));
  return {...circuit,nets:circuit.nets.map((n,i)=>i===index?{...value,metadata:{...value.metadata,evidence_stale:true},confidence:null,source:null,nodes:value.nodes.map(p=>({...p,confidence:null,source:null}))}:n),
    ...(circuit.review_hotspots?{review_hotspots:circuit.review_hotspots.map(h=>h.net===old.name||pins.has(JSON.stringify([h.ref,h.pin]))?{...h,stale:true,reviewed:false}:h)}:{})};
}
export function confirmHotspot(circuit,id){
  return {...circuit,review_hotspots:(circuit.review_hotspots||[]).map(h=>h.id===id?{...h,reviewed:!h.reviewed}:h)};
}
export function mergeNets(circuit,index,target){
 if(index===target)return circuit;
 const next=editNetEvidence(circuit,target,{...circuit.nets[target],nodes:[...circuit.nets[target].nodes,...circuit.nets[index].nodes]});
 return {...next,nets:next.nets.filter((_,i)=>i!==index),warnings:[...(next.warnings||[]),`Manual merge: ${circuit.nets[index].name} into ${circuit.nets[target].name}. Check the source junction or scoped label before export.`],review_hotspots:(next.review_hotspots||[]).map(h=>h.net===circuit.nets[index].name?{...h,stale:true,reviewed:false}:h)};
}
export function electricalWarnings(circuit){
 const types=new Map((circuit.physical_pins||[]).map(p=>[JSON.stringify([p.ref,p.pin]),p.electrical_type]));
 const components=new Map(circuit.components.map(c=>[c.ref,c]));
 const constraints=circuit.nets.flatMap(n=>n.nodes.flatMap(p=>{
  const c=components.get(p.ref);
  return ['Device:R','Device:C','Device:L','Device:D'].includes(c?.library)&&!['1','2'].includes(p.pin)?[`${p.ref}.${p.pin}: physical pin is absent from ${c.library}. Review the source number or symbol assignment; connection retained.`]:[];
 }));
 const unlocated=circuit.components.filter(c=>c.value==='CONNECTOR'&&c.x==null&&c.y==null).map(c=>`${c.ref}: connector has no located source body. Verify this is a physical reference rather than an internal pin-function label.`);
 return [...new Set([...constraints,...unlocated,...circuit.nets.flatMap(n=>{
  const outputs=n.nodes.filter(p=>['Output','PowerOut','power_out','output'].includes(types.get(JSON.stringify([p.ref,p.pin]))));
  return outputs.length>1?[`${n.name}: ${outputs.length} explicit output drivers share a net. Review required; connections retained.`]:[];
 })])];
}
export function splitPin(circuit,index,pinIndex){
 const old=circuit.nets[index];if(old.nodes.length<2)return circuit;
 let suffix=1,name;do{name=`SPLIT_${suffix++}`;}while(circuit.nets.some(n=>n.name===name));
 const pin=old.nodes[pinIndex],next=editNetEvidence(circuit,index,{...old,nodes:old.nodes.filter((_,j)=>j!==pinIndex)});
 return {...next,nets:[...next.nets,{name,metadata:{evidence_stale:true},nodes:[{...pin,confidence:null,source:null}],confidence:null,source:null}]};
}
export function evidenceText(item){
  if(item?.confidence==null)return 'Unscored';
  const labels={vector:'Native PDF',wire_trace:'Traced wire',net_label:'Printed label',erc_healed:'Recovered connection',vlm_tiebreak:'Crop interpretation',implicit_passive_terminal:'Inferred passive terminal',provisional_stub:'Provisional stub - confirm number and net'};
  return `${labels[item.source]||'Evidence'} · ${item.confidence.toFixed(2)}`;
}
export function circuitErrors(circuit) {
  const errors=[],refs=new Set(),names=new Set(),pins=new Set();
  const evidence=item=>{if(item.confidence!=null&&(!Number.isFinite(item.confidence)||item.confidence<0||item.confidence>1))errors.push('Evidence scores must be between 0 and 1.');if(item.source!=null&&!['vector','wire_trace','net_label','erc_healed','vlm_tiebreak','implicit_passive_terminal','provisional_stub'].includes(item.source))errors.push('Unknown evidence source.');};
  if(!Array.isArray(circuit?.components)||!Array.isArray(circuit?.nets))return ['Components and nets must be lists.'];
  if(!circuit.components.length)errors.push('Add at least one component.');
  if(circuit.warnings!==undefined&&(!Array.isArray(circuit.warnings)||circuit.warnings.some(w=>typeof w!=='string')))errors.push('Warnings must be a list of text.');
  for(const c of circuit.components){
    if(!c||typeof c!=='object'){errors.push('Each component must be an object.');continue;}
    if(!/^[A-Z][A-Z0-9_]*\d+$/.test(c.ref))errors.push(`Invalid reference: ${c.ref || '(empty)'}.`);
    if(refs.has(c.ref))errors.push(`Duplicate reference: ${c.ref}.`);refs.add(c.ref);
    if(typeof c.value!=='string'||!c.value.trim()||c.value.length>200)errors.push(`${c.ref}: enter a value of 1–200 characters.`);
    for(const key of ['library','footprint'])if(c[key]!=null&&typeof c[key]!=='string')errors.push(`${c.ref}: ${key} must be text.`);
    for(const key of ['x','y'])if(c[key]!=null&&(!Number.isFinite(c[key])||c[key]<0||c[key]>10))errors.push(`${c.ref}: ${key} must be a source position between 0 and 10.`);
  }
  for(const n of circuit.nets){
    if(!n||typeof n!=='object'){errors.push('Each net must be an object.');continue;}
    evidence(n);
    if(typeof n.name!=='string'||!n.name.trim()||n.name.length>100||/[\r\n"\\]/.test(n.name))errors.push('Enter a valid net name of 1–100 characters.');
    if(names.has(n.name))errors.push(`Duplicate net: ${n.name}.`);names.add(n.name);
    if(!Array.isArray(n.nodes)||!n.nodes.length){errors.push(`${n.name}: add at least one pin.`);continue;}
    for(const p of n.nodes){
      if(!p||typeof p!=='object'){errors.push(`${n.name}: each pin connection must be an object.`);continue;}
      evidence(p);
      if(!refs.has(p.ref))errors.push(`${n.name}: unknown component ${p.ref}.`);
      if(typeof p.pin!=='string'||!p.pin.trim())errors.push(`${n.name}: enter a physical pin number as text.`);
      const key=JSON.stringify([p.ref,p.pin]);if(pins.has(key))errors.push(`${p.ref} pin ${p.pin} is assigned more than once.`);pins.add(key);
    }
  }
  if(circuit.review_hotspots!==undefined){
    if(!Array.isArray(circuit.review_hotspots))errors.push('Source review regions must be a list.');
    else for(const h of circuit.review_hotspots){
      if(!h||typeof h!=='object'){errors.push('Invalid source review region.');continue;}
      evidence(h);
      if(!Array.isArray(h.bbox)||h.bbox.length!==4||!h.bbox.every(Number.isFinite)||!Number.isFinite(h.source_width)||!Number.isFinite(h.source_height)||h.source_width<=0||h.source_height<=0||h.bbox[0]<0||h.bbox[1]<0||h.bbox[2]<=h.bbox[0]||h.bbox[3]<=h.bbox[1]||h.bbox[2]>h.source_width||h.bbox[3]>h.source_height)errors.push('Source review regions must lie inside their image.');
    }
  }
  return [...new Set(errors)];
}
export function boardErrors(plan,components){
 const errors=[];
 for(const k of ['width_mm','height_mm'])if(!Number.isFinite(+plan[k])||+plan[k]<10||+plan[k]>500)errors.push('Board dimensions must be 10–500 mm.');
 for(const k of ['track_width_mm','clearance_mm'])if(!Number.isFinite(+plan[k])||+plan[k]<.1||+plan[k]>2)errors.push('Track width and clearance must be 0.1–2 mm.');
 for(const c of components){const p=plan.placements[c.ref];
  if(!p?.footprint||!/^([^:\/\\]+):([^:\/\\]+)$/.test(p.footprint))errors.push(`${c.ref}: select an installed footprint.`);
  if(!p||![p.x_mm,p.y_mm,p.rotation_deg].every(x=>x!==''&&Number.isFinite(+x)))errors.push(`${c.ref}: enter numeric position and rotation.`);
  else if(+p.x_mm<2||+p.y_mm<2||+p.x_mm>+plan.width_mm-2||+p.y_mm>+plan.height_mm-2)errors.push(`${c.ref}: position must stay inside the 2 mm board margin.`);
 }
 return [...new Set(errors)];
}
