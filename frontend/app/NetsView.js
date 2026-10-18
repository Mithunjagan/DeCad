'use client';
import {useMemo,useState} from 'react';
export default function NetsView({nets,onPrompt}){
 const [query,setQuery]=useState(''),[kind,setKind]=useState('all');
 const singles=nets.filter(n=>n.nodes.length===1).length;
 const shown=useMemo(()=>nets.filter(n=>(kind==='all'||(kind==='single'?n.nodes.length===1:n.nodes.length>1))&&[n.name,...n.nodes.map(p=>`${p.ref}:${p.pin}`)].some(s=>s.toLowerCase().includes(query.toLowerCase()))),[nets,query,kind]);
 return <section className="nets-workspace" aria-label="Electrical nets">
  <div className="nets-heading"><div><h2>Electrical connections</h2><p>{nets.length} nets · {singles} single-pin nets. These are KiCad’s current netlist connections.</p></div><button className="studio-secondary" onClick={()=>onPrompt('connect net GND to ')}>Edit with assistant</button></div>
  <div className="nets-filters"><label>Find net or pin<input aria-label="Search electrical nets" placeholder="Search a net, U61 or U61:6…" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Connections<select aria-label="Filter net connections" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All nets</option><option value="multi">Multiple pins</option><option value="single">Single pin</option></select></label><span>{shown.length} shown</span></div>
  <div className="nets-table-scroll"><table className="nets-table"><thead><tr><th scope="col">Net name</th><th scope="col">Physical pins</th><th scope="col">Class</th></tr></thead><tbody>{shown.map(n=><tr key={n.name}><td><strong>{n.name}</strong>{n.nodes.length===1&&<small>Single pin</small>}</td><td><div className="net-pin-tags">{n.nodes.map(p=><span key={`${p.ref}:${p.pin}`}>{p.ref}<b>:{p.pin}</b></span>)}</div></td><td>{n.class||'Default'}</td></tr>)}</tbody></table>{!shown.length&&<div className="nets-empty">{nets.length?'No nets match your filters.':'No nets are defined. Add wires or labels in the schematic editor.'}{!!nets.length&&<button className="studio-secondary" onClick={()=>{setQuery('');setKind('all');}}>Clear filters</button>}</div>}</div>
 </section>;
}
