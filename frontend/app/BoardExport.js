'use client';
import {useEffect,useState} from 'react';
import WorkbenchDialog from './WorkbenchDialog';
import {boardErrors} from './review-model.mjs';
function FootprintPicker({component,value,requiredPins,request,onChange,onValidated}){
 const [query,setQuery]=useState(value||''),[items,setItems]=useState([]),[detail,setDetail]=useState(null),[error,setError]=useState('');
 useEffect(()=>{
  let active=true;const timer=setTimeout(()=>{
   if(query.trim().length<2){setItems([]);return;}
   request(`/libraries/footprints?q=${encodeURIComponent(query)}`).then(r=>r.json()).then(d=>{if(active)setItems(d.items);}).catch(e=>{if(active)setError(e.message);});
  },250);return ()=>{active=false;clearTimeout(timer);};
 },[query,request]);
 useEffect(()=>{
  let active=true;setDetail(null);setError('');onValidated(false);
  if(value)request(`/libraries/footprint?id=${encodeURIComponent(value)}`).then(r=>r.json()).then(d=>{
   if(!active)return;setDetail(d);const missing=requiredPins.filter(p=>!d.pads.includes(p));
   if(missing.length)setError(`Missing required pads: ${missing.join(', ')}`);
   else onValidated(true);
  }).catch(e=>{if(active)setError(e.message);});
  return ()=>{active=false;};
 },[value,request]);
 return <div className="footprint-picker"><label>Footprint search<input aria-label={`${component.ref} footprint search`} placeholder="Search resistor, SOIC, connector…" value={query} onChange={e=>{setQuery(e.target.value);onChange('');}}/></label>
  {!value&&items.length>0&&<select aria-label={`Choose ${component.ref} footprint`} size={Math.min(5,items.length+1)} value="" onChange={e=>{onChange(e.target.value);setQuery(e.target.value);setItems([]);}}><option value="" disabled>Select a matching physical package</option>{items.map(id=><option value={id} key={id}>{id}</option>)}</select>}
  {detail&&<small>{detail.description}<br/>Pads: {detail.pads.join(', ')} · Required: {requiredPins.join(', ')||'none connected'}</small>}
  {error&&<small role="alert" className="workflow-error">{error}</small>}
 </div>;
}
export default function BoardExport({graph,request,onExport,onClose}){
 const columns=Math.max(2,Math.ceil(Math.sqrt(graph.components.length*1.25)));
 const [plan,setPlan]=useState(()=>({width_mm:Math.max(100,20+columns*20),height_mm:Math.max(80,20+Math.ceil(graph.components.length/columns)*20),track_width_mm:.25,clearance_mm:.2,placements:Object.fromEntries(graph.components.map((c,i)=>[c.ref,{footprint:c.footprint||'',x_mm:10+(i%columns)*20,y_mm:10+Math.floor(i/columns)*20,rotation_deg:0}]))}));
 const [valid,setValid]=useState({}),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reviewed,setReviewed]=useState(false);
 const edit=(key,value)=>{setPlan(p=>({...p,[key]:value}));setReviewed(false);};
 const place=(ref,key,value)=>{setPlan(p=>({...p,placements:{...p.placements,[ref]:{...p.placements[ref],[key]:value}}}));setReviewed(false);};
 const errors=boardErrors(plan,graph.components),ready=graph.components.length>0&&graph.components.every(c=>valid[c.ref]);
 const submit=async e=>{e.preventDefault();if(!ready||errors.length||!reviewed)return;setBusy(true);setError('');try{await onExport(plan);onClose();}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <WorkbenchDialog title="Export PCB and Specctra DSN" busy={busy} onClose={onClose}><form onSubmit={submit}>
  <p>Choose physical footprints, board size and placement. Downloads an editable KiCad PCB and a Specctra DSN for Freerouting.</p>
  {!graph.components.length&&<p role="alert">Add components to the schematic before exporting a board.</p>}
  <div className="board-rules">{[['width_mm','Board width (mm)',10,500,1],['height_mm','Board height (mm)',10,500,1],['track_width_mm','Track width (mm)',.1,2,.05],['clearance_mm','Clearance (mm)',.1,2,.05]].map(([key,label,min,max,step])=><label key={key}>{label}<input required disabled={busy} type="number" min={min} max={max} step={step} value={plan[key]} onChange={e=>edit(key,e.target.value)}/></label>)}</div>
  <svg className="board-preview" viewBox={`-5 -5 ${Math.max(10,Number(plan.width_mm)||100)+10} ${Math.max(10,Number(plan.height_mm)||80)+10}`} role="img" aria-label="Approximate footprint origin placement; not footprint outlines"><rect width={Math.max(0,+plan.width_mm)||100} height={Math.max(0,+plan.height_mm)||80} fill="#123326" stroke="#58a6ff" strokeWidth=".4"/>{graph.components.map(c=>{const p=plan.placements[c.ref];return <g key={c.ref} transform={`translate(${+p.x_mm||0} ${+p.y_mm||0})`}><circle r="1.1" fill="#7ee787"/><text fontSize="3" x="2" y="1" fill="white">{c.ref}</text></g>;})}</svg>
  <small>Preview shows origins only. Inspect footprint outlines, spacing and DRC in the exported PCB before routing.</small>
  <fieldset disabled={busy} className="board-components">{graph.components.map(c=><section className="board-component" key={c.ref}><h3>{c.ref} · {c.value}</h3><FootprintPicker component={c} value={plan.placements[c.ref].footprint} requiredPins={[...new Set(graph.nets.flatMap(n=>n.nodes.filter(p=>p.ref===c.ref).map(p=>p.pin)))]} request={request} onChange={value=>place(c.ref,'footprint',value)} onValidated={ok=>setValid(v=>v[c.ref]===ok?v:{...v,[c.ref]:ok})}/><div className="board-rules">{[['x_mm','X (mm)'],['y_mm','Y (mm)'],['rotation_deg','Rotation (°)']].map(([key,label])=><label key={key}>{label}<input required type="number" step="any" value={plan.placements[c.ref][key]} onChange={e=>place(c.ref,key,e.target.value)}/></label>)}</div></section>)}</fieldset>
  {(error||errors.length>0)&&<p className="workflow-error" role="alert">{error||errors.join(' ')}</p>}
  {!ready&&graph.components.length>0&&<p>Select an installed footprint with all required physical pads for every component.</p>}
  <label className="review-confirm"><input disabled={busy} type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I checked the physical packages, placement and routing dimensions.</label>
  <div className="modal-actions"><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="btn-primary" type="submit" disabled={busy||!reviewed||!ready||errors.length>0}>{busy?'Generating board…':'Download PCB + DSN'}</button></div>
 </form></WorkbenchDialog>;
}
