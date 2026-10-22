import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { BackgroundMode, Scene, Theme } from "../types";

// A few background modes from one palette, switched on cuts (never cross-faded, so a cut reads as
// a cut). Gradients and a drifting dot grid only - no CSS blur, which is slow on a 2-core CPU.
export const Background: React.FC<{ theme: Theme; scene: Scene | undefined }> = ({ theme, scene }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const mode: BackgroundMode = scene?.background ?? "grid";
  const drift = (frame * 0.6) % 60;
  const orbX = width * (0.5 + Math.sin(frame / 90) * 0.18);
  const orbY = height * (0.3 + Math.cos(frame / 110) * 0.06);
  const dots = (alpha: number, color = "255,255,255") => (
    <div
      style={{
        position: "absolute",
        inset: -60,
        backgroundImage: `radial-gradient(rgba(${color},${alpha}) 2px, transparent 2.5px)`,
        backgroundSize: "60px 60px",
        transform: `translate(${drift}px, ${drift}px)`,
      }}
    />
  );
  const vignette = (
    <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 115%, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 60%)" }} />
  );

  let body: React.ReactNode;
  switch (mode) {
    case "glow":
      body = (
        <>
          <div style={{ position: "absolute", inset: 0, background: `linear-gradient(170deg, ${theme.bg_from} 0%, ${theme.bg_to} 100%)` }} />
          <div style={{ position: "absolute", inset: 0, background: `radial-gradient(circle at ${orbX}px ${orbY}px, ${theme.accent}40 0px, ${theme.accent}00 560px)` }} />
          <div style={{ position: "absolute", inset: 0, background: `radial-gradient(circle at ${width - orbX}px ${height * 0.75}px, ${theme.accent2}2A 0px, ${theme.accent2}00 520px)` }} />
          {vignette}
        </>
      );
      break;
    case "accent":
      body = (
        <>
          <div style={{ position: "absolute", inset: 0, background: `linear-gradient(160deg, ${theme.accent2} 0%, #B8325F 100%)` }} />
          <div
            style={{
              position: "absolute",
              inset: -200,
              backgroundImage: "repeating-linear-gradient(115deg, rgba(255,255,255,0.07) 0 40px, transparent 40px 120px)",
              transform: `translateX(${(frame * 3) % 160}px)`,
            }}
          />
        </>
      );
      break;
    case "terminal":
      body = (
        <>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, #08090E 0%, #10121A 100%)" }} />
          {dots(0.05)}
          <div style={{ position: "absolute", inset: 0, background: `radial-gradient(circle at 50% 40%, ${theme.accent}14 0px, transparent 700px)` }} />
        </>
      );
      break;
    case "paper":
      body = (
        <>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, #F4F2EE 0%, #E9E6EF 100%)" }} />
          {dots(0.06, "30,25,60")}
        </>
      );
      break;
    default:
      body = (
        <>
          <div style={{ position: "absolute", inset: 0, background: `linear-gradient(165deg, ${theme.bg_from} 0%, ${theme.bg_to} 100%)` }} />
          {dots(0.1)}
          {vignette}
        </>
      );
  }
  return <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>{body}</div>;
};
