'use client';
import {useEffect,useRef,useState} from 'react';
import {measuredPercent,percentText,memoryText,primaryGpu} from './system-metrics.mjs';
import styles from './SystemMonitor.module.css';

function Metric({name,value,note}){
 const percent=measuredPercent(value);
 return <div className={styles.metric}><span>{name}</span><output aria-label={`${name} usage`}>{percentText(percent)}</output>
  <div className={styles.track} aria-hidden="true">{percent!==null&&<i style={{width:`${percent}%`}}/>}</div><small title={note}>{note}</small></div>;
}

export default function SystemMonitor(){
 const [sample,setSample]=useState(null),[error,setError]=useState(''),[paused,setPaused]=useState(false),[expanded,setExpanded]=useState(false);
 const retry=useRef(null);
 useEffect(()=>{
  let stopped=false,timer,controller,inFlight=false;
  const update=async()=>{
   if(stopped||document.hidden||inFlight)return;
   inFlight=true;controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),8000);
   try{
    const response=await fetch('/api/system/stats',{credentials:'include',cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('Live readings unavailable');
    const next=await response.json();if(!stopped){setSample(next);setError('');}
   }catch{if(!stopped&&!document.hidden)setError('Connection interrupted');}
   finally{clearTimeout(deadline);inFlight=false;if(!stopped&&!document.hidden)timer=setTimeout(update,2000);}
  };
  const visibility=()=>{setPaused(document.hidden);clearTimeout(timer);if(document.hidden)controller?.abort();else update();};
  retry.current=update;visibility();document.addEventListener('visibilitychange',visibility);
  return ()=>{stopped=true;clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visibility);retry.current=null;};
 },[]);
 const gpu=primaryGpu(sample?.gpus),stale=!!error||(!!sample&&Date.now()-sample.sampled_at*1000>8000);
 const label=paused?'Paused':error?(sample?'Last reading':'Offline'):!sample?'Connecting…':stale?'Last reading':'Live · ~2 s';
 return <section className={styles.monitor} aria-label="System resources" data-stale={stale||paused}>
  <div className={styles.heading}><strong>System resources</strong><span className={styles.live}><i aria-hidden="true"/>{label}</span>
   <button type="button" onClick={()=>setExpanded(v=>!v)} aria-expanded={expanded} aria-controls="system-resource-details">{expanded?'Less':'Details'}</button></div>
  <div className={styles.grid}>
   <Metric name="CPU" value={sample?.cpu?.percent} note={sample?.cpu?.percent===null&&!sample?.errors?.cpu?'Sampling…':sample?.cpu?.logical_cores?`${sample.cpu.logical_cores} logical CPUs`:'Host CPU'}/>
   <Metric name="GPU" value={gpu?.utilization_percent} note={gpu?'NVIDIA':sample?'Unavailable':'Detecting…'}/>
   <Metric name="RAM" value={sample?.memory?.percent} note={sample?.memory?memoryText(sample.memory.used_bytes,sample.memory.total_bytes):'Physical memory'}/>
  </div>
  {expanded&&<div id="system-resource-details" className={styles.details}>
   <p>Whole computer · all processes{sample?.platform?` · ${sample.platform}`:''}</p>
   {(sample?.gpus||[]).map(item=><div className={styles.gpu} key={item.uuid||item.id}><strong>{item.name}</strong>
    <span>VRAM {memoryText(item.memory_used_bytes,item.memory_total_bytes)}</span>
    <span>{measuredPercent(item.utilization_percent)!==null?`${percentText(item.utilization_percent)} utilization`:'Utilization unavailable'}{Number.isFinite(item.temperature_celsius)?` · ${Math.round(item.temperature_celsius)} °C`:''}</span></div>)}
   {sample?.memory&&<p>Available RAM: {(sample.memory.available_bytes/2**30).toFixed(1)} GiB</p>}
   {Object.entries(sample?.errors||{}).map(([name,message])=><p key={name}>{message}</p>)}
   <p>CPU and RAM come from the OS; GPU data comes from NVIDIA. Graphics load and OCR compute can vary independently.</p>
   {sample&&<time dateTime={new Date(sample.sampled_at*1000).toISOString()}>Sampled {new Date(sample.sampled_at*1000).toLocaleTimeString()}</time>}
  </div>}
  {error&&<div className={styles.retry}><span>{error}. Cached values are marked above.</span><button onClick={()=>retry.current?.()}>Retry</button></div>}
 </section>;
}
