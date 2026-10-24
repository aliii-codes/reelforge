import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { StatData } from "../types";
import { DotGrid } from "./ComparisonPanel";
import { Pill } from "./KeywordLabel";
import { C, card, FONT, pop } from "./theme";

const fmt = (v: number, d: number) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

// The number counts up exactly when it is spoken, lands with a small punch, and its label
// underlines itself. Big quantities (billions, x-times) also fill a dot grid as they count.
export const StatCallout: React.FC<{ stat: StatData; title: string; at: number; dots: boolean; emoji?: string }> = ({ stat, title, at, dots, emoji }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = pop(frame, 0, fps);
  const count = interpolate(frame - at, [0, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: (t) => 1 - Math.pow(1 - t, 3) });
  const land = pop(frame, at + 16, fps);
  const value = fmt(stat.value * count, stat.decimals);
  const text = `${stat.prefix}${value}`;
  const size = Math.min(230, 1500 / Math.max(3, text.length + stat.suffix.length));
  return (
    <div
      style={{
        width: 940,
        ...card(34),
        padding: "34px 40px 36px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
        opacity: Math.min(1, enter * 1.5),
        transform: `translateY(${(1 - enter) * 50}px)`,
      }}
    >
      {title ? <Pill text={`${title}${emoji ? ` ${emoji}` : ""}`} color={C.yellow} size={38} rotate={-2} /> : null}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          fontFamily: FONT,
          fontWeight: 800,
          lineHeight: 1,
          marginTop: 18,
          transform: `scale(${1 + 0.08 * Math.sin(Math.min(1, Math.max(0, land)) * Math.PI)})`,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span style={{ fontSize: size, color: C.purple }}>{frame >= at ? text : `${stat.prefix}${fmt(0, stat.decimals)}`}</span>
        {stat.suffix ? <span style={{ fontSize: size * 0.55, color: C.orange, marginLeft: 8 }}>{stat.suffix.trim()}</span> : null}
      </div>
      <div style={{ height: 10, width: 520 * count, background: C.orange, borderRadius: 5, border: `3px solid ${C.ink}`, opacity: count > 0 ? 1 : 0 }} />
      {stat.label ? (
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 52, color: C.ink, textAlign: "center", lineHeight: 1.1, marginTop: 12, opacity: Math.min(1, land * 1.4) }}>
          {stat.label}
        </div>
      ) : null}
      {dots ? (
        <div style={{ marginTop: 18 }}>
          <DotGrid cols={16} rows={4} dot={30} fill={count} />
        </div>
      ) : null}
    </div>
  );
};
