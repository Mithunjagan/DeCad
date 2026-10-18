'use client';
import {useEffect,useRef,useState} from 'react';
import ComponentBrowser from './ComponentBrowser';

const LIBRARY_ACCEPT='.olb,.dsn,.zip,.csv,.psm,.dra,.pad,.bsm,.fsm,.ssm,.osm,.mdd,.kicad_mod';
const BLUEPRINT_ACCEPT='.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.pdf';
const kb=n=>n>1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.max(1,Math.round(n/1024))} KB`;

function DropZone({accept,multiple,disabled,onFiles,title,hint,busy}){
 const input=useRef(null),[over,setOver]=useState(false);
 const pick=list=>{const files=[...(list||[])];if(files.length&&!disabled)onFiles(files);};
 return <div role="button" tabIndex={0} aria-disabled={disabled} className={`library-drop ${over?'over':''} ${disabled?'disabled':''}`}
  onClick={()=>!disabled&&input.current?.click()} onKeyDown={e=>{if((e.key==='Enter'||e.key===' ')&&!disabled){e.preventDefault();input.current?.click();}}}
  onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={()=>setOver(false)} onDrop={e=>{e.preventDefault();setOver(false);pick(e.dataTransfer.files);}}>
  <input ref={input} type="file" hidden accept={accept} multiple={multiple} onChange={e=>{pick(e.target.files);e.target.value='';}}/>
  <strong>{busy||title}</strong><span>{hint}</span>
 </div>;
}

// Workspace libraries for OrCAD generation: blueprint conversion, symbol libraries, existing designs, footprints, part map.
export default function LibraryPanel({pid,api,request,onStatus,onOrcadReady,onProjectChanged}){
 const [lib,setLib]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(''),[added,setAdded]=useState([]);
 const [convert,setConvert]=useState(null),[now,setNow]=useState(Date.now());
 const [query,setQuery]=useState(''),[found,setFound]=useState(null),[row,setRow]=useState({key:'',footprint:'',symbol:''}),[stamp,setStamp]=useState(Date.now());
 const refresh=async()=>{try{setLib(await (await request('/library')).json());setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{refresh();},[]);
 useEffect(()=>{if(!convert?.running)return;const t=setInterval(()=>setNow(Date.now()),1000);return ()=>clearInterval(t);},[convert?.running]);
 useEffect(()=>{const t=setTimeout(async()=>{try{setFound(await (await request(`/library/footprints?q=${encodeURIComponent(query)}`)).json());}catch{}},250);return ()=>clearTimeout(t);},[query,lib]);

 const upload=async files=>{
  setError('');const out=[];
  for(const [i,file] of files.entries()){
   setBusy(`Adding ${file.name} (${i+1}/${files.length})…`);
   try{const j=await (await request(`/library/upload?name=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}})).json();out.push(...j.added);}
   catch(e){out.push({kind:'error',name:file.name,detail:e.message});}
  }
  setAdded(out);setBusy('');setStamp(Date.now());await refresh();
  const ok=out.filter(a=>a.kind!=='error'&&a.kind!=='skipped').length;onStatus?.(`Library: ${ok} item(s) added${out.some(a=>a.kind==='error')?', some files failed':''}`);
 };
 const blueprint=async([file])=>{
  if(!pid){setError('Create or open a project first; the design is saved in it.');return;}
  setError('');const started=Date.now();setNow(started);
  setConvert({running:true,file:file.name,stage:'Uploading the blueprint…',started});
  try{
   const up=await (await request(`/projects/${pid}/attachments?name=${encodeURIComponent(file.name)}`,{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream'}})).json();
   setConvert(c=>({...c,stage:'Reading the drawing, matching parts to the libraries, writing and verifying the .DSN (usually 1–3 minutes)…'}));
   const j=await (await request(`/projects/${pid}/orcad/auto`,{method:'POST',body:JSON.stringify({attachment:up.path,recognition_mode:'auto'})})).json();
   setConvert({running:false,file:file.name,started,finished:Date.now(),status:j.status,warnings:j.warnings||[]});
   onStatus?.(`OrCAD design verified: ${j.status.components} parts, ${j.status.checked_pins} pins`);onOrcadReady?.();
  }catch(e){setConvert({running:false,file:file.name,started,finished:Date.now(),error:e.message});}
 };
 const remove=async(kind,name)=>{if(!confirm(`Remove ${name} from the workspace library?`))return;try{await request(`/library/${kind}/${encodeURIComponent(name)}`,{method:'DELETE'});await refresh();}catch(e){setError(e.message);}};
 const saveRow=async e=>{e.preventDefault();try{await request('/library/partmap',{method:'POST',body:JSON.stringify(row)});setRow({key:'',footprint:'',symbol:''});await refresh();}catch(e){setError(e.message);}};
 const openDesign=async name=>{try{const j=await (await request(`/library/designs/${encodeURIComponent(name)}/open`,{method:'POST'})).json();onStatus?.(`${j.status}: ${j.path}`);}catch(e){setError(e.message);}};

 const parts=lib?.symbols.reduce((n,s)=>n+s.parts,0)||0,elapsed=s=>Math.round(((s.finished||now)-s.started)/1000);
 return <section className="integrations-panel library-panel">
  <h2>Libraries &amp; footprints</h2>
  <p>Add the libraries your team already uses. Generated OrCAD designs use these parts first, and every placed part gets a PCB footprint. The library is shared by all projects in this workspace.</p>
  {error&&<div role="alert" className="workflow-error">{error}</div>}
  <ComponentBrowser pid={pid} request={request} onStatus={onStatus} onProjectChanged={onProjectChanged}/>
  {lib&&!lib.available&&<p>Capture automation is unavailable on this computer. Unified KiCad imports and local component search remain available.</p>}

  <div className="library-grid">
   <article className="library-card">
    <h3>Blueprint → OrCAD Capture</h3>
    <p>Drop a schematic image or PDF (clear, scanned or blurry). DeCad reads it, matches parts against the built-in and workspace libraries, writes a native .DSN, then reopens it to check every pin.</p>
    <DropZone accept={BLUEPRINT_ACCEPT} disabled={!!convert?.running||!pid||!lib?.available} onFiles={blueprint} busy={convert?.running?`${convert.file} · ${elapsed(convert)} s`:''}
     title={pid?'Drop a blueprint here or choose a file':'Open a project first'} hint="PNG · JPG · TIFF · PDF"/>
    {convert&&<div className="library-progress" aria-live="polite">
     {convert.running&&<><div className="library-bar"><span/></div><p>{convert.stage}</p></>}
     {convert.status&&<p><strong>Verified .DSN in {elapsed(convert)} s:</strong> {convert.status.components} parts, {convert.status.checked_pins} pins checked, {convert.status.nets} nets{convert.status.footprints?`, ${convert.status.footprints.assigned}/${convert.status.footprints.total} footprints`:''}. <button onClick={onOrcadReady}>Show design</button></p>}
     {convert.error&&<p role="alert" className="library-error">{convert.error}</p>}
    </div>}
   </article>
   <article className="library-card">
    <h3>Add to the library</h3>
    <p>Capture symbol libraries (.OLB), existing designs (.DSN; their parts are extracted into a reusable library), footprints (.psm .dra .pad, KiCad .kicad_mod), a part-to-footprint .csv, or a .zip of any of these.</p>
    <DropZone accept={LIBRARY_ACCEPT} multiple disabled={!!busy} onFiles={upload} busy={busy} title="Drop library files here or choose files" hint=".OLB · .DSN · .psm/.dra/.pad · .kicad_mod · .csv · .zip"/>
    {!!added.length&&<ul className="library-added">{added.map((a,i)=><li key={i} className={a.kind==='error'?'library-error':''}><strong>{a.name}</strong> <span>{a.kind==='error'?'failed':a.kind}</span> {a.detail}</li>)}</ul>}
   </article>
  </div>

  <div className="orcad-stats library-stats">
   <div><strong>{lib?.symbols.length??'–'}</strong><span>symbol libraries ({parts} parts)</span></div>
   <div><strong>{lib?.designs.length??'–'}</strong><span>imported designs</span></div>
   <div><strong>{lib?.footprints.length??'–'}</strong><span>uploaded footprint files</span></div>
   <div><strong>{lib?.catalog??'–'}</strong><span>footprints available in total</span></div>
  </div>

  <h3>Imported designs</h3>
  {lib?.designs.length?<div className="library-designs">{lib.designs.map(d=><article key={d.name} className="library-card">
   {d.preview?<div className="library-thumb"><img alt={`${d.name} preview`} src={`${api}/library/designs/${encodeURIComponent(d.name)}/preview.svg?v=${stamp}`}/></div>:null}
   <h4>{d.name}</h4>
   <p>{d.library?`${d.parts.length} parts reusable from ${d.library}`:'Parts not extracted'}{d.notes?.length?` · ${d.notes.join(' ')}`:''}</p>
   <div className="library-actions"><button onClick={()=>openDesign(d.name)}>Open in OrCAD Capture</button><button onClick={()=>remove('designs',d.name)}>Remove</button></div>
  </article>)}</div>:<p>No designs yet. Drop a Capture .DSN above to reuse its parts.</p>}

  <h3>Symbol libraries</h3>
  {lib?.symbols.length?<table><thead><tr><th>Library</th><th>Parts</th><th>With footprint</th><th>Examples</th><th/></tr></thead><tbody>
   {lib.symbols.map(s=><tr key={s.name}><td>{s.name}{s.from_design?' (from design)':''}</td><td>{s.parts}</td><td>{s.footprints}</td><td>{s.sample.slice(0,6).join(', ')}</td><td><button onClick={()=>remove('symbols',s.name)}>Remove</button></td></tr>)}
  </tbody></table>:<p>None yet. The installed OrCAD libraries are always available; libraries added here take precedence.</p>}

  <h3>Part → footprint map</h3>
  <p>Matched by reference (U12), part number (74F174) or package name. A symbol override is written Library.olb:Package.</p>
  <form className="library-map-form" onSubmit={saveRow}>
   <input aria-label="Part number, reference or package" placeholder="Part number / reference / package" value={row.key} onChange={e=>setRow({...row,key:e.target.value})} required/>
   <input aria-label="PCB footprint" placeholder="PCB footprint (e.g. soic16)" list="library-footprint-names" value={row.footprint} onChange={e=>{setRow({...row,footprint:e.target.value});setQuery(e.target.value);}}/>
   <input aria-label="Symbol override" placeholder="Symbol override (optional)" value={row.symbol} onChange={e=>setRow({...row,symbol:e.target.value})}/>
   <button className="btn-primary" type="submit">Add mapping</button>
   <datalist id="library-footprint-names">{found?.items.map(i=><option key={i.name} value={i.name}>{i.source}</option>)}</datalist>
  </form>
  {lib?.partmap.length?<table><thead><tr><th>Key</th><th>PCB footprint</th><th>Symbol</th><th/></tr></thead><tbody>
   {lib.partmap.map(r=><tr key={r.key}><td>{r.key}</td><td>{r.footprint||'–'}</td><td>{r.symbol||'–'}</td><td><button onClick={()=>remove('partmap',r.key)}>Remove</button></td></tr>)}
  </tbody></table>:<p>No mappings. Without one, the footprint comes from the symbol library, or from a standard OrCAD PCB footprint chosen by package type and pin count.</p>}

  <h3>Footprints</h3>
  <input className="library-search" type="search" aria-label="Search footprints" placeholder={`Search ${lib?.catalog??''} footprints (dip, soic, to220…)`} value={query} onChange={e=>setQuery(e.target.value)}/>
  {found&&<div className="library-chips">{found.items.length?found.items.map(i=><button key={i.name} title={i.source} className={i.source==='uploaded'?'uploaded':''} onClick={()=>setRow(r=>({...r,footprint:i.name}))}>{i.name}</button>):<span>{query?'No match.':'No uploaded footprints yet; search the installed OrCAD PCB library above.'}</span>}</div>}
  {!!lib?.footprints.length&&<table><thead><tr><th>Uploaded file</th><th>Kind</th><th>Size</th><th/></tr></thead><tbody>
   {lib.footprints.map(f=><tr key={f.name}><td>{f.name}</td><td>{f.kind}</td><td>{kb(f.size)}</td><td><button onClick={()=>remove('footprints',f.name)}>Remove</button></td></tr>)}
  </tbody></table>}
 </section>;
}
