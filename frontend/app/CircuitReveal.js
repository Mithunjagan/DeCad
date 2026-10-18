'use client';
import { useMemo } from 'react';

const COLS = 10;
const ROWS = 7;
const STEP_MS = 40;      // gentle stagger so pieces overlap and never blink
const BUILD_MS = COLS * ROWS * STEP_MS;

// Deterministic shuffle so the assembly order is varied but stable per image.
function order(seed) {
  let s = seed * 9301 + 49297;
  const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  const idx = Array.from({ length: COLS * ROWS }, (_, i) => i);
  for (let i = idx.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx;
}

/**
 * Builds the schematic from its own pieces: each tile is a real crop of the image,
 * fades in over the previous full image (`prev`), so the hand-off is seamless.
 * Remount (change `key`) to replay.
 */
export default function CircuitReveal({ src, prev = null, seed = 1, cycleMs = 9000 }) {
  const rank = useMemo(() => {
    const o = order(seed), r = new Array(o.length);
    o.forEach((cell, n) => { r[cell] = n; });
    return r;
  }, [seed]);

  const tiles = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const i = r * COLS + c;
      tiles.push(
        <div key={i} className="tile"
          style={{
            left: `${(c / COLS) * 100}%`, top: `${(r / ROWS) * 100}%`,
            width: `${100 / COLS}%`, height: `${100 / ROWS}%`,
            animationDelay: `${rank[i] * STEP_MS}ms`,
          }}>
          <img src={src} alt=""
            style={{
              width: `${COLS * 100}%`, height: `${ROWS * 100}%`,
              left: `${-c * 100}%`, top: `${-r * 100}%`,
            }} />
        </div>
      );
    }
  }

  return (
    <div className="reveal" style={{ '--cycle': `${cycleMs}ms`, '--build': `${BUILD_MS}ms` }}>
      <img className="base" src={prev || src} alt="" style={{ opacity: prev ? 1 : 0.25, filter: 'contrast(1.1) brightness(0.7) blur(1px)' }} />
      {tiles}
    </div>
  );
}
