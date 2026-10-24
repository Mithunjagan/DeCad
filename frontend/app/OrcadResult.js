'use client';
import {useEffect,useState} from 'react';
import WorkbenchDialog from './WorkbenchDialog';
import OrcadNetlist from './OrcadNetlist';
import {VerificationRibbon,ComparisonView,useCadProof} from './EngineeringProof';
// Generated OrCAD design: the saved .DSN read back from Capture's database and drawn, with its verification record.
export default function OrcadResult({pid,api,request,onDownload,onClose}){
 const [info,setInfo]=useState(null),[error,setError]=useState(''),[note,setNote]=useState(''),[stamp]=useState(()=>Date.now());
 useEffect(()=>{let active=true;request(`/projects/${pid}/orcad`).then(r=>r.json()).then(j=>{if(active)setInfo(j);}).catch(e=>{if(active)setError(e.message);});return ()=>{active=false;};},[pid,request]);
 const open=async()=>{try{setNote('');const j=await (await request(`/projects/${pid}/orcad/open`,{method:'POST'})).json();setNote(`${j.status}: ${j.path}`);}catch(e){setError(e.message);}};
 const d=info?.design;
 const proof=useCadProof(request,pid,false);
 const [original,setOriginal]=useState(null);
 useEffect(()=>{let active=true,url;const source=proof?.graph?.image_metadata?.review_source;if(!source?.path)return;
  request(source.path).then(r=>r.blob()).then(blob=>{if(!active)return;url=URL.createObjectURL(blob);setOriginal(url);}).catch(()=>{});
  return()=>{active=false;if(url)URL.revokeObjectURL(url);};},[request,proof?.graph]);
 return <WorkbenchDialog title="OrCAD Capture design" onClose={onClose}>
  {d?<>
   <VerificationRibbon circuit={proof?.graph} design={d}/>
   <ComparisonView sourceUrl={original} generatedUrl={proof?.url}/>
   <div className="orcad-stats">
    <div><strong>{d.routing?.endpoint_verification?.free_end_count?'Draft: open wire ends':d.passed?'Assigned pins verified':'Not verified'}</strong><span>native Capture readback</span></div>
    <div><strong>{d.components}</strong><span>parts placed</span></div>
    <div><strong>{d.checked_pins}</strong><span>pin connections checked</span></div>
    <div><strong>{d.nets}</strong><span>nets</span></div>
   </div>
   <p>{d.design} ({Math.round((d.size||0)/1024)} KB){d.generated_symbols?.length?` · ${d.generated_symbols.length} generated symbol(s) shipped in DECAD_GENERATED.OLB`:''}</p>
   {d.footprints&&<p className="orcad-footprints"><strong>PCB footprints: {d.footprints.assigned}/{d.footprints.total} parts</strong>{d.footprints.placed!==undefined?` (${d.footprints.placed} confirmed in the reopened design)`:''}{Object.keys(d.footprints.sources||{}).length?' · '+Object.entries(d.footprints.sources).map(([k,v])=>`${v} from ${k}`).join(', '):''}{d.footprints.without?.length?` · no footprint: ${d.footprints.without.join(', ')} (add them in Libraries & footprints)`:''}{d.footprints.placeholder?.length?` · placeholder header, review: ${d.footprints.placeholder.join(', ')}`:''}</p>}
   {!!(d.pcb_readiness?.missing?.length||d.netlist?.without_footprint?.length)&&<div role="alert" className="workflow-error"><strong>PCB netlisting blocked: missing footprint properties.</strong> Assign the correct packages in Libraries &amp; footprints, then regenerate the design. Schematic connectivity verification does not certify PCB readiness.</div>}
   {!!d.pcb_readiness?.needs_review?.length&&<p className="orcad-footprints"><strong>PCB package review required:</strong> {d.pcb_readiness.needs_review.join(', ')} use automatically suggested footprints. Confirm their package, pin count and pad numbering before PCB layout.</p>}
   {d.pcb_readiness&&<p className="orcad-footprints">{d.pcb_readiness.footprint_properties_complete?'Footprint properties confirmed in the saved design.':'Some footprint properties remain unresolved.'} {d.pcb_readiness.native_pcb_netlisting_verified?'Native PCB netlisting verified.':'Native PCB netlisting has not been verified.'}</p>}
   {d.routing&&<p className="orcad-footprints">{d.routing.error?`Wiring: ${d.routing.error}`:d.routing.all_connections_wired?<><strong>Assigned pin connectivity checked: {d.routing.wired_nets} nets</strong> · {d.routing.singleton_pins} isolated pins have no reviewed connection to draw.</>:<>Earlier export: {d.routing.wired_nets} nets drawn as wires · {d.routing.labelled_nets} nets use labels. Regenerate to require visible wiring.</>}</p>}
   {d.routing?.endpoint_verification?.free_end_count>0&&<div role="alert" className="workflow-error"><strong>Incomplete drawing: {d.routing.endpoint_verification.free_end_count} free wire ends require review.</strong> Matching assigned pins does not prove that all source wires were reconstructed. This download is an editable draft.</div>}
   {d.source_layout&&<p className="orcad-footprints">Source geometry retained for {d.source_layout.source_geometry_components.length} components.{d.source_layout.fallback_components.length?` Geometry unavailable or ambiguous for ${d.source_layout.fallback_components.join(', ')}; compare these symbols and positions with the source.`:''}</p>}
   {d.visual_comparison&&<details className="orcad-howto" open={!d.visual_comparison.source_faithful}><summary>{d.visual_comparison.source_faithful?'Source geometry checks passed':'Source drawing still needs review'}</summary>
    <p>{d.visual_comparison.observed_source_edges_kept} observed conductor paths retained. {d.visual_comparison.pins_above_grid_tolerance} pin positions differ beyond grid rounding. {d.visual_comparison.symbol_mismatches.length} symbols need review.</p>
    <p>Electrical agreement does not certify visual reconstruction. The download includes visual-comparison.json and routing-audit.json with every inferred route and unresolved discrepancy.</p>
   </details>}
   {!!Object.keys(d.user_libraries||{}).length&&<p className="orcad-footprints">Workspace libraries used: {Object.entries(d.user_libraries).map(([k,v])=>`${k} (${v.length} parts)`).join(', ')}</p>}
   {!!d.corrections?.length&&<details className="review-notices"><summary>{d.corrections.length} automatic correction(s) made during verification</summary>{d.corrections.map((c,i)=><p key={i}>{c}</p>)}</details>}
   <div className="orcad-preview"><img alt={`${d.design} drawn from the saved design`} src={`${api}/projects/${pid}/orcad/preview.svg?v=${stamp}`}/></div>
   {d.source_comparison_available&&<details className="orcad-howto"><summary>Compare source and reconstructed drawing</summary><div className="orcad-preview"><img alt="Original source beside the reconstructed Capture drawing in the same coordinate frame" src={`${api}/projects/${pid}/orcad/file?name=source-versus-output.svg&v=${stamp}`}/></div></details>}
   <OrcadNetlist pid={pid} request={request} stamp={stamp} onDownload={kind=>{const stem=d.design.replace(/\.DSN$/i,'');const name=kind==='net'?`${stem}.net`:'netlist.csv';const a=document.createElement('a');a.href=`${api}/projects/${pid}/orcad/file?name=${encodeURIComponent(name)}`;a.download=name;document.body.appendChild(a);a.click();a.remove();}}/>
   <details className="orcad-howto"><summary>How to see it in OrCAD Capture</summary>
    <ol>
     <li>Click <strong>Open in OrCAD Capture</strong>. Capture opens the project; the schematic is not shown until you open its page.</li>
     <li>In the project tree on the left: expand <strong>{d.design.toLowerCase()}</strong> → <strong>SCHEMATIC1</strong>, then double-click <strong>PAGE1</strong>. Press <strong>Zoom All</strong> to fit.</li>
     <li>Capture's own netlist: select <strong>{d.design.toLowerCase()}</strong> in the tree → <strong>Tools → Create Netlist → PCB</strong>. {d.footprints?.without?.length?`Give ${d.footprints.without.join(', ')} a PCB Footprint first (Libraries & footprints), or Capture stops with ORNET-1193.`:'PCB netlisting additionally requires valid package footprints. Electrical comparison is included in verification.json.'}</li>
     <li>OrCAD PCB Editor: <strong>File → Import → Logic/Netlist → Other</strong> and choose the downloaded <strong>.net</strong> file.</li>
    </ol>
   </details>
  </>:<p>{error?'':'Loading the saved design…'}</p>}
  {note&&<p className="orcad-note">{note}</p>}
  {error&&<div role="alert" className="workflow-error">{error}</div>}
  <div className="modal-actions"><button onClick={onClose}>Close</button><button onClick={onDownload}>Download design (.zip)</button>{info?.capture&&<button className="btn-primary" onClick={open}>Open in OrCAD Capture</button>}</div>
 </WorkbenchDialog>;
}
