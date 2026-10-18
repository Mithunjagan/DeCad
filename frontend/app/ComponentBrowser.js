'use client';
import {useEffect,useState} from 'react';
import styles from './ComponentBrowser.module.css';

export default function ComponentBrowser({pid,request,onStatus,onProjectChanged}){
 const [status,setStatus]=useState(null),[query,setQuery]=useState(''),[items,setItems]=useState([]);
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [location,setLocation]=useState(''),[license,setLicense]=useState('Unknown'),[rights,setRights]=useState('reference');
 const [cursors,setCursors]=useState({}),[symbol,setSymbol]=useState(null),[footprint,setFootprint]=useState(null),[checked,setChecked]=useState(null);
 const [target,setTarget]=useState('internal'),[ref,setRef]=useState('U1'),[installed,setInstalled]=useState(false),[external,setExternal]=useState(true);
 const [provider,setProvider]=useState({name:'',base_url:'',token_env:'',authorized:false});
 const policy=()=>({name:license,allow_import:rights!=='reference',allow_redistribute:rights==='export',evidence:'Permission recorded by the local workspace operator.'});
 const refresh=async()=>setStatus(await (await request('/components/status')).json());
 useEffect(()=>{refresh().catch(e=>setError(e.message));},[]);
 useEffect(()=>{let cancelled=false;const t=setTimeout(async()=>{try{const j=await (await request(`/components/search?q=${encodeURIComponent(query)}`)).json();if(!cancelled)setItems(j.items);}catch(e){if(!cancelled)setError(e.message);}},250);return()=>{cancelled=true;clearTimeout(t);};},[query,status]);
 const act=async(label,fn)=>{setBusy(label);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy('');}};
 const add=()=>act('Saving location…',async()=>{await request('/components/locations',{method:'POST',body:JSON.stringify({path:location,source_license:policy()})});await refresh();setMessage('Location saved. Scan it to index supported assets.');});
 const scan=root=>act(`Indexing ${root.path}…`,async()=>{const j=await (await request('/components/scan',{method:'POST',body:JSON.stringify({location:root.id,max_files:250,after:cursors[root.id]||''})})).json();setCursors(c=>({...c,[root.id]:j.cursor}));setMessage(`${j.indexed} files indexed, ${j.unchanged} unchanged. ${j.complete?'Scan complete.':'Use Continue scan for the next batch.'}${j.errors.length?' '+j.errors.length+' errors: '+j.errors[0].error:''}`);await refresh();});
 const resolve=()=>act('Finding components…',async()=>{const j=await (await request('/components/resolve',{method:'POST',body:JSON.stringify({query,search_installed:installed,external})})).json();setItems(j.items);setMessage(j.trace.map(s=>`${s.stage}: ${s.status||s.matches+' matches'}`).join(' · '));});
 const select=(item,kind)=>act('Reading component…',async()=>{const detail=await (await request(`/components/item/${item.id}?extract=true`)).json();if(kind==='symbol')setSymbol(detail);else setFootprint(detail);setChecked(null);});
 const validate=()=>act('Checking pin and pad mapping…',async()=>{const j=await (await request('/components/validate',{method:'POST',body:JSON.stringify({symbol:symbol.id,footprint:footprint.id})})).json();setChecked(j);setMessage(j.cached?'Pin/pad mapping verified and cached. Physical dimensions passed structural checks; compare manufacturer tolerances before manufacture.':j.validation.issues.join(' '));});
 const download=()=>act('Preparing component export…',async()=>{const r=await request(`/components/export/${symbol?.id||footprint?.id}?target=${target}`);const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=r.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'component.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 const advanceReference=circuit=>{const match=ref.match(/^(.*?)(\d+)$/);if(!match)return;const used=new Set((circuit?.components||[]).map(c=>c.ref));let number=Number(match[2])+1;while(used.has(match[1]+number))number++;setRef(match[1]+number);};
 const place=()=>act('Placing verified component…',async()=>{const j=await (await request(`/projects/${pid}/components/place`,{method:'POST',body:JSON.stringify({component:checked.id,ref})})).json();setMessage(`${ref} placed at ${j.position.x.toFixed(2)}, ${j.position.y.toFixed(2)} mm. Move it in the KiCad editor to refine the layout.`);advanceReference(j.circuit);onStatus?.(`${ref} placed from the unified library`);await onProjectChanged?.();});
 const acquire=()=>act('Searching libraries and acquiring verified assets…',async()=>{const j=await (await request(`/projects/${pid}/components/acquire`,{method:'POST',body:JSON.stringify({query,ref,external,footprint_id:footprint?.id})})).json();if(j.placement){setSymbol(j.component);setChecked(j.component);advanceReference(j.placement.circuit);setMessage(`${ref} added with a verified pin/pad mapping and project-local footprint. ${j.trace.map(t=>t.stage+': '+(t.status??t.matches+' matches')).join(' · ')}`);onStatus?.(`${ref} acquired and added to this project`);await onProjectChanged?.();}else{setItems(j.items||[]);setMessage(`${j.status}: ${j.message} ${j.issues?.map(i=>i.error||i.issues?.join(' ')).filter(Boolean).slice(0,3).join(' ')||''}`);}await refresh();});
 const upload=files=>act('Importing asset…',async()=>{for(const file of files){await request(`/components/upload?name=${encodeURIComponent(file.name)}&license_name=${encodeURIComponent(license)}&allow_import=${rights!=='reference'}&allow_redistribute=${rights==='export'}`,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});}await refresh();setMessage('Uploaded assets indexed. Unsupported geometry remains marked in the search results.');});
 return <article className={`library-card ${styles.browser}`}>
  <h3>Unified KiCad &amp; OrCAD component database</h3>
  <p>Search both ecosystems, inspect source permissions, and validate electrical pins against physical pads. Allegro binaries can be identified; their geometry conversion remains unavailable.</p>
  {error&&<p role="alert" className="library-error">{error}</p>}
  {busy&&<p role="status">{busy}</p>}{message&&<p role="status">{message}</p>}
  <details><summary>Library locations, asset import and source permissions</summary>
   <p>Unknown permissions allow metadata indexing only. Record the asset license before importing geometry or exporting assets. Source directories stay unchanged.</p>
   <label>Library directory <input aria-label="Unified library directory" value={location} onChange={e=>setLocation(e.target.value)} placeholder="Absolute path to a library folder"/></label>
   <label>Source license <input aria-label="Source license" value={license} onChange={e=>setLicense(e.target.value)}/></label>
   <label>Recorded permissions <select value={rights} onChange={e=>setRights(e.target.value)}><option value="reference">Metadata only / unknown</option><option value="import">License permits local import</option><option value="export">License permits import and redistribution</option></select></label>
   <button disabled={!!busy||!location} onClick={add}>Save location</button>
   <label>Import files <input type="file" multiple disabled={!!busy||rights==='reference'} accept=".kicad_sym,.kicad_mod,.olb,.dsn,.opj,.dra,.psm,.pad,.brd,.step,.stp,.wrl" onChange={e=>{upload([...e.target.files]);e.target.value='';}}/></label>
   <p>Detected locations:</p><div className="library-chips">{status?.discovered.map(p=><button key={p.path} onClick={()=>setLocation(p.path)}>{p.ecosystem}: {p.path}</button>)}</div>
   {status?.roots.map(root=><div key={root.id}><span>{root.path} · {root.source_license.name}</span> <button disabled={!!busy} onClick={()=>scan(root)}>{cursors[root.id]?'Continue scan':'Scan'}</button> <button disabled={!!busy} onClick={()=>act('Removing index…',async()=>{await request(`/components/locations/${root.id}`,{method:'DELETE'});await refresh();})}>Remove index</button></div>)}
  </details>
  <label>Search components <input className="library-search" type="search" value={query} onChange={e=>{setQuery(e.target.value);setSymbol(null);setFootprint(null);setChecked(null);}} placeholder="Part number or exact library symbol, e.g. Timer:NE555P"/></label>
  <label>Add as reference <input value={ref} onChange={e=>setRef(e.target.value)} aria-label="Acquired component reference"/></label>
  <button className="btn-primary" disabled={!!busy||!pid||!query||!ref} onClick={acquire}>Find component and add to project</button>
  <p>This searches local KiCad and OrCAD sources, then permitted external assets if enabled, checks the symbol against its footprint, and saves both in the project. New parts use spaced grid positions; references advance after placement. Move parts in the KiCad editor to refine the layout. Unresolved parts leave the project unchanged.</p>
  <label><input type="checkbox" checked={installed} onChange={e=>setInstalled(e.target.checked)}/> Search installed locations if absent locally</label>
  <label><input type="checkbox" checked={external} onChange={e=>setExternal(e.target.checked)}/> Query authorized external providers if absent locally</label>
  <button disabled={!!busy||!query} onClick={resolve}>Find component</button>
  <div style={{maxHeight:360,overflow:'auto'}}><table><thead><tr><th>Component</th><th>Source</th><th>License / validation</th><th>Select</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{item.name}<br/>{item.manufacturer_part_number}</td><td title={item.original_library_path}>{item.source_format}<br/>{item.kind}</td><td>{item.source_license.name}<br/>{item.validation.status}{item.validation.issues.length>0&&<details><summary>Limits</summary>{item.validation.issues.join(' ')}</details>}</td><td>{['symbol','footprint'].includes(item.kind)&&<button disabled={!!busy} onClick={()=>select(item,item.kind)}>Use {item.kind}</button>}</td></tr>)}</tbody></table></div>
  <p>Symbol: {symbol?.name||'none'} · Footprint: {footprint?.name||'none'}</p>
  <button disabled={!!busy||!symbol||!footprint} onClick={validate}>Validate and cache pair</button>
  {checked&&<p>Validation: {checked.validation.status}; pin/pad mapping: {checked.validation.pin_to_pad}.</p>}
  <label>Export target <select value={target} onChange={e=>setTarget(e.target.value)}><option value="internal">Internal component JSON</option><option value="kicad">KiCad library</option><option value="orcad">OrCAD Capture (availability checked)</option><option value="allegro">Allegro (availability checked)</option></select></label>
  <button disabled={!!busy||(!symbol&&!footprint)} onClick={download}>Export selected asset</button>
  <label>Reference <input value={ref} onChange={e=>setRef(e.target.value)} aria-label="Library placement reference"/></label>
  <button disabled={!!busy||!pid||!checked?.cached} onClick={place}>Place in current schematic</button>
  <details><summary>Format and version support</summary><table><thead><tr><th>Format</th><th>Implemented support</th><th>Tested versions</th></tr></thead><tbody>{status?.formats.map(f=><tr key={f.extension}><td>{f.extension}</td><td>{f.support}{f.requires_native&&!f.native_available?' — native API unavailable':''}</td><td>{f.tested_versions.join(', ')||'not verified'}</td></tr>)}</tbody></table></details>
  <details><summary>Authorized providers</summary><p>No provider is enabled by default. Providers must implement the documented DeCad asset-search protocol. Credentials use a backend environment variable.</p>
   <label>Provider name <input value={provider.name} onChange={e=>setProvider({...provider,name:e.target.value})}/></label>
   <label>HTTPS base URL <input value={provider.base_url} onChange={e=>setProvider({...provider,base_url:e.target.value})}/></label>
   <label>Token environment variable <input value={provider.token_env} onChange={e=>setProvider({...provider,token_env:e.target.value})}/></label>
   <label><input type="checkbox" checked={provider.authorized} onChange={e=>setProvider({...provider,authorized:e.target.checked})}/> I have authorization to use this provider</label>
   <p>The source license and permissions selected above apply to downloaded assets.</p>
   <button disabled={!!busy||!provider.name||!provider.base_url} onClick={()=>act('Saving provider…',async()=>{await request('/components/providers',{method:'POST',body:JSON.stringify({...provider,source_license:policy()})});await refresh();})}>Save provider</button>
   {status?.providers.map(p=><p key={p.id}>{p.name}: {p.authorized?'authorized':'disabled'} · {p.source_license.name}</p>)}
  </details>
 </article>;
}
