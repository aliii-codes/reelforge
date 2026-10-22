import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionGroup, CaptionStyle, Theme } from "../types";

// Word-timed captions: one short group on screen at a time, the spoken word highlighted.
// Groups are sized by the Python side (max words/characters) so text never overflows; the
// font-size guard below is a second line of defence.
export const Captions: React.FC<{ groups: CaptionGroup[]; style: CaptionStyle; theme: Theme }> = ({
  groups,
  style,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const group = groups.find((g) => frame >= g.start_frame && frame < g.end_frame);
  if (!group) return null;

  const chars = group.words.reduce((n, w) => n + w.text.length + 1, 0);
  const approxLineWidth = chars * style.font_size * 0.58;
  const fontSize = approxLineWidth > style.max_width * 2 ? (style.font_size * style.max_width * 2) / approxLineWidth : style.font_size;

  const enter = spring({ frame: frame - group.start_frame, fps, config: { damping: 14, stiffness: 180 } });
  const scale = interpolate(enter, [0, 1], [0.86, 1]);

  return (
    <div
      style={{
        position: "absolute",
        left: (width - style.max_width) / 2,
        width: style.max_width,
        top: style.center_y,
        transform: `translateY(-50%) scale(${scale})`,
        opacity: enter,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: "6px 14px",
        fontFamily: theme.font_family,
        fontWeight: 900,
        fontSize,
        lineHeight: 1.12,
        textAlign: "center",
      }}
    >
      {group.words.map((w, i) => {
        const active = frame >= w.start_frame && frame < w.end_frame;
        const spoken = frame >= w.end_frame;
        const pop = active
          ? spring({ frame: frame - w.start_frame, fps, config: { damping: 12, stiffness: 260 }, durationInFrames: 8 })
          : 0;
        return (
          <span
            key={`${group.start_frame}-${i}`}
            style={{
              padding: "4px 14px",
              borderRadius: 18,
              color: active ? "#0E0B1F" : w.emphasis ? theme.accent : spoken ? "#FFFFFF" : "rgba(255,255,255,0.88)",
              background: active ? style.highlight : "transparent",
              transform: `scale(${1 + pop * 0.08})`,
              textTransform: style.uppercase ? "uppercase" : "none",
              WebkitTextStroke: active ? "0px" : "2px rgba(8,6,20,0.85)",
              paintOrder: "stroke fill",
              textShadow: active ? "none" : "0 6px 18px rgba(0,0,0,0.55)",
            }}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
};
