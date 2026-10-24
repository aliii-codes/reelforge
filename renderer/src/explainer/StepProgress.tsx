import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { ConnectionArrow } from "./Diagram";
import { C, draw, FONT, outline, pop } from "./theme";

// Chapter tabs that persist across beats: done (white, ticked), active (orange), locked (grey,
// dashed). They give the whole video a sense of "where are we" like a progress bar with names.
export const ChapterTabs: React.FC<{ chapters: string[]; active: number; activeSince: number; width?: number }> = ({
  chapters,
  active,
  activeSince,
  width = 960,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = chapters.length;
  const fs = n >= 4 ? 28 : 34;
  const p = pop(frame, activeSince, fps);
  return (
    <div style={{ display: "flex", gap: 16, width }}>
      {chapters.map((c, i) => {
        const done = i < active;
        const on = i === active;
        const style: React.CSSProperties = on
          ? { background: C.orange, ...outline(22, 6, 4), transform: `scale(${0.9 + 0.1 * Math.min(p, 1.05)})` }
          : done
            ? { background: C.white, ...outline(22, 6, 4) }
            : { background: C.soft, border: `4px dashed ${C.ink}`, borderRadius: 22, color: C.muted };
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: 82,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontFamily: FONT,
              fontWeight: 800,
              fontSize: fs,
              color: C.ink,
              whiteSpace: "nowrap",
              overflow: "hidden",
              ...style,
            }}
          >
            {done ? <span style={{ color: C.green }}>✓</span> : on ? null : <span style={{ fontSize: fs * 0.8 }}>🔒</span>}
            <span style={{ color: on || done ? C.ink : C.muted }}>{on || done ? c : `${i + 1}`}</span>
          </div>
        );
      })}
    </div>
  );
};

// A vertical process: each step lands on the word that names it, connected by drawn arrows.
// The newest step is highlighted; earlier ones get a green tick.
export const StepList: React.FC<{ items: string[]; at: number[]; width?: number; rowHeight?: number; gap?: number }> = ({
  items,
  at,
  width = 900,
  rowHeight = 112,
  gap = 46,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const active = at.reduce((acc, f, i) => (frame >= f ? i : acc), -1);
  return (
    <div style={{ position: "relative", width, display: "flex", flexDirection: "column", gap }}>
      <svg width={width} height={items.length * (rowHeight + gap)} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        {items.slice(1).map((_, i) => {
          const y1 = (i + 1) * rowHeight + i * gap + 6;
          return <ConnectionArrow key={i} x1={86} y1={y1} x2={86} y2={y1 + gap - 10} p={draw(frame, at[i + 1] - 6, 8)} width={6} />;
        })}
      </svg>
      {items.map((it, i) => {
        const p = pop(frame, at[i], fps);
        const on = i === active;
        const done = i < active;
        return (
          <div
            key={i}
            style={{
              height: rowHeight,
              display: "flex",
              alignItems: "center",
              gap: 26,
              padding: "0 30px",
              background: on ? "#FFF3EA" : C.white,
              ...outline(26, on ? 7 : 5, 4),
              opacity: Math.min(1, p * 1.5),
              transform: `translateX(${(1 - p) * -60}px) scale(${on ? 1.02 : 1})`,
              transformOrigin: "0 50%",
            }}
          >
            <div
              style={{
                width: 66,
                height: 66,
                borderRadius: 33,
                flexShrink: 0,
                background: done ? C.green : on ? C.orange : C.soft,
                border: `4px solid ${C.ink}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: FONT,
                fontWeight: 800,
                fontSize: 36,
                color: done ? C.white : C.ink,
              }}
            >
              {done ? "✓" : i + 1}
            </div>
            <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: it.length > 22 ? 46 : 52, color: C.ink, lineHeight: 1.05 }}>{it}</div>
          </div>
        );
      })}
    </div>
  );
};
