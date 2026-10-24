'use client';
import DeCadMark from './DeCadMark';
import PremiumEmptyCanvas from './PremiumEmptyCanvas';

export function Icon({name, size = 18, ...props}) {
  const paths = {
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    circuit: <><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 3v4m6-4v4M9 17v4m6-4v4M3 9h4m-4 6h4m10-6h4m-4 6h4"/></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></>,
    folder: <path d="M3 7V5h6l2 2h10v13H3Z"/>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/></>,
    panels: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16m8-16v16"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    wave: <path d="M2 12h3l3-8 4 16 4-16 3 8h3"/>,
    shield: <><path d="m12 3 8 3v6c0 4-8 9-8 9s-8-5-8-9V6Z"/><path d="m8 12 3 3 5-6"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.circuit}</svg>;
}

export function Brand() {
  return <span className="studio-brand"><span className="brand-symbol"><DeCadMark className="decad-brand-mark" size={35}/></span><span>DeCad<span className="brand-period">.</span></span></span>;
}

// A decorative circuit drawing. It is deliberately labelled as an illustration,
// and is never used in place of a project's native schematic preview.
export function CircuitArtwork({compact = false}) {
  return <svg className={`circuit-artwork ${compact ? 'compact' : ''}`} viewBox="0 0 620 360" fill="none" role="img" aria-label="Illustration of an RC circuit">
    <defs><pattern id={compact ? 'grid-small' : 'grid-large'} width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.8" fill="currentColor" opacity=".18"/></pattern></defs>
    <rect width="620" height="360" fill={`url(#${compact ? 'grid-small' : 'grid-large'})`}/>
    <g className="art-wires" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M100 178v-72h112m76 0h132v60m0 28v70H100v-50m320-108h92v72m0 38v48h-92"/>
      <path d="m212 106 7-12 12 24 12-24 12 24 12-24 12 24 9-12"/>
      <circle cx="100" cy="196" r="18"/><path d="M93 190h14m-7-7v14m-6 9h12M398 166h44m-44 13h44m-22 0v15M493 178l38 19-38 19Zm38 0v38M310 264v18m-15 0h30m-24 6h18m-12 6h6"/>
      <circle cx="420" cy="106" r="3" fill="currentColor"/><circle cx="420" cy="264" r="3" fill="currentColor"/>
    </g>
    <g fill="currentColor" fontFamily="ui-monospace, monospace" fontSize="11" opacity=".6"><text x="229" y="76">R1 · 10kΩ</text><text x="450" y="173">C1</text><text x="450" y="190">100nF</text><text x="49" y="200">5V</text><text x="103" y="89">VIN</text><text x="423" y="89">VOUT</text><text x="330" y="292">GND</text></g>
    <g className="art-signal" stroke="currentColor" strokeWidth="2"><path d="M100 106h72"/><circle cx="172" cy="106" r="3" fill="currentColor"/></g>
  </svg>;
}

export function WelcomeScreen({localAvailable, onLocal, onGithub, busy, status}) {
  return <main className="studio-welcome">
    <nav className="welcome-nav" aria-label="Welcome"><Brand/><span className="welcome-nav-label">THE CIRCUIT DESIGN STUDIO</span><span className="local-badge"><span/>Built for your machine</span></nav>
    <div className="welcome-layout">
      <section className="welcome-copy"><div className="eyebrow"><span className="eyebrow-line"/> LESS FRICTION. MORE INVENTION.</div>
        <h1>Great circuits.<br/>Start with<br/><em>an idea.</em></h1>
        <p>A focused space to turn circuit ideas into working designs. Create, inspect, simulate, and export—all in one local workspace.</p>
        <div className="welcome-actions"><button className="studio-primary" disabled={!localAvailable || busy} onClick={onLocal}>{busy ? 'Opening workspace…' : 'Open local workspace'}<Icon name="arrow"/></button><button className="welcome-github" onClick={onGithub}>Continue with GitHub <span>↗</span></button></div>
        <div className="welcome-assurance"><Icon name="shield" size={15}/> Local files. Native tools. Your workflow.</div>
        {status !== 'Ready' && <p className="welcome-connection" role="status">{status}</p>}
        {!localAvailable && <p className="welcome-connection">Waiting for the local service. Start the DeCad launcher to open your workspace.</p>}
      </section>
      <section className="welcome-visual" aria-label="Design workflow preview"><div className="visual-kicker"><span>IDEA → SCHEMATIC → SIMULATION</span><span>01 / STUDIO</span></div>
        <div className="circuit-specimen"><div className="specimen-heading"><span><span className="specimen-dot"/> RC low-pass filter</span><span>CIRCUIT STUDY 001</span></div><CircuitArtwork/><div className="specimen-bottom"><span>ILLUSTRATIVE SCHEMATIC</span><span>R · C · V</span></div></div>
        <div className="wave-specimen"><div><Icon name="wave"/><span>See the signal.<small>Transient analysis, in your workspace.</small></span></div><svg viewBox="0 0 240 60" aria-hidden="true"><path d="M0 48H30V12H90V48H150V12H210V48H240" fill="none" stroke="currentColor" opacity=".22"/><path d="M0 48H30C42 48 48 12 90 12c12 0 18 36 60 36 12 0 18-36 60-36 12 0 18 36 30 36" fill="none" stroke="currentColor" strokeWidth="2"/></svg></div>
        <div className="visual-note"><span className="note-line"/> From the first connection to the final detail.</div>
      </section>
    </div>
    <footer className="welcome-bottom"><span>ENGINEERED FOR YOUR NEXT IDEA.</span><div><span>01 <b>Design with intent</b></span><span>02 <b>Validate every connection</b></span><span>03 <b>Export to your tools</b></span></div><span>DeCad © {new Date().getFullYear()}</span></footer>
  </main>;
}

export function EmptyCanvas({hasProject, onCreate, onImport, onPrompt}) {
  return <PremiumEmptyCanvas hasProject={hasProject} onCreate={onCreate} onImport={onImport} onPrompt={onPrompt}/>;
}
