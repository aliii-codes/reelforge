import React from "react";
import { interpolateColors, useCurrentFrame, useVideoConfig } from "remotion";
import type { Scene, Theme } from "../types";

// Cheap-to-render animated backdrop: gradients and a drifting dot grid only (no CSS blur,
// which is slow in headless Chrome on a 2-core CPU).
const SCENE_TINT: Record<string, number> = {
  hook: 0,
  explain: 0.15,
  stat: 0.35,
  analogy: 0.5,
  diagram: 0.2,
  comparison: 0.45,
  twist: 1,
  cta: 0.6,
};

export const Background: React.FC<{ theme: Theme; scene: Scene | undefined }> = ({ theme, scene }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const tint = scene ? SCENE_TINT[scene.type] ?? 0 : 0;
  const glow = interpolateColors(tint, [0, 1], [theme.accent, theme.accent2]);
  const drift = (frame * 0.6) % 60;
  const orbX = width * (0.5 + Math.sin(frame / 90) * 0.18);
  const orbY = height * (0.28 + Math.cos(frame / 110) * 0.06);
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: `linear-gradient(165deg, ${theme.bg_from} 0%, ${theme.bg_to} 100%)` }} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(circle at ${orbX}px ${orbY}px, ${glow}55 0px, ${glow}00 520px)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: -60,
          backgroundImage: "radial-gradient(rgba(255,255,255,0.10) 2px, transparent 2.5px)",
          backgroundSize: "60px 60px",
          transform: `translate(${drift}px, ${drift}px)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 50% 120%, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 60%)",
        }}
      />
    </div>
  );
};
