'use client';
import {useEffect,useState} from 'react';

// Physical netlist of the saved design, read back from the reopened .DSN: nets with part.pin
// connections, and parts with their PCB footprints.
export default function OrcadNetlist({pid,request,onDownload,stamp}){
 const [net,setNet]=useState(null),[error,setError]=useState(''),[q,setQ]=useState(''),[view,setView]=useState('nets');
 useEffect(()=>{let active=true;setNet(null);request(`/projects/${pid}/orcad/netlist`).then(r=>r.json()).then(j=>{if(active)setNet(j);}).catch(e=>{if(active)setError(e.message);});return ()=>{active=false;};},[pid,request,stamp]);
 if(error)return <p className="orcad-note">{error}</p>;
 if(!net)return <p className="orcad-note">Loading the physical netlist…</p>;
 const s=q.trim().toUpperCase();
 const nets=net.nets.filter(n=>!s||n.name.toUpperCase().includes(s)||n.nodes.some(p=>`${p.ref}.${p.pin}`.toUpperCase().includes(s)||p.ref.toUpperCase()===s));
 const parts=net.parts.filter(p=>!s||[p.ref,p.value,p.footprint,p.package].some(v=>(v||'').toUpperCase().includes(s)));
 const connections=net.nets.reduce((a,n)=>a+n.nodes.length,0);
 return <section className="orcad-netlist">
  <div className="orcad-netlist-head">
   <h3>Physical netlist</h3>
   <span>{net.nets.length} nets · {connections} pin connections · {net.parts.length} parts — read back from the saved .DSN</span>
  </div>
  <div className="orcad-netlist-tools">
   <div className="orcad-netlist-tabs" role="tablist">
    <button role="tab" aria-selected={view==='nets'} className={view==='nets'?'active':''} onClick={()=>setView('nets')}>Nets</button>
    <button role="tab" aria-selected={view==='parts'} className={view==='parts'?'active':''} onClick={()=>setView('parts')}>Parts &amp; footprints</button>
   </div>
   <input type="search" aria-label="Filter the netlist" placeholder="Filter: net, U12, U12.5, footprint…" value={q} onChange={e=>setQ(e.target.value)}/>
   <button onClick={()=>onDownload('net')}>PCB Editor netlist (.net)</button>
   <button onClick={()=>onDownload('csv')}>Netlist (.csv)</button>
  </div>
  <div className="orcad-netlist-table">
   {view==='nets'?<table><thead><tr><th>Net</th><th>Pins</th><th>Connections (part.pin)</th></tr></thead><tbody>
    {nets.slice(0,400).map(n=><tr key={n.name}><td>{n.name}</td><td>{n.nodes.length}</td><td className="orcad-pins">{n.nodes.map(p=>`${p.ref}.${p.pin}`).join('  ')}</td></tr>)}
   </tbody></table>:<table><thead><tr><th>Reference</th><th>Value</th><th>PCB footprint</th><th>Capture symbol</th></tr></thead><tbody>
    {parts.map(p=><tr key={p.ref}><td>{p.ref}</td><td>{p.value}</td><td>{p.footprint||<em>none</em>}</td><td>{p.library}{p.package?` : ${p.package}`:''}</td></tr>)}
   </tbody></table>}
   {view==='nets'&&nets.length>400&&<p className="orcad-note">Showing 400 of {nets.length} nets; filter or download for the rest.</p>}
  </div>
 </section>;
}
