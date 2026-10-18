'use client';
import {useEffect,useRef} from 'react';
export default function WorkbenchDialog({title,onClose,busy,children,className=''}){
 const root=useRef(null),close=useRef(onClose);close.current=onClose;
 useEffect(()=>{
  const previous=document.activeElement;root.current?.focus();
  return ()=>previous?.focus?.();
 },[]);
 const key=e=>{
  if(e.key==='Escape'&&!busy){e.preventDefault();close.current();}
  if(e.key==='Tab'){
   const items=[...root.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary')].filter(x=>x.getClientRects().length);
   const first=items[0],last=items.at(-1);
   if(!first){e.preventDefault();return;}
   if(e.shiftKey&&(document.activeElement===first||document.activeElement===root.current)){e.preventDefault();last.focus();}
   else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
  }
 };
 return <div className="modal-backdrop"><section ref={root} tabIndex={-1} onKeyDown={key} role="dialog" aria-modal="true" aria-label={title} className={`modal workflow-dialog ${className}`}><header className="workflow-heading"><h2>{title}</h2><button disabled={busy} aria-label="Close dialog" onClick={onClose}>Close</button></header>{children}</section></div>;
}
