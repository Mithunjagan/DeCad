'use client';
import {useEffect,useId,useMemo,useRef,useState} from 'react';
import WorkbenchDialog from './WorkbenchDialog';
import {renameComponent,removeComponent,circuitErrors,editNetEvidence,confirmHotspot,evidenceText} from './review-model.mjs';
import styles from './CircuitReview.module.css';

export default function CircuitReviewPanel({initial,source,request,onApply,onOrcad,onClose,busy}){
 const [circuit,setCircuit]=useState(()=>structuredClone({...initial,nets:initial.nets||[]}));
 const [error,setError]=useState(''),[reviewed,setReviewed]=useState(false),[preview,setPreview]=useState(null),[sourceError,setSourceError]=useState('');
 const [tab,setTab]=useState('components'),[query,setQuery]=useState(''),[activeNet,setActiveNet]=useState(0);
 const [showSource,setShowSource]=useState(false),[zoom,setZoom]=useState(1),[target,setTarget]=useState('kicad');
 const [raw,setRaw]=useState(''),[rawDirty,setRawDirty]=useState(false),[previous,setPrevious]=useState(null);
 const [sourcePage,setSourcePage]=useState(1),[rasterPreview,setRasterPreview]=useState(null),[hotspotLimit,setHotspotLimit]=useState(50);
 const hotspots=circuit.review_hotspots||[],sourceFrames=circuit.image_metadata?.source_frames||[];
 const sourcePages=[...new Set([...sourceFrames.map(f=>f.page),...hotspots.map(h=>h.page||1)])].sort((a,b)=>a-b);
 if(!sourcePages.length)sourcePages.push(1);
 const panel=useRef(null),id=useId();
 useEffect(()=>{
  setPreview(null);setSourceError('');
  if(!source)return;let active=true,url;
  request(source.path).then(r=>r.blob()).then(blob=>{
   const ext=source.name.split('.').at(-1).toLowerCase(),type={pdf:'application/pdf',tif:'image/tiff',tiff:'image/tiff',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',bmp:'image/bmp',svg:'image/svg+xml'}[ext];
   if(!active)return;url=URL.createObjectURL(type?new Blob([blob],{type}):blob);setPreview({url,type});
  }).catch(e=>{if(active)setSourceError(e.message);});
  return ()=>{active=false;if(url)URL.revokeObjectURL(url);};
 },[source,request]);
 useEffect(()=>{if(!sourcePages.includes(sourcePage))setSourcePage(sourcePages[0]);},[sourcePage,sourcePages.join(',')]);
 useEffect(()=>{
  setRasterPreview(null);if(!source||!['application/pdf','image/tiff'].includes(preview?.type))return;
  let active=true,url;setSourceError('');
  request(`${source.path}${source.path.includes('?')?'&':'?'}preview=true&page=${sourcePage}`).then(r=>r.blob()).then(blob=>{
   if(!active)return;url=URL.createObjectURL(blob);setRasterPreview(url);
  }).catch(e=>{if(active)setSourceError(e.message);});
  return()=>{active=false;if(url)URL.revokeObjectURL(url);};
 },[source,request,preview?.type,sourcePage]);
 const update=next=>{setPrevious(circuit);setCircuit(next);setReviewed(false);setError('');};
 const errors=useMemo(()=>circuitErrors(circuit),[circuit]),warnings=circuit.warnings||[];
 const components=useMemo(()=>circuit.components.map((c,i)=>({c,i})).filter(({c})=>[c.ref,c.value,c.library].some(s=>String(s||'').toLowerCase().includes(query.toLowerCase()))),[circuit.components,query]);
 const nets=useMemo(()=>circuit.nets.map((n,i)=>({n,i})).filter(({n})=>[n.name,...n.nodes.map(p=>`${p.ref}:${p.pin}`)].some(s=>String(s).toLowerCase().includes(query.toLowerCase()))),[circuit.nets,query]);
 const selected=nets.find(({i})=>i===activeNet)||nets[0];
 const editComponent=(i,key,value)=>{const ref=circuit.components[i].ref;update({...circuit,components:circuit.components.map((c,j)=>j===i?{...c,[key]:value}:c),
  nets:circuit.nets.map(n=>n.nodes.some(p=>p.ref===ref)?{...n,confidence:null,source:null,nodes:n.nodes.map(p=>p.ref===ref?{...p,confidence:null,source:null}:p)}:n),
  review_hotspots:hotspots.map(h=>h.ref===ref?{...h,stale:true,reviewed:false}:h)});};
 const editNet=(i,value)=>update(editNetEvidence(circuit,i,value));
 const removeNet=i=>{const next=editNetEvidence(circuit,i,{...circuit.nets[i],nodes:[]});update({...next,nets:next.nets.filter((_,j)=>j!==i)});setActiveNet(Math.max(0,i-1));};
 const selectTab=next=>{setTab(next);setQuery('');if(next==='json'&&!rawDirty)setRaw(JSON.stringify(circuit,null,2));if(panel.current)panel.current.scrollTop=0;};
 const addComponent=()=>{selectTab('components');update({...circuit,components:[...circuit.components,{ref:'',value:'',library:''}]});};
 const addNet=()=>{let index=circuit.nets.length+1;while(circuit.nets.some(n=>n.name===`NET_${index}`))index++;selectTab('connections');setActiveNet(circuit.nets.length);update({...circuit,nets:[...circuit.nets,{name:`NET_${index}`,nodes:[]}]});};
 const applyRaw=()=>{try{const value=JSON.parse(raw),problems=circuitErrors(value);if(problems.length)throw Error(problems.join(' '));update({...value,nets:value.nets.map(n=>({...n,confidence:null,source:null,nodes:n.nodes.map(p=>({...p,confidence:null,source:null}))})),review_hotspots:(value.review_hotspots||[]).map(h=>({...h,stale:true,reviewed:false}))});setRawDirty(false);setTab('components');setQuery('');}catch(e){setError(e.message);}};
 const submit=async()=>{if(busy||!reviewed||errors.length||rawDirty)return;try{setError('');await (target==='orcad'?onOrcad:onApply)(circuit);}catch(e){setError(e.message);}};
 const ready=reviewed&&!errors.length&&!rawDirty;
 const tabs=[['components','Components',circuit.components.length],['connections','Connections',circuit.nets.length],['checks','Review notes',errors.length+warnings.length],['json','JSON',null]];
 const sourceUrl=['application/pdf','image/tiff'].includes(preview?.type)?rasterPreview:preview?.type?.startsWith('image/')?preview.url:null;
 const pageHotspots=hotspots.filter(h=>(h.page||1)===sourcePage&&!h.stale);
 const toggleHotspot=id=>update(confirmHotspot(circuit,id));
 return <WorkbenchDialog title="Review circuit" onClose={onClose} busy={busy} className={styles.dialog}>
  <div className={styles.intro}>
   <p>Compare the recognized parts and physical pins with your source. Your project changes only when you apply this review.</p>
   <div className={styles.summary}><span>{circuit.components.length} components</span><span>{circuit.nets.length} nets</span><span className={errors.length?styles.attention:styles.valid}>{errors.length?`${errors.length} issues to fix`:'Structure checked'}</span>
    {!!hotspots.length&&<span className={styles.attention}>{hotspots.filter(h=>!h.reviewed&&!h.stale).length} source regions to review</span>}
    {source&&<button disabled={busy} aria-pressed={showSource} onClick={()=>setShowSource(v=>!v)}>{showSource?'Hide source':'Compare source'}</button>}
    <button disabled={busy||!previous||rawDirty} onClick={()=>{setCircuit(previous);setPrevious(null);setReviewed(false);setError('');}}>Undo edit</button>
   </div>
  </div>
  <div className={styles.tabs} role="tablist" aria-label="Circuit review sections">
   {tabs.map(([key,label,count])=><button key={key} role="tab" id={`${id}-${key}`} aria-controls={`${id}-panel`} aria-selected={tab===key} tabIndex={tab===key?0:-1} onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const index=tabs.findIndex(t=>t[0]===tab),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;selectTab(tabs[next][0]);document.getElementById(`${id}-${tabs[next][0]}`)?.focus();}}} onClick={()=>selectTab(key)}>{label}{count!==null&&<span>{count}</span>}{key==='json'&&rawDirty&&<span>Unsaved</span>}</button>)}
  </div>
  <div className={`${styles.body} ${showSource&&source?styles.comparing:''}`}>
   {showSource&&source&&<aside className={styles.source} aria-label="Source comparison">
    <div className={styles.sourceHeading}><strong title={source.name}>{source.name}</strong>{preview&&<a href={preview.url} target="_blank" rel="noopener noreferrer">Open ↗</a>}</div>
    {preview&&<div className={styles.zoom}><button aria-label="Zoom source out" disabled={zoom<=.5} onClick={()=>setZoom(z=>Math.max(.5,z-.25))}>−</button><button onClick={()=>setZoom(1)}>Fit</button><button aria-label="Zoom source in" disabled={zoom>=4} onClick={()=>setZoom(z=>Math.min(4,z+.25))}>+</button><span>{Math.round(zoom*100)}%</span>{sourcePages.length>1&&<label>Page <select aria-label="Source page" value={sourcePage} onChange={e=>setSourcePage(+e.target.value)}>{sourcePages.map(p=><option key={p} value={p}>{p}</option>)}</select></label>}</div>}
    {!!hotspots.length&&<p className={styles.sourceLegend}>Amber regions need review. Click a region to mark it checked.</p>}
    <div className={styles.sourceViewport}>{sourceError?<p role="alert">Source preview unavailable: {sourceError}</p>:!preview||(['application/pdf','image/tiff'].includes(preview.type)&&!sourceUrl)?<p>Loading source…</p>:sourceUrl?<div className={styles.imageFrame} style={{width:`${zoom*100}%`}}>
      <img alt={`Original schematic for comparison, page ${sourcePage}`} src={sourceUrl}/>
      <div className={styles.hotspotOverlay} aria-label="Source review regions">{pageHotspots.map(h=><button key={h.id} type="button" aria-label={`Review ${h.ref||'source'}${h.pin?` pin ${h.pin}`:''}: ${h.reason}`} aria-pressed={h.reviewed} title={`${h.reason} · ${evidenceText(h)}`} disabled={busy||rawDirty} className={`${styles.hotspot} ${h.reviewed?styles.hotspotReviewed:''}`} onClick={()=>toggleHotspot(h.id)} style={{left:`${100*h.bbox[0]/h.source_width}%`,top:`${100*h.bbox[1]/h.source_height}%`,width:`${100*(h.bbox[2]-h.bbox[0])/h.source_width}%`,height:`${100*(h.bbox[3]-h.bbox[1])/h.source_height}%`}}/>)}</div>
     </div>:<p>Use Open to view this source file.</p>}</div>
   </aside>}
   <div ref={panel} className={styles.panel} id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`}>
    {(tab==='components'||tab==='connections')&&<div className={styles.tools}><label className={styles.search}><span>{tab==='components'?'Find a component':'Find a net or pin'}</span><input aria-label={tab==='components'?'Filter components':'Filter nets'} value={query} placeholder={tab==='components'?'Reference, value or library…':'Net name, U61 or U61:6…'} onChange={e=>setQuery(e.target.value)}/></label><button disabled={busy||rawDirty} onClick={tab==='components'?addComponent:addNet}>{tab==='components'?'+ Add component':'+ Add net'}</button></div>}
    {tab==='components'&&<>
     <p className={styles.hint}>{components.length} of {circuit.components.length} shown. Changing a reference also updates its connections.</p>
     <div className={styles.componentRows}>
      <div className={styles.componentLabels} aria-hidden="true"><span>Reference</span><span>Part / value</span><span>KiCad library symbol</span><span/></div>
      {components.map(({c,i})=><div className={styles.componentRow} key={i}>
       <label className={styles.field}><span>Reference</span><input disabled={busy||rawDirty} aria-label={`Component ${i+1} reference`} value={c.ref} onChange={e=>update(renameComponent(circuit,i,e.target.value.toUpperCase()))}/></label>
       <label className={styles.field}><span>Part / value</span><input disabled={busy||rawDirty} aria-label={`${c.ref||'Component '+(i+1)} value`} value={c.value} onChange={e=>editComponent(i,'value',e.target.value)}/></label>
       <label className={styles.field}><span>KiCad library symbol</span><input disabled={busy||rawDirty} aria-label={`${c.ref||'Component '+(i+1)} KiCad symbol`} placeholder="Library:Symbol or resolve by value" value={c.library||''} onChange={e=>editComponent(i,'library',e.target.value||null)}/></label>
       <button className={styles.remove} disabled={busy||rawDirty} aria-label={`Remove ${c.ref||'component '+(i+1)}`} onClick={()=>update(removeComponent(circuit,i))}>Remove</button>
      </div>)}
     </div>
     {!components.length&&<div className={styles.empty}>No matching components.{query&&<button onClick={()=>setQuery('')}>Clear filter</button>}</div>}
    </>}
    {tab==='connections'&&<div className={styles.connections}>
     <div className={styles.netList} aria-label="Circuit nets">{nets.map(({n,i})=><button key={i} aria-pressed={selected?.i===i} onClick={()=>setActiveNet(i)}><strong>{n.name||'(unnamed net)'}</strong><span>{n.nodes.length} pins</span></button>)}{!nets.length&&<p>No matching nets.</p>}</div>
     {selected&&<section className={styles.netEditor} aria-label="Selected net">
      <div className={styles.netHeading}><label className={styles.field}><span>Net name</span><input aria-label="Net name" disabled={busy||rawDirty} value={selected.n.name} onChange={e=>editNet(selected.i,{...selected.n,name:e.target.value})}/></label><button className={styles.remove} disabled={busy||rawDirty} onClick={()=>removeNet(selected.i)}>Remove net</button></div>
      <p className={styles.evidence} title="Evidence score is a review heuristic, not measured accuracy.">{evidenceText(selected.n)}</p>
      <p className={styles.hint}>Use physical pin numbers from the symbol. Each pin can belong to one net.</p>
      {selected.n.nodes.map((p,j)=><div className={styles.pinRow} key={j}>
       <label className={styles.field}><span>Component</span><select aria-label={`Connection ${j+1} component`} disabled={busy||rawDirty} value={p.ref} onChange={e=>editNet(selected.i,{...selected.n,nodes:selected.n.nodes.map((q,k)=>k===j?{...q,ref:e.target.value}:q)})}><option value="">Select component</option>{circuit.components.map((c,k)=><option key={k} value={c.ref}>{c.ref||'(unnamed)'}</option>)}</select></label>
       <label className={styles.field}><span>Physical pin</span><input aria-label={`Connection ${j+1} physical pin`} disabled={busy||rawDirty} value={p.pin} onChange={e=>editNet(selected.i,{...selected.n,nodes:selected.n.nodes.map((q,k)=>k===j?{...q,pin:e.target.value}:q)})}/></label>
       <button className={styles.remove} aria-label={`Remove connection ${j+1}`} disabled={busy||rawDirty} onClick={()=>editNet(selected.i,{...selected.n,nodes:selected.n.nodes.filter((_,k)=>k!==j)})}>Remove</button>
      </div>)}
      <div className={styles.pinEvidence}>{selected.n.nodes.map((p,j)=><span key={j}>{p.ref}:{p.pin} · {evidenceText(p)}</span>)}</div>
      <button disabled={busy||rawDirty||!circuit.components.length} onClick={()=>editNet(selected.i,{...selected.n,nodes:[...selected.n.nodes,{ref:'',pin:''}]})}>+ Add pin</button>
     </section>}
    </div>}
    {tab==='checks'&&<div className={styles.notes}>
     <h3>{errors.length?`${errors.length} issues need correction`:'No structural issues found'}</h3>
     <p className={styles.hint}>These checks catch missing fields and conflicting pin assignments. Compare the circuit with the source to verify recognition.</p>
     {!!errors.length&&<ul className={styles.issues}>{errors.map((text,i)=><li key={i}>{text}</li>)}</ul>}
     {!!hotspots.length&&<section aria-label="Review region list"><h3>Source review regions ({hotspots.length})</h3>
      <p className={styles.hint}>Scores describe the available evidence, not measured accuracy. Confirmation marks a region checked and leaves its score unchanged.</p>
      <div className={styles.regionList}>{hotspots.slice(0,hotspotLimit).map(h=><div key={h.id} className={styles.regionRow}>
       <div><strong>{h.ref||'Source'}{h.pin?` · pin ${h.pin}`:''} · page {h.page||1}</strong><p>{h.reason}</p><small>{h.stale?'Source evidence predates your edit':evidenceText(h)}</small></div>
       {source&&<button disabled={busy||h.stale} onClick={()=>{setSourcePage(h.page||1);setShowSource(true);}}>Show</button>}
       <button disabled={busy||rawDirty||h.stale} aria-pressed={h.reviewed} onClick={()=>toggleHotspot(h.id)}>{h.stale?'Edited':h.reviewed?'Checked':'Confirm'}</button>
      </div>)}</div>{hotspotLimit<hotspots.length&&<button onClick={()=>setHotspotLimit(n=>n+50)}>Show 50 more regions</button>}
     </section>}
     <h3>Recognition notes ({warnings.length})</h3>{warnings.length?<ul>{warnings.map((text,i)=><li key={i}>{text}</li>)}</ul>:<p>No recognition notes were provided.</p>}
    </div>}
    {tab==='json'&&<div className={styles.jsonEditor}><p>Edit the complete circuit, including source positions and pin metadata. Apply valid JSON changes before importing.</p><textarea aria-label="Circuit JSON" spellCheck={false} disabled={busy} value={raw} onChange={e=>{setRaw(e.target.value);setRawDirty(true);setReviewed(false);}}/><div><button disabled={busy||!rawDirty} onClick={applyRaw}>Use JSON changes</button><button disabled={busy||!rawDirty} onClick={()=>{setRaw(JSON.stringify(circuit,null,2));setRawDirty(false);setError('');}}>Discard JSON changes</button></div></div>}
   </div>
  </div>
  <footer className={styles.footer}>
   {error&&<p className={styles.error} role="alert">{error}</p>}
   <label className={styles.confirm}><input type="checkbox" disabled={busy||rawDirty||!!errors.length} checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>I checked the component values, symbols and pin connections against the source.</span></label>
   <div className={styles.actions}><div className={styles.gate} aria-live="polite">{busy?'Writing and validating your design…':rawDirty?'Apply or discard your JSON changes.':errors.length?<button onClick={()=>selectTab('checks')}>Resolve {errors.length} issues to continue</button>:reviewed?'Ready to apply your review.':'Confirm your review to continue.'}</div>
    <button disabled={busy} onClick={onClose}>Cancel</button>
    {onOrcad&&<select aria-label="Review export target" disabled={busy} value={target} onChange={e=>setTarget(e.target.value)}><option value="kicad">KiCad project</option><option value="orcad">OrCAD Capture</option></select>}
    <button className={styles.primary} disabled={busy||!ready} onClick={submit}>{busy?'Working…':target==='orcad'?'Generate & verify OrCAD .DSN':onOrcad?'Import into KiCad project':'Apply reviewed circuit'}</button>
   </div>
  </footer>
 </WorkbenchDialog>;
}
