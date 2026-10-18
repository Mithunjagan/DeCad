'use client';
import {useEffect,useRef,useState} from 'react';
const tools=[['kicad','KiCad'],['ngspice','ngspice'],['ltspice','LTspice'],['qucs-s','Qucs-S']];
export default function ApplicationLauncher({project,request,onStatus,onSelect,compact=false}){
 const [data,setData]=useState(null),[pending,setPending]=useState(''),[error,setError]=useState('');
 const mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const refresh=()=>request('/integrations').then(r=>r.json()).then(d=>{if(mounted.current)setData(d);}).catch(e=>{if(mounted.current)setError(e.message);});
 useEffect(()=>{refresh();},[project]);
 const open=async id=>{
  setPending(id);setError('');onSelect(id);
  try{
   let job=await (await request(`/projects/${project}/integrations/${id}/open`,{method:'POST'})).json();
   onStatus(`${id}: opening project…`);
   for(let i=0;i<30&&job.status==='queued'&&mounted.current;i++){
    await new Promise(r=>setTimeout(r,500));
    job=await (await request(`/integrations/jobs/${job.id}`)).json();
   }
   if(!mounted.current)return;
   if(job.status==='failed')throw new Error(job.error||'Application launch failed');
   if(job.status==='queued')throw new Error('Launch pending. Check the desktop bridge before trying again.');
   onStatus(`${id}: ${job.status}`);
  }catch(e){if(mounted.current){setError(e.message);onStatus(e.message);}}
  finally{if(mounted.current)setPending('');}
 };
 return <section className={`application-launcher ${compact?'compact':''}`} aria-label="Desktop applications">
  <div className="launcher-heading"><span>Applications</span><button onClick={refresh} title="Refresh application availability" aria-label="Refresh application availability">↻</button></div>
  <div className="launcher-tools">{tools.map(([id,name])=>{
   const app=data?.applications?.find(a=>a.id===id),ready=data?.desktop?.ready&&app?.host_installed;
   const reason=!project?'Select a project':!data?.desktop?.ready?'Start the desktop bridge':!app?.host_installed?`Install ${name}`:`Open current project in ${name}`;
   return <button key={id} title={reason} disabled={!project||!!pending||!ready} onClick={()=>open(id)}><span>{name}</span><small>{pending===id?'Opening…':ready?'Open ↗':app?.host_installed?'Bridge offline':'Unavailable'}</small></button>;
  })}</div>
  {!compact&&<small className="launcher-note">{data?.desktop?.ready?'Desktop bridge connected':'Run start.command or start.ps1 to connect desktop applications.'}</small>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
