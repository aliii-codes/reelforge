// Motion language shared by every scene: entrances (cut / whip / zoom / flash), camera moves
// (push / drift / punch), a short shake on impacts. All transforms - no blur filters, which are
// expensive in headless Chrome on a 2-core CPU.
import { Easing, interpolate, spring } from "remotion";
import type { Scene } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// `local` = frame inside the scene.
export const enterStyle = (scene: Scene, local: number, fps: number): { transform: string; opacity: number } => {
  switch (scene.transition) {
    case "whip": {
      // fast lateral push with a skew that reads as motion blur
      const t = interpolate(local, [0, 7], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
      return { transform: `translateX(${(1 - t) * 620}px) skewX(${(1 - t) * -14}deg)`, opacity: 0.35 + 0.65 * t };
    }
    case "zoom": {
      const t = interpolate(local, [0, 9], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
      return { transform: `scale(${1.35 - 0.35 * t})`, opacity: interpolate(local, [0, 4], [0, 1], clamp) };
    }
    case "flash": {
      const t = interpolate(local, [0, 8], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
      return { transform: `scale(${1.08 - 0.08 * t})`, opacity: 1 };
    }
    case "slide": {
      const s = spring({ frame: local, fps, config: { damping: 16, stiffness: 140 }, durationInFrames: 12 });
      return { transform: `translateX(${(1 - s) * 160}px)`, opacity: s };
    }
    case "pop": {
      const s = spring({ frame: local, fps, config: { damping: 16, stiffness: 140 }, durationInFrames: 12 });
      return { transform: `scale(${0.7 + s * 0.3})`, opacity: s };
    }
    case "fade":
    case "wipe":
      return { transform: "", opacity: interpolate(local, [0, 8], [0, 1], clamp) };
    default:
      return { transform: "", opacity: 1 }; // hard cut
  }
};

export const cameraStyle = (scene: Scene, local: number, fps: number): string => {
  const dur = Math.max(1, scene.end_frame - scene.start_frame);
  const p = local / dur;
  switch (scene.camera) {
    case "push":
      return `scale(${1 + 0.06 * p})`;
    case "drift":
      return `translateY(${-26 * p}px) scale(${1.02 + 0.02 * p})`;
    case "punch": {
      const s = spring({ frame: local, fps, config: { damping: 9, stiffness: 180 } });
      return `scale(${1.18 - 0.16 * s + 0.03 * p}) rotate(${(1 - s) * -2}deg)`;
    }
    default:
      return ""; // "none", and "track" (footage components move their own camera)
  }
};

// Small decaying shake for impacts (number slams, flash cuts). Deterministic.
export const shake = (framesSince: number, strength = 14): string => {
  if (framesSince < 0 || framesSince > 10) return "";
  const k = (1 - framesSince / 10) * strength;
  return `translate(${Math.sin(framesSince * 2.9) * k}px, ${Math.cos(framesSince * 3.7) * k * 0.6}px)`;
};

// Emphasised word spoken -> brief punch-in of the scene content.
export const punchScale = (scene: Scene, local: number): number => {
  let p = 0;
  for (const c of scene.cues) {
    if (c.kind !== "emphasis") continue;
    const d = local - (c.frame - scene.start_frame);
    if (d >= 0 && d < 12) p = Math.max(p, Math.sin((d / 12) * Math.PI));
  }
  return 1 + p * 0.03;
};
