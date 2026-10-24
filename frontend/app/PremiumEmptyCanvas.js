'use client';
import {useEffect,useRef} from 'react';
import DeCadMark from './DeCadMark';
import './premium-empty.css';

function Icon({name,size=18,...props}){
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{name==='arrow'?<path d="M5 12h14m-6-6 6 6-6 6"/>:name==='upload'?<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>:<path d="M12 5v14M5 12h14"/>}</svg>;
}

function CircuitStudy(){
 const signal='M78 132H198l8-10 12 20 12-20 12 20 12-20 12 20 8-10H610';
 return <svg className="design-study" viewBox="0 0 760 324" fill="none" role="img" aria-label="Illustrative RC low-pass filter: a zero to five volt pulse source through a ten kiloohm resistor, with a ten nanofarad capacitor to ground and a wired output">
  <g className="study-guides" stroke="currentColor" strokeWidth=".6" strokeDasharray="2 7"><path d="M36 92H724M36 264H724M410 70V302M78 70V290"/></g>
  <g className="study-annotation" fill="currentColor"><text x="38" y="38">01 / ANALOG SIGNAL PATH</text><text x="722" y="38" textAnchor="end">RC · LOW-PASS</text></g>
  <g className="study-wire" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
   <path d={signal}/><path d="M78 132v59m0 44v29h332V188m0-56v46m-18 0h36m-36 10h36M410 264v18m-18 0h36m-29 7h22m-15 7h8"/>
   <circle cx="78" cy="213" r="22"/><path d="M65 219h7v-13h12v13h7"/>
   <circle cx="610" cy="132" r="4" fill="var(--panel)"/>
  </g>
  <path className="study-signal" d={signal} stroke="currentColor" strokeWidth="2.4" pathLength="1" strokeLinecap="round"/>
  <g className="study-node" fill="currentColor"><circle cx="410" cy="132" r="3.5"/><circle cx="410" cy="264" r="3"/><circle cx="78" cy="132" r="3"/></g>
  <g className="study-label" fill="currentColor"><text x="78" y="111" textAnchor="middle">VIN</text><text x="236" y="104" textAnchor="middle">R1</text><text x="438" y="179">C1</text><text x="612" y="111" textAnchor="end">VOUT</text></g>
  <g className="study-value" fill="currentColor"><text x="236" y="166" textAnchor="middle">10 kΩ</text><text x="438" y="197">10 nF</text><text x="42" y="216" textAnchor="end">0–5 V</text><text x="441" y="284">GND</text></g>
  <g className="study-scope"><rect x="545" y="190" width="169" height="75" rx="6" fill="var(--panel)" stroke="var(--line)"/>
   <path d="M559 243h140m-140-22h140" stroke="var(--line)" strokeWidth=".6"/>
   <path d="M559 243h19v-22h49v22h50v-22h22" stroke="var(--muted)" strokeWidth="1" opacity=".3"/>
   <path className="study-wave" d="M559 243h19c0-16 15-22 49-22 0 16 16 22 50 22 0-14 10-21 22-22" stroke="var(--accent)" strokeWidth="1.6"/>
   <text className="study-scope-label" x="558" y="207" fill="var(--muted)">PULSE RESPONSE</text>
  </g>
  <text className="study-footnote" x="38" y="311" fill="currentColor">f<tspan baselineShift="sub" fontSize="5">c</tspan> = 1 / (2πRC) ≈ 1.59 kHz</text>
  <text className="study-footnote" x="722" y="311" fill="currentColor" textAnchor="end">ILLUSTRATION · NOT A SIMULATION</text>
 </svg>;
}

export default function PremiumEmptyCanvas({hasProject,onCreate,onImport,onPrompt}){
 const surface=useRef(null),frame=useRef(0),motion=useRef(false);
 useEffect(()=>{const query=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>{motion.current=!query.matches;if(query.matches){cancelAnimationFrame(frame.current);surface.current?.style.setProperty('--drift-x','0px');surface.current?.style.setProperty('--drift-y','0px');}};update();query.addEventListener('change',update);
  return()=>{query.removeEventListener('change',update);cancelAnimationFrame(frame.current);};},[]);
 const move=e=>{
  if(!motion.current||e.pointerType!=='mouse')return;
  const bounds=e.currentTarget.getBoundingClientRect(),x=(e.clientX-bounds.left)/bounds.width-.5,y=(e.clientY-bounds.top)/bounds.height-.5;
  cancelAnimationFrame(frame.current);frame.current=requestAnimationFrame(()=>{const el=surface.current;if(!el||!motion.current)return;el.style.setProperty('--drift-x',`${x*7}px`);el.style.setProperty('--drift-y',`${y*5}px`);});
 };
 const reset=()=>{cancelAnimationFrame(frame.current);const el=surface.current;if(el){el.style.setProperty('--drift-x','0px');el.style.setProperty('--drift-y','0px');}};
 return <div ref={surface} className="studio-empty premium-empty" onPointerMove={move} onPointerLeave={reset}>
  <div className="empty-atmosphere" aria-hidden="true"/>
  <div className="empty-composition">
   <div className="empty-signature hero-reveal" style={{'--reveal-delay':'0ms'}}><DeCadMark size={42}/><span>DeCad<span className="brand-period">.</span><small>THE CIRCUIT DESIGN WORKBENCH</small></span></div>
   <div className="eyebrow hero-reveal" style={{'--reveal-delay':'70ms'}}><span/>A CLEAR PATH FROM IDEA TO CIRCUIT<span/></div>
   <h2 className="hero-reveal" style={{'--reveal-delay':'130ms'}}>Every connection.<br/><em>Considered.</em></h2>
   <p className="hero-reveal" style={{'--reveal-delay':'200ms'}}>{hasProject?'Bring your schematic into focus. Inspect the details. Make the next connection.':'Your next design begins with a blank sheet and a better way to build.'}</p>
   <div className="empty-actions hero-reveal" style={{'--reveal-delay':'260ms'}}>
    <button className="studio-primary" onClick={hasProject?onImport:onCreate}><Icon name={hasProject?'upload':'plus'} size={17}/>{hasProject?'Import a schematic':'Create your first project'}<Icon className="empty-cta-arrow" name="arrow" size={17}/></button>
    {hasProject&&<button className="studio-secondary" onClick={()=>onPrompt('create a voltage divider')}>Start with a voltage divider <Icon name="arrow" size={15}/></button>}
   </div>
   <div className="empty-study hero-reveal" style={{'--reveal-delay':'340ms'}}><div className="study-registration" aria-hidden="true"><span/><span/><span/><span/></div><CircuitStudy/></div>
   <div className="empty-capabilities hero-reveal" style={{'--reveal-delay':'410ms'}}><span>Native KiCad</span><i/><span>Local history</span><i/><span>SPICE simulation</span></div>
  </div>
 </div>;
}
