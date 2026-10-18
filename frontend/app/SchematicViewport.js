'use client';
import {useEffect,useRef,useState} from 'react';
export default function SchematicViewport({api,project,revision,zoom,onZoom,selected,grid=true}){
 const [sheet,setSheet]=useState(false),[offset,setOffset]=useState({x:0,y:0}),[cursor,setCursor]=useState({x:0,y:0}),[error,setError]=useState(false);
 const drag=useRef(null),root=useRef(null);
 useEffect(()=>{setOffset({x:0,y:0});setError(false);},[project,revision]);
 useEffect(()=>{if(zoom===1)setOffset({x:0,y:0});},[zoom]);
 const wheel=e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();onZoom(Math.max(.4,Math.min(8,zoom*(e.deltaY>0?.9:1.1))));}};
 useEffect(()=>{const el=root.current;el?.addEventListener('wheel',wheel,{passive:false});return()=>el?.removeEventListener('wheel',wheel);},[zoom]);
 return <div className="schematic-viewport" style={grid?undefined:{backgroundImage:'none'}} ref={root} onPointerDown={e=>{if(e.button===1||e.altKey){e.preventDefault();drag.current={x:e.clientX-offset.x,y:e.clientY-offset.y};e.currentTarget.setPointerCapture(e.pointerId);}}} onPointerMove={e=>{const r=e.currentTarget.getBoundingClientRect();setCursor({x:Math.round(e.clientX-r.left),y:Math.round(e.clientY-r.top)});if(drag.current)setOffset({x:e.clientX-drag.current.x,y:e.clientY-drag.current.y});}} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null}>
  <div className="canvas-document-label"><span>SCHEMATIC / {project}</span><label><input type="checkbox" checked={sheet} onChange={e=>{setSheet(e.target.checked);onZoom(1);setOffset({x:0,y:0});}}/>Full sheet</label></div>
  <div className="schematic-artboard"><img draggable={false} alt={`${project} native schematic with physical pin connections`} src={`${api}/projects/${project}/preview.svg?content=${!sheet}&v=${revision}&highlight=${encodeURIComponent(selected||'')}`} onLoad={()=>setError(false)} onError={()=>setError(true)} style={{transform:`translate(${offset.x}px,${offset.y}px) scale(${zoom})`}}/></div>
  {error&&<div role="alert" className="canvas-error">Unable to load native schematic. Check Output and refresh.</div>}
  <div className="canvas-navigation"><button title="Zoom out" onClick={()=>onZoom(Math.max(.4,zoom/1.2))}>−</button><button title="Fit circuit" onClick={()=>{onZoom(1);setOffset({x:0,y:0});}}>Fit</button><span>{Math.round(zoom*100)}%</span><button title="Zoom in" onClick={()=>onZoom(Math.min(8,zoom*1.2))}>+</button></div>
  <div className="canvas-readout"><span>X {cursor.x} · Y {cursor.y} px</span><span>{selected?`Selected ${selected}`:'Middle drag: pan · Ctrl/⌘ scroll: zoom'}</span></div>
 </div>;
}
