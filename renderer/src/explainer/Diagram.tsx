import React from "react";
import { C } from "./theme";

// SVG diagram primitives. Both take a 0..1 progress so callers drive them from cue frames.

// A node: outlined circle that scales in; `active` adds a thick coloured ring.
export const DiagramNode: React.FC<{
  x: number;
  y: number;
  r: number;
  color: string;
  p: number;
  active?: number; // 0..1
  label?: string;
  emoji?: string;
}> = ({ x, y, r, color, p, active = 0, label, emoji }) => {
  if (p <= 0.001) return null;
  const s = Math.min(p, 1.08);
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      {active > 0 ? <circle r={r + 10 * active} fill="none" stroke={C.yellow} strokeWidth={8 * active} /> : null}
      <circle r={r} fill={color} stroke={C.ink} strokeWidth={5} />
      <circle r={r * 0.38} cx={-r * 0.25} cy={-r * 0.3} fill="#FFFFFF" opacity={0.28} />
      {emoji ? (
        <text textAnchor="middle" dominantBaseline="central" fontSize={r * 1.1}>
          {emoji}
        </text>
      ) : null}
      {label ? (
        <text y={r + 34} textAnchor="middle" fontFamily="'Baloo 2', sans-serif" fontWeight={800} fontSize={30} fill={C.ink}>
          {label}
        </text>
      ) : null}
    </g>
  );
};

// A connection that draws itself from (x1,y1) to (x2,y2); arrowhead appears as it lands.
// `bend` curves it (0 = straight).
export const ConnectionArrow: React.FC<{
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  p: number;
  color?: string;
  width?: number;
  head?: boolean;
  bend?: number;
  opacity?: number;
}> = ({ x1, y1, x2, y2, p, color = C.ink, width = 5, head = true, bend = 0, opacity = 1 }) => {
  if (p <= 0.001) return null;
  const mx = (x1 + x2) / 2 - (y2 - y1) * bend;
  const my = (y1 + y2) / 2 + (x2 - x1) * bend;
  const d = `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;
  // quadratic length approximation (chord + control polygon)/2
  const chord = Math.hypot(x2 - x1, y2 - y1);
  const poly = Math.hypot(mx - x1, my - y1) + Math.hypot(x2 - mx, y2 - my);
  const len = (chord + poly) / 2 + 1;
  const ang = Math.atan2(y2 - my, x2 - mx);
  const hs = width * 3.2;
  return (
    <g opacity={opacity}>
      <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeDasharray={len} strokeDashoffset={len * (1 - Math.min(p, 1))} />
      {head && p > 0.85 ? (
        <polygon
          points={`0,0 ${-hs},${-hs * 0.62} ${-hs},${hs * 0.62}`}
          fill={color}
          transform={`translate(${x2} ${y2}) rotate(${(ang * 180) / Math.PI}) scale(${(p - 0.85) / 0.15})`}
        />
      ) : null}
    </g>
  );
};
