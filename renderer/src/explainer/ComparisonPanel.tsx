import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, CYCLE, FONT, outline, pop, settle } from "./theme";

const Badge: React.FC<{ t: string; color: string }> = ({ t, color }) => (
  <div
    style={{
      width: 62,
      height: 62,
      background: color,
      ...outline(14, 4, 4),
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: FONT,
      fontWeight: 800,
      fontSize: 38,
      color: C.white,
    }}
  >
    {t}
  </div>
);

// Two options side by side (A vs B, or "this ≈ that" for analogies). The second card lands on
// its spoken cue and, once it's there, the first one steps back (greys out) when `winner` says
// the second is the point being made.
export const ComparisonPanel: React.FC<{
  left: string;
  right: string;
  rightAt: number;
  mode: "vs" | "approx";
  winner?: "right" | null;
}> = ({ left, right, rightAt, mode, winner = "right" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = pop(frame, 2, fps);
  const b = pop(frame, rightAt, fps);
  const dim = winner === "right" ? settle(frame, rightAt + 8, fps, 12) : 0;
  const box = (text: string, badge: string, color: string, p: number, faded: number, win: number): React.ReactNode => (
    <div
      style={{
        flex: 1,
        minHeight: 330,
        background: faded > 0 ? "#F3F4F7" : C.white,
        ...outline(28, 7, 4),
        borderColor: win > 0 ? C.green : C.ink,
        padding: "26px 26px 30px",
        display: "flex",
        flexDirection: "column",
        gap: 18,
        opacity: Math.min(1, p * 1.5) * (1 - 0.45 * faded),
        transform: `translateY(${(1 - p) * 60}px) scale(${0.94 + 0.06 * Math.min(p, 1) + 0.03 * win})`,
      }}
    >
      <Badge t={badge} color={faded > 0.5 ? C.muted : color} />
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: text.length > 30 ? 44 : 52, lineHeight: 1.1, color: C.ink }}>{text}</div>
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, width: 960 }}>
      {box(left, "A", C.muted, a, mode === "vs" ? dim : 0, 0)}
      <div
        style={{
          flexShrink: 0,
          width: 84,
          height: 84,
          borderRadius: 42,
          background: C.yellow,
          ...outline(42, 5, 4),
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: mode === "vs" ? 34 : 54,
          color: C.ink,
          transform: `scale(${pop(frame, Math.max(4, rightAt - 6), fps)})`,
        }}
      >
        {mode === "vs" ? "vs" : "≈"}
      </div>
      {box(right, "B", C.purple, b, 0, mode === "vs" ? dim : 0)}
    </div>
  );
};

// A grid of coloured dots: the "billions of parameters" picture. `fill` (0..1) reveals dots in
// reading order; size is set by cols/rows.
export const DotGrid: React.FC<{ cols: number; rows: number; dot: number; fill: number; seed?: number }> = ({ cols, rows, dot, fill, seed = 0 }) => {
  const n = cols * rows;
  const shown = Math.round(fill * n);
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, ${dot}px)`, gap: dot * 0.32 }}>
      {Array.from({ length: n }, (_, i) => (
        <div
          key={i}
          style={{
            width: dot,
            height: dot,
            borderRadius: dot / 2,
            background: CYCLE[(i * 7 + seed + Math.floor(i / cols)) % CYCLE.length],
            border: `${Math.max(2, dot * 0.1)}px solid ${C.ink}`,
            opacity: i < shown ? 1 : 0,
            transform: `scale(${i < shown ? 1 : 0.4})`,
          }}
        />
      ))}
    </div>
  );
};

// Scaled comparison: two groups of dots whose areas follow the real ratio (e.g. 1.3B vs 175B,
// clamped so the small one stays visible), each with its number and name.
export const ScaleComparison: React.FC<{ left: string; right: string; ratio: number; bigger: "left" | "right"; rightAt: number }> = ({
  left,
  right,
  ratio,
  bigger,
  rightAt,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const big = { cols: 12, rows: 9, dot: 30 };
  const k = Math.max(0.18, Math.sqrt(ratio));
  const small = { cols: Math.max(2, Math.round(big.cols * k)), rows: Math.max(2, Math.round(big.rows * k)), dot: 30 };
  const sides: { text: string; g: typeof big; at: number }[] = [
    { text: left, g: bigger === "left" ? big : small, at: 2 },
    { text: right, g: bigger === "right" ? big : small, at: rightAt },
  ];
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "center", gap: 40, width: 960 }}>
      {sides.map((s, i) => {
        const p = pop(frame, s.at, fps);
        const fill = Math.min(1, Math.max(0, (frame - s.at) / 16));
        const isBig = s.g === big;
        return (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, opacity: Math.min(1, p * 1.5), transform: `scale(${0.9 + 0.1 * Math.min(p, 1)})` }}>
            <div style={{ background: C.white, ...outline(22, 6, 4), padding: 18 }}>
              <DotGrid {...s.g} fill={fill} seed={i * 3} />
            </div>
            <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 50, color: isBig ? C.pink : C.green, lineHeight: 1, textAlign: "center", maxWidth: isBig ? 560 : 360 }}>
              {s.text}
            </div>
          </div>
        );
      })}
    </div>
  );
};
