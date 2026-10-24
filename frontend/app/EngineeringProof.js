'use client';
import {useEffect,useState} from 'react';
import {circuitSignature,engineeringMetrics} from './engineering-proof.mjs';
import styles from './CircuitReview.module.css';

export function VerificationRibbon({circuit,design}){
 const m=engineeringMetrics(circuit,design);
 const badge=(label,value,suffix='')=><span title={label==='ERC Status'?'Native readback short check; full CAD ERC is separate.':undefined} className={value===0?styles.proofGood:styles.proofPending}>{label}: {value==null?'Not checked':`${value}${suffix}`}</span>;
 return <div className={styles.proofRibbon} role="status" aria-label="Engineering verification scorecard">
  <span>Components <strong>{m.components}</strong></span><span>Total Physical Pins <strong>{m.pins}</strong></span>
  <span>Multi-Pin Wired Nets <strong>{m.multi??'Pending'}</strong></span><span>Labeled Signal Stubs <strong>{m.stubs??'Pending'}</strong></span>
  {badge('Unlabelled Loose Ends',m.loose)}{badge('ERC Status',m.shorts,' Power/GND Shorts')}
  <span className={m.verified?styles.proofGood:styles.proofPending}>Export Readback: {m.verified?'Verified':'Pending'}</span>
 </div>;
}

export function ComparisonView({sourceUrl,generatedUrl,label='Generated wired CAD schematic',overlay}){
 const [open,setOpen]=useState(false);
 return <section className={styles.comparisonProof}>
  <button type="button" disabled={!sourceUrl||!generatedUrl} aria-pressed={open} onClick={()=>setOpen(v=>!v)}>Side-by-Side Comparison View</button>
  {!generatedUrl&&<small>Available after a CAD preview is generated.</small>}
  {open&&sourceUrl&&generatedUrl&&<div className={styles.proofColumns}>
   <figure><figcaption>Original Source Schematic</figcaption><div className={styles.proofImage}><img src={sourceUrl} alt="Original source schematic"/>{overlay}</div></figure>
   <figure><figcaption>{label}</figcaption><img src={generatedUrl} alt={label}/></figure>
  </div>}
 </section>;
}

export function useCadProof(request,projectId,refresh,preferred='orcad'){
 const [proof,setProof]=useState(null);
 useEffect(()=>{
  let active=true,url;
  setProof(null);if(!projectId)return;
  (async()=>{
   try{
    if(preferred==='kicad')throw Error('KiCad selected');
    const status=await (await request(`/projects/${projectId}/orcad`)).json();
    if(!status.design)throw Error('No OrCAD export');
    const graph=await (await request(`/projects/${projectId}/orcad/file?name=circuit.json`)).json();
    const image=await (await request(`/projects/${projectId}/orcad/preview.svg`)).blob();
    if(!active)return;url=URL.createObjectURL(new Blob([image],{type:'image/svg+xml'}));
    setProof({design:status.design,graph,signature:circuitSignature(graph),url,label:'Generated wired OrCAD schematic'});
   }catch{
    try{const response=await request(`/projects/${projectId}/preview.svg`);if(!response.ok)return;const image=await response.blob();
     let graph,design;
     try{const text=await (await request(`/projects/${projectId}/netlist`)).text(),xml=new DOMParser().parseFromString(text,'application/xml');
      if(xml.querySelector('parsererror')||!xml.querySelector('export'))throw Error('No native XML');
      graph={components:[...xml.querySelectorAll('components > comp')].map(c=>({ref:c.getAttribute('ref'),value:c.querySelector('value')?.textContent||''})),
       nets:[...xml.querySelectorAll('nets > net')].map(n=>({name:n.getAttribute('name').replace(/^\//,''),nodes:[...n.querySelectorAll('node')].map(p=>({ref:p.getAttribute('ref'),pin:p.getAttribute('pin')}))}))};
      design={passed:true,components:graph.components.length,checked_pins:graph.nets.flatMap(n=>n.nodes).length};
     }catch{/* A preview alone never certifies readback. */}
     if(!active)return;url=URL.createObjectURL(new Blob([image],{type:'image/svg+xml'}));setProof({url,graph,design,signature:graph?circuitSignature(graph):null,label:'Generated KiCad schematic'});
    }catch{/* No saved preview yet. */}
   }
  })();
  return()=>{active=false;if(url)URL.revokeObjectURL(url);};
 },[request,projectId,refresh,preferred]);
 return proof;
}
