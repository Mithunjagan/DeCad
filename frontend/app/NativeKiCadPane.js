'use client';
import {useEffect,useRef,useState} from 'react';

export default function NativeKiCadPane({pid,api,onError}){
 const root=useRef(null),[state,setState]=useState('Opening native KiCad…'),[retry,setRetry]=useState(0);
 useEffect(()=>{
  const bridge=window.__DECAD_DESKTOP__;if(!bridge)return;
  let cancelled=false,frame=0;
  const report=()=>{
   cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
    if(!root.current)return;const b=root.current.getBoundingClientRect();
    bridge.notify('bounds',{x:b.x,y:b.y,width:b.width,height:b.height,viewport:innerWidth,
      visible:document.visibilityState==='visible'&&b.width>0&&b.height>0&&!document.querySelector('[role="dialog"],.modal-backdrop')});
   });
  };
  const resize=new ResizeObserver(report);resize.observe(root.current);
  const closed=()=>setState('The KiCad editor is closed. Reopen it to continue editing.');
  window.addEventListener('decad-native-closed',closed);
  const observer=new MutationObserver(report);observer.observe(document.body,{childList:true,subtree:true});
  window.addEventListener('resize',report);window.addEventListener('scroll',report,true);document.addEventListener('visibilitychange',report);report();
  (async()=>{
   try{
    const response=await fetch(`${api}/projects/${encodeURIComponent(pid)}/kicad/path`,{credentials:'include'});
    if(!response.ok)throw Error('Could not open this project’s schematic.');
    const {path}=await response.json();if(cancelled)return;
    await bridge.request('open',{path});if(!cancelled){setState('');report();}
   }catch(error){if(!cancelled){setState(error.message);onError?.(error.message);}}
  })();
  return ()=>{cancelled=true;cancelAnimationFrame(frame);resize.disconnect();observer.disconnect();window.removeEventListener('decad-native-closed',closed);window.removeEventListener('resize',report);window.removeEventListener('scroll',report,true);document.removeEventListener('visibilitychange',report);bridge.notify('bounds',{visible:false});};
 },[pid,api,retry]);
 return <div ref={root} className="native-kicad-pane" aria-label="Native KiCad schematic editor">
   <div className="project-loading" role={state?'status':undefined}>{state&&<p>{state}</p>}<button className="studio-secondary" onClick={()=>{setState('Opening native KiCad…');setRetry(n=>n+1);}}>Reopen editor</button></div>
 </div>;
}
