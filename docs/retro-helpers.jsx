/* Retro Price Watch — helpers + small components */
const { useState, useMemo, useEffect, useRef } = React;

const STORE_BY_ID = Object.fromEntries(window.RETRO_STORES.map(s => [s.id, s]));
const fmt = n => "$" + n.toFixed(2);
const fmtPct = p => (p >= 0 ? "+" : "") + p.toFixed(1) + "%";

/* deterministic RNG so a row's history is stable across renders */
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* build an 8-point price history ending at current price */
function genHistory(item) {
  const rnd = mulberry32(item.id * 99 + 7);
  const pts = 8;
  const end = item.price;
  const prior = item.prev != null ? item.prev : item.price;
  const arr = new Array(pts);
  arr[pts - 1] = end;
  arr[pts - 2] = prior;
  // walk backwards from prior with gentle drift
  let v = prior;
  for (let i = pts - 3; i >= 0; i--) {
    const drift = (rnd() - 0.45) * prior * 0.12;
    v = Math.max(end * 0.55, v + drift);
    arr[i] = Math.round(v * 100) / 100;
  }
  return arr;
}

function changeOf(item) {
  if (item.prev == null) return { kind: "new" };
  const diff = +(item.price - item.prev).toFixed(2);
  if (Math.abs(diff) < 0.01) return { kind: "flat" };
  const pct = (diff / item.prev) * 100;
  return { kind: diff < 0 ? "down" : "up", diff, pct };
}

/* ---- Sparkline (SVG) ---- */
function Sparkline({ data, w = 260, h = 60 }) {
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const stepX = w / (data.length - 1);
  const y = v => h - 6 - ((v - min) / span) * (h - 12);
  const pts = data.map((v, i) => [i * stepX, y(v)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = line + ` L ${w} ${h} L 0 ${h} Z`;
  const up = data[data.length - 1] >= data[0];
  const col = up ? "var(--red)" : "var(--green)";
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={"sg" + w} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={col} stopOpacity="0.28" />
          <stop offset="100%" stopColor={col} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#sg${w})`} />
      <path d={line} fill="none" stroke={col} strokeWidth="1.6"
            style={{ filter: up ? "none" : "drop-shadow(0 0 4px var(--accent-glow))" }} />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 3 : 1.6}
                fill={i === pts.length - 1 ? col : "var(--ink-faint)"} />
      ))}
      <circle cx={last[0]} cy={last[1]} r="3" fill={col} />
    </svg>
  );
}

window.RPW = { STORE_BY_ID, fmt, fmtPct, genHistory, changeOf, Sparkline };
