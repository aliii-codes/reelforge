import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionGroup, CaptionStyle, Theme } from "../types";

// Word-timed captions, creator style: heavy white type with a dark stroke and shadow (legible on
// any background), the spoken word lifts and turns accent-coloured, key terms (numbers, emphasised
// words) stay accent-coloured once spoken. No boxes. Groups are short (<= 3 words) and sized by
// the Python side; the font-size guard is a second line of defence. `backing` adds a translucent
// plate for light backgrounds (screenshots).
export const Captions: React.FC<{ groups: CaptionGroup[]; style: CaptionStyle; theme: Theme; hidden?: boolean; backing?: boolean }> = ({
  groups,
  style,
  theme,
  hidden,
  backing,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const group = groups.find((g) => frame >= g.start_frame && frame < g.end_frame);
  if (!group || hidden) return null;

  const chars = group.words.reduce((n, w) => n + w.text.length + 1, 0);
  const approxLineWidth = chars * style.font_size * 0.6;
  const fontSize = approxLineWidth > style.max_width * 2 ? (style.font_size * style.max_width * 2) / approxLineWidth : style.font_size;
  const enter = spring({ frame: frame - group.start_frame, fps, config: { damping: 14, stiffness: 200 } });

  return (
    <div
      style={{
        position: "absolute",
        left: (width - style.max_width) / 2,
        width: style.max_width,
        top: style.center_y,
        transform: `translateY(-50%) translateY(${(1 - enter) * 18}px)`,
        opacity: enter,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "baseline",
          gap: `4px ${fontSize * 0.24}px`,
          padding: backing ? "14px 26px" : 0,
          borderRadius: 26,
          background: backing ? "rgba(12,10,28,0.82)" : "transparent",
          fontFamily: theme.font_family,
          fontWeight: 900,
          fontSize,
          lineHeight: 1.1,
          textAlign: "center",
          letterSpacing: -0.5,
        }}
      >
        {group.words.map((w, i) => {
          const active = frame >= w.start_frame && frame < w.end_frame;
          const spoken = frame >= w.start_frame;
          const lift = active ? spring({ frame: frame - w.start_frame, fps, config: { damping: 12, stiffness: 300 }, durationInFrames: 7 }) : 0;
          const color = active ? theme.accent : w.emphasis && spoken ? theme.accent : "#FFFFFF";
          return (
            <span
              key={`${group.start_frame}-${i}`}
              style={{
                display: "inline-block",
                color,
                opacity: spoken ? 1 : 0.55,
                transform: `translateY(${-6 * lift}px) scale(${1 + 0.1 * lift})`,
                textTransform: style.uppercase ? "uppercase" : "none",
                WebkitTextStroke: backing ? "0px" : "3px rgba(8,6,20,0.9)",
                paintOrder: "stroke fill",
                textShadow: "0 6px 22px rgba(0,0,0,0.6)",
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};

