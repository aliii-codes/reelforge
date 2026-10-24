import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionGroup } from "../types";
import { C, FONT, outline, pop } from "./theme";

// Captions as the presenter's speech bubble: one phrase at a time, words darken as they are
// spoken (upcoming words stay light grey), and key terms turn into a purple pill once spoken.
// `side` is where the presenter is: "left" (bubble to the right of a corner presenter) or
// "below" (bubble under a centred presenter).

const GAP_REOPEN = 8; // frames of silence after which the bubble pops in again

export interface BubbleAnchor {
  x: number;
  y: number;
  side: "left" | "below";
  maxWidth: number;
  fontSize: number;
}

const Tail: React.FC<{ side: "left" | "below" }> = ({ side }) =>
  side === "left" ? (
    <svg width={34} height={44} viewBox="0 0 34 44" style={{ position: "absolute", left: -29, top: 22 }}>
      <polygon points="34,2 2,22 34,42" fill={C.white} />
      <polyline points="34,2 2,22 34,42" fill="none" stroke={C.ink} strokeWidth={4} strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width={48} height={34} viewBox="0 0 48 34" style={{ position: "absolute", left: "50%", marginLeft: -24, top: -29 }}>
      <polygon points="2,34 24,2 46,34" fill={C.white} />
      <polyline points="2,34 24,2 46,34" fill="none" stroke={C.ink} strokeWidth={4} strokeLinejoin="round" />
    </svg>
  );

export const SpeechBubble: React.FC<{ groups: CaptionGroup[]; anchor: BubbleAnchor; uppercase?: boolean }> = ({ groups, anchor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const gi = groups.findIndex((g) => frame >= g.start_frame && frame < g.end_frame);
  // Keep the last phrase briefly after it ends so the bubble can shrink away instead of vanishing.
  let idx = gi;
  let closing = 0;
  if (idx < 0) {
    const last = groups.reduce((acc, g, i) => (g.end_frame <= frame ? i : acc), -1);
    if (last < 0 || frame - groups[last].end_frame >= 6) return null;
    idx = last;
    closing = interpolate(frame - groups[last].end_frame, [0, 6], [0, 1]);
  }
  const g = groups[idx];
  // Find where this run of back-to-back phrases started: the bubble only pops at the start of a run.
  let runStart = g.start_frame;
  for (let k = idx; k > 0 && groups[k].start_frame - groups[k - 1].end_frame < GAP_REOPEN; k--) runStart = groups[k - 1].start_frame;
  const open = pop(frame, runStart, fps);
  const swap = interpolate(frame - g.start_frame, [0, 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const scale = (0.55 + 0.45 * Math.min(open, 1.04)) * (1 - 0.4 * closing);
  const origin = anchor.side === "left" ? "0% 40px" : "50% 0%";
  const fs = anchor.fontSize;
  const words = g.words;
  const chars = words.reduce((n, w) => n + w.text.length + 1, 0);
  const size = chars > 30 ? fs * 0.9 : fs;

  const box: React.CSSProperties =
    anchor.side === "left"
      ? { position: "absolute", left: anchor.x, top: anchor.y, maxWidth: anchor.maxWidth }
      : { position: "absolute", left: anchor.x - anchor.maxWidth / 2, top: anchor.y, width: anchor.maxWidth, display: "flex", justifyContent: "center" };
  return (
    <div style={box}>
      <div
        style={{
          position: "relative",
          display: "inline-block",
          background: C.white,
          ...outline(30, 6, 4),
          padding: "12px 26px 8px",
          transform: `scale(${scale})`,
          transformOrigin: origin,
          opacity: Math.min(1, open * 2) * (1 - closing),
        }}
      >
        <Tail side={anchor.side} />
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: `0 ${size * 0.24}px`,
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: size,
            lineHeight: 1.18,
            transform: `translateY(${(1 - swap) * 6}px)`,
            opacity: 0.4 + 0.6 * swap,
          }}
        >
          {words.map((w, i) => {
            const spoken = frame >= w.start_frame;
            const hot = w.emphasis && spoken;
            return (
              <span
                key={`${g.start_frame}-${i}`}
                style={{
                  color: hot ? C.white : spoken ? C.ink : C.muted,
                  background: hot ? C.purple : "transparent",
                  borderRadius: 12,
                  padding: hot ? "0 12px" : 0,
                  margin: hot ? "2px -4px" : 0,
                }}
              >
                {w.text}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};
