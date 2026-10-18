'use client';
import {useEffect, useRef, useState} from 'react';
import WorkbenchDialog from './WorkbenchDialog';
import {Icon} from './StudioElements';

export default function CommandPalette({actions, onClose}) {
  const [query,setQuery]=useState('');
  const [selected,setSelected]=useState(0);
  const input=useRef(null);
  const results=actions.filter(a=>`${a.label} ${a.group}`.toLowerCase().includes(query.toLowerCase()));
  useEffect(()=>{input.current?.focus();},[]);
  useEffect(()=>{document.getElementById(`command-${selected}`)?.scrollIntoView({block:'nearest'});},[selected]);
  const run=action=>{if(!action)return;onClose();action.run();};
  return <WorkbenchDialog title="Find your next action" onClose={onClose}><div className="command-search"><Icon name="search"/><input ref={input} aria-label="Search commands and projects" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="command-results" aria-activedescendant={results.length ? `command-${selected}` : undefined} placeholder="Search commands, views, projects…" value={query} onChange={e=>{setQuery(e.target.value);setSelected(0);}} onKeyDown={e=>{if(e.key==='ArrowDown'){e.preventDefault();setSelected(i=>Math.min(i+1,results.length-1));}if(e.key==='ArrowUp'){e.preventDefault();setSelected(i=>Math.max(0,i-1));}if(e.key==='Enter'){e.preventDefault();run(results[selected]);}}}/><kbd>esc</kbd></div><div className="command-results" id="command-results" role="listbox" aria-label="Commands">{results.map((action,i)=><button id={`command-${i}`} role="option" aria-selected={selected===i} key={`${action.group}-${action.label}`} className={selected===i?'selected':''} onMouseEnter={()=>setSelected(i)} onClick={()=>run(action)}><Icon name={action.icon || 'arrow'}/><span>{action.label}<small>{action.group}</small></span><span className="command-enter">↵</span></button>)}{!results.length&&<p className="command-no-results">No matching commands. Try “schematic” or “new project”.</p>}</div><div className="command-help"><span>↑ ↓ to navigate</span><span>↵ to select</span><span>esc to close</span></div></WorkbenchDialog>;
}
