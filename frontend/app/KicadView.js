'use client';
import { useEffect, useRef, useState } from 'react';

// KiCad schematic viewer inside DeCad: KiCanvas (MIT, bundled as public/kicanvas/kicanvas.js) renders the
// project's real .kicad_sch with KiCad's own fonts and colours: pan, zoom, select a part to see its pins and properties.
let loader = null;
const loadKicanvas = () => loader ||= new Promise((resolve, reject) => {
  if (customElements.get('kicanvas-embed')) return resolve();
  const script = document.createElement('script');
  script.type = 'module';
  script.src = '/kicanvas/kicanvas.js';
  script.onload = () => customElements.whenDefined('kicanvas-embed').then(resolve);
  script.onerror = () => { loader = null; reject(new Error('The KiCad viewer could not load.')); };
  document.head.appendChild(script);
});

export default function KicadView({ pid, name, api, rev, onError }) {
  const host = useRef(null);
  const [state, setState] = useState('loading');

  useEffect(() => {
    if (!pid || !name) return;
    let cancelled = false;
    setState('loading');
    (async () => {
      try {
        await loadKicanvas();
        const r = await fetch(`${api}/projects/${pid}/file?name=${encodeURIComponent(name)}`, { credentials: 'include' });
        if (!r.ok) throw new Error(`The schematic could not be read (${r.status}).`);
        const text = await r.text();
        if (cancelled || !host.current) return;
        const embed = document.createElement('kicanvas-embed');
        // Keep pan/zoom without a second app sidebar inside the canvas.
        embed.setAttribute('controls', 'basic');
        embed.setAttribute('controlslist', 'nodownload nooverlay');
        embed.setAttribute('theme', 'kicad');
        const source = document.createElement('kicanvas-source');
        source.setAttribute('name', name);
        source.textContent = text;
        embed.appendChild(source);
        host.current.replaceChildren(embed);
        setState('ready');
      } catch (e) {
        if (cancelled) return;
        setState('error');
        onError?.(e.message);
      }
    })();
    return () => { cancelled = true; };
  }, [pid, name, api, rev]);

  return (
    <div className="kicad-view">
      <div ref={host} className="kicad-view-host" />
      {state !== 'ready' && (
        <div className={`project-loading preview-loading ${state === 'error' ? 'has-error' : ''}`} role="status">
          <span className="loading-line" />
          <p>{state === 'error' ? 'The KiCad view could not load. Use Preview, or Edit in KiCad.' : 'Opening the schematic in KiCad view…'}</p>
        </div>
      )}
    </div>
  );
}
