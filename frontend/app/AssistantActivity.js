'use client';
import {useEffect, useState} from 'react';
import {ocrRuntimeLabel} from './ocr-runtime.mjs';

const phases = {
  upload: ['Reading your attachment', 'Sending the source to your local workspace.'],
  recognize: ['Reading the schematic', 'Analyzing components, text and connections.'],
  design: ['Working on your circuit', 'Your request is running. Changes appear when ready.'],
  plan: ['Preparing your design review', 'The model is considering your circuit request.'],
  apply: ['Applying your reviewed design', 'Writing the schematic and checking the result.'],
  export: ['Preparing your OrCAD design', 'Generating the design and verifying it in Capture.'],
};

export default function AssistantActivity({phase = 'design', runtime}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [phase]);
  const [title, detail] = phases[phase] || phases.design;
  return <div className="assistant-activity" data-phase={phase}>
    <div className="activity-circuit" aria-hidden="true">
      <svg viewBox="0 0 280 88" fill="none">
        <g className="activity-traces">
          <path d="M10 26h52l18 18h38M16 66h52l12-12h38M162 34h34l18-18h54M162 54h36l16 16h54"/>
          <path d="M104 10v12l24 12M142 64v14h36"/>
        </g>
        <g className="activity-flow">
          <path d="M10 26h52l18 18h38M16 66h52l12-12h38M162 34h34l18-18h54M162 54h36l16 16h54"/>
        </g>
        <g className="activity-nodes">
          <circle cx="10" cy="26" r="3"/><circle cx="16" cy="66" r="3"/>
          <circle cx="268" cy="16" r="3"/><circle cx="268" cy="70" r="3"/>
        </g>
        <rect className="activity-chip" x="118" y="22" width="44" height="44" rx="10"/>
        <path className="activity-core" d="m140 31 3.5 9.5L153 44l-9.5 3.5L140 57l-3.5-9.5L127 44l9.5-3.5Z"/>
      </svg>
      <span className="activity-live">IN PROGRESS</span>
    </div>
    <div className="activity-copy" role="status"><strong>{title}<span className="activity-ellipsis" aria-hidden="true">…</span></strong><p>{detail}</p>{phase==='recognize'&&<p className="activity-runtime">{ocrRuntimeLabel(runtime,true)}<br/><small>Text models can use the GPU; image preparation and wire tracing also use the CPU.</small></p>}</div>
    <div className="activity-footer" aria-hidden="true"><span className="activity-dot"/>Design assistant<span>{elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`}</span></div>
  </div>;
}
