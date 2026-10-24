'use client';
import {useEffect,useState} from 'react';
import WorkbenchDialog from './WorkbenchDialog';
import OrcadNetlist from './OrcadNetlist';
// Generated OrCAD design: the saved .DSN read back from Capture's database and drawn, with its verification record.
export default function OrcadResult({pid,api,request,onDownload,onClose}){
 const [info,setInfo]=useState(null),[error,setError]=useState(''),[note,setNote]=useState(''),[stamp]=useState(()=>Date.now());
 useEffect(()=>{let active=true;request(`/projects/${pid}/orcad`).then(r=>r.json()).then(j=>{if(active)setInfo(j);}).catch(e=>{if(active)setError(e.message);});return ()=>{active=false;};},[pid,request]);
 const open=async()=>{try{setNote('');const j=await (await request(`/projects/${pid}/orcad/open`,{method:'POST'})).json();setNote(`${j.status}: ${j.path}`);}catch(e){setError(e.message);}};
 const d=info?.design;
 return <WorkbenchDialog title="OrCAD Capture design" onClose={onClose}>
  {d?<>
   <div className="orcad-stats">
    <div><strong>{d.passed?'Verified':'Not verified'}</strong><span>reopened in Capture</span></div>
    <div><strong>{d.components}</strong><span>parts placed</span></div>
    <div><strong>{d.checked_pins}</strong><span>pin connections checked</span></div>
    <div><strong>{d.nets}</strong><span>nets</span></div>
   </div>
   <p>{d.design} ({Math.round((d.size||0)/1024)} KB){d.generated_symbols?.length?` · ${d.generated_symbols.length} generated symbol(s) shipped in DECAD_GENERATED.OLB`:''}</p>
   {d.footprints&&<p className="orcad-footprints"><strong>PCB footprints: {d.footprints.assigned}/{d.footprints.total} parts</strong>{d.footprints.placed!==undefined?` (${d.footprints.placed} confirmed in the reopened design)`:''}{Object.keys(d.footprints.sources||{}).length?' · '+Object.entries(d.footprints.sources).map(([k,v])=>`${v} from ${k}`).join(', '):''}{d.footprints.without?.length?` · no footprint: ${d.footprints.without.join(', ')} (add them in Libraries & footprints)`:''}{d.footprints.placeholder?.length?` · placeholder header, review: ${d.footprints.placeholder.join(', ')}`:''}</p>}
   {d.routing&&<p className="orcad-footprints">{d.routing.error?`Wiring: ${d.routing.error}`:d.routing.all_connections_wired?<><strong>Visible wiring verified: {d.routing.wired_nets} nets</strong> · {d.routing.singleton_pins} isolated pins have no reviewed connection to draw.</>:<>Earlier export: {d.routing.wired_nets} nets drawn as wires · {d.routing.labelled_nets} nets use labels. Regenerate to require visible wiring.</>}</p>}
   {d.source_layout&&<p className="orcad-footprints">Source geometry retained for {d.source_layout.source_geometry_components.length} components.{d.source_layout.fallback_components.length?` Geometry unavailable or ambiguous for ${d.source_layout.fallback_components.join(', ')}; compare these symbols and positions with the source.`:''}</p>}
   {!!Object.keys(d.user_libraries||{}).length&&<p className="orcad-footprints">Workspace libraries used: {Object.entries(d.user_libraries).map(([k,v])=>`${k} (${v.length} parts)`).join(', ')}</p>}
   {!!d.corrections?.length&&<details className="review-notices"><summary>{d.corrections.length} automatic correction(s) made during verification</summary>{d.corrections.map((c,i)=><p key={i}>{c}</p>)}</details>}
   <div className="orcad-preview"><img alt={`${d.design} drawn from the saved design`} src={`${api}/projects/${pid}/orcad/preview.svg?v=${stamp}`}/></div>
   <OrcadNetlist pid={pid} request={request} stamp={stamp} onDownload={kind=>{const stem=d.design.replace(/\.DSN$/i,'');const name=kind==='net'?`${stem}.net`:'netlist.csv';const a=document.createElement('a');a.href=`${api}/projects/${pid}/orcad/file?name=${encodeURIComponent(name)}`;a.download=name;document.body.appendChild(a);a.click();a.remove();}}/>
   <details className="orcad-howto"><summary>How to see it in OrCAD Capture</summary>
    <ol>
     <li>Click <strong>Open in OrCAD Capture</strong>. Capture opens the project; the schematic is not shown until you open its page.</li>
     <li>In the project tree on the left: expand <strong>{d.design.toLowerCase()}</strong> → <strong>SCHEMATIC1</strong>, then double-click <strong>PAGE1</strong>. Press <strong>Zoom All</strong> to fit.</li>
     <li>Capture's own netlist: select <strong>{d.design.toLowerCase()}</strong> in the tree → <strong>Tools → Create Netlist → PCB</strong>. {d.footprints?.without?.length?`Give ${d.footprints.without.join(', ')} a PCB Footprint first (Libraries & footprints), or Capture stops with ORNET-1193.`:'Every part already has a PCB Footprint.'}</li>
     <li>OrCAD PCB Editor: <strong>File → Import → Logic/Netlist → Other</strong> and choose the downloaded <strong>.net</strong> file.</li>
    </ol>
   </details>
  </>:<p>{error?'':'Loading the saved design…'}</p>}
  {note&&<p className="orcad-note">{note}</p>}
  {error&&<div role="alert" className="workflow-error">{error}</div>}
  <div className="modal-actions"><button onClick={onClose}>Close</button><button onClick={onDownload}>Download design (.zip)</button>{info?.capture&&<button className="btn-primary" onClick={open}>Open in OrCAD Capture</button>}</div>
 </WorkbenchDialog>;
}
