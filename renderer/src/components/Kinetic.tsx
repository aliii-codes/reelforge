// Kinetic typography: the spoken words themselves, phrase by phrase. Each word slams in on the
// frame it is spoken; emphasised words (numbers, key terms) are bigger and in the accent colour
// with a marker swipe. The previous phrase slides up and dims so the eye always knows where to look.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { KineticMeta, Scene, Theme } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const KineticScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const abs = frame + scene.start_frame;
  const phrases = (scene.meta as unknown as KineticMeta).phrases || [];
  let cur = 0;
  phrases.forEach((p, i) => {
    if (p.words.length && abs >= p.words[0].frame - 2) cur = i;
  });

  const render = (pi: number, role: "current" | "previous") => {
    const p = phrases[pi];
    if (!p) return null;
    const chars = p.words.reduce((n, w) => n + w.text.length + 1, 0);
    const base = chars <= 12 ? 132 : chars <= 20 ? 112 : 94;
    const enterAt = (p.words[0]?.frame ?? scene.start_frame) - scene.start_frame;
    const nextAt = (phrases[pi + 1]?.words[0]?.frame ?? 0) - scene.start_frame;
    const slide = role === "previous" ? interpolate(frame - nextAt, [-4, 2], [0, 1], { ...clamp, easing: (t) => 1 - (1 - t) ** 3 }) : 0;
    return (
      <div
        key={`${pi}-${role}`}
        style={{
          position: "absolute",
          left: 60,
          right: 60,
          top: role === "current" ? 700 : 700 - 300 * slide,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "baseline",
          gap: `6px ${base * 0.22}px`,
          opacity: role === "previous" ? 0.28 * (1 - slide * 0.6) : 1,
          transform: role === "previous" ? `scale(${1 - 0.35 * slide})` : "",
          transformOrigin: "50% 0%",
        }}
      >
        {p.words.map((w, wi) => {
          const at = w.frame - scene.start_frame;
          const s = spring({ frame: frame - at, fps, config: { damping: 11, stiffness: 230 } });
          const shown = role === "previous" || frame >= at - 1 || frame >= enterAt + wi * 3 + 40;
          // never wider than the safe text width (long hyphenated words like "seven-billion-parameter")
          const size = Math.min(w.emph ? base * 1.28 : base, 900 / Math.max(1, w.text.length * 0.56));
          const marker = w.emph ? interpolate(frame - at - 3, [0, 7], [0, 100], clamp) : 0;
          return (
            <span
              key={wi}
              style={{
                display: "inline-block",
                fontFamily: theme.font_family,
                fontWeight: 900,
                fontSize: size,
                lineHeight: 1.02,
                letterSpacing: -2,
                color: w.emph ? theme.accent : theme.text,
                opacity: shown ? (role === "previous" ? 1 : Math.min(1, s * 1.4)) : 0,
                transform: role === "previous" ? "" : `translateY(${(1 - s) * 40}px) scale(${1.25 - 0.25 * Math.min(1, s)})`,
                backgroundImage: w.emph
                  ? `linear-gradient(transparent 72%, ${theme.accent2}AA 72%, ${theme.accent2}AA 92%, transparent 92%)`
                  : "none",
                backgroundSize: `${marker}% 100%`,
                backgroundRepeat: "no-repeat",
                textShadow: "0 10px 40px rgba(0,0,0,0.45)",
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    );
  };

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {cur > 0 ? render(cur - 1, "previous") : null}
      {render(cur, "current")}
    </div>
  );
};
