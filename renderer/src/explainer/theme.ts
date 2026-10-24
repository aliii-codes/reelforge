// Explainer style: palette, type, outline language and the motion system. Every animation is a
// pure function of the frame (springs / interpolations from a cue frame), so renders are
// deterministic and can be split across Remotion's parallel tabs.
import type React from "react";
import { continueRender, delayRender, Easing, interpolate, spring } from "remotion";
import baloo from "../fonts/Baloo2.ttf";
import caveat from "../fonts/Caveat.ttf";

export const C = {
  bg: "#ECEEF2",
  dot: "#C8CCD6",
  ink: "#1F1C2E",
  white: "#FFFFFF",
  paper: "#FBFBFD",
  muted: "#A9ADBA",
  soft: "#DADDE5",
  orange: "#FF8A4C",
  purple: "#6D4AF6",
  pink: "#F2456E",
  green: "#1FAE7E",
  teal: "#17A9B8",
  yellow: "#FFC93C",
  skin: "#C98B62",
  skinShade: "#B07450",
} as const;

export const PILL: Record<string, string> = { orange: C.orange, purple: C.purple, pink: C.pink, green: C.green };
// Cycled for nodes, knobs, dots and bars.
export const CYCLE = [C.orange, C.purple, C.green, C.pink, C.teal];

export const FONT = "'Baloo 2', 'Lato', 'Noto Color Emoji', sans-serif";
export const HAND = "'Caveat', 'Baloo 2', cursive";
export const MONO = "'Fira Code', 'DejaVu Sans Mono', monospace";

// The outline language: thick dark stroke + hard offset shadow (no blur: cheap to render).
export const outline = (radius = 26, shadow = 7, border = 4): React.CSSProperties => ({
  border: `${border}px solid ${C.ink}`,
  borderRadius: radius,
  boxShadow: `${shadow}px ${shadow}px 0 ${C.ink}`,
});

export const card = (radius = 28): React.CSSProperties => ({
  background: C.white,
  ...outline(radius),
});

// ------------------------------------------------------------------ fonts (bundled OFL fonts)

let fontsRequested = false;
export const ensureFonts = () => {
  if (fontsRequested || typeof document === "undefined") return;
  fontsRequested = true;
  const handle = delayRender("Loading explainer fonts");
  const faces = [
    new FontFace("Baloo 2", `url(${baloo})`, { weight: "400 800" }),
    new FontFace("Caveat", `url(${caveat})`, { weight: "400 700" }),
  ];
  Promise.all(faces.map((f) => f.load()))
    .then((loaded) => {
      loaded.forEach((f) => (document.fonts as unknown as { add: (f: FontFace) => void }).add(f));
      continueRender(handle);
    })
    .catch((e) => {
      console.error("font load failed, falling back to system fonts", e);
      continueRender(handle);
    });
};

// ------------------------------------------------------------------ motion

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Entrance with a small, controlled overshoot (no rubber-band bouncing).
export const pop = (frame: number, at: number, fps: number) =>
  spring({ frame: frame - at, fps, config: { damping: 15, stiffness: 190, mass: 0.8 } });

// Smooth, overshoot-free settle for larger moves (layout changes, camera framing).
export const settle = (frame: number, at: number, fps: number, frames = 16) =>
  spring({ frame: frame - at, fps, config: { damping: 200 }, durationInFrames: frames });

// 0..1 progress for drawing lines / filling bars.
export const draw = (frame: number, at: number, dur = 14) =>
  interpolate(frame - at, [0, dur], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });

export const fadeIn = (frame: number, at: number, dur = 8) => interpolate(frame - at, [0, dur], [0, 1], clamp);

// A short 0->1->0 pulse lasting `len` frames after `at` (emphasis on a spoken word).
export const pulse = (frame: number, at: number, len = 12) => {
  const d = frame - at;
  return d >= 0 && d < len ? Math.sin((d / len) * Math.PI) : 0;
};

export const rise = (p: number, dist = 40): React.CSSProperties => ({
  opacity: Math.min(1, Math.max(0, p * 1.4)),
  transform: `translateY(${(1 - p) * dist}px) scale(${0.92 + 0.08 * p})`,
});

// Deterministic pseudo-random in [0,1) from an integer (stable across frames and tabs).
export const hash = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

export const mix = (a: number, b: number, t: number) => a + (b - a) * t;
