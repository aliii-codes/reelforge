import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, HAND, outline, PILL, pop, pulse } from "./theme";

const clean = (w: string) => w.toLowerCase().replace(/[^a-z0-9%$.]/g, "").replace(/\.$/, "");
export const isKey = (w: string, emphasis: string[]) => {
  const set = new Set(emphasis.map(clean));
  return set.has(clean(w)) || /\d/.test(w);
};

// Small coloured pill with an outline: section headers, tags, badges.
export const Pill: React.FC<{
  text: string;
  color?: string;
  size?: number;
  textColor?: string;
  rotate?: number;
  style?: React.CSSProperties;
}> = ({ text, color = C.orange, size = 40, textColor = C.ink, rotate = 0, style }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      padding: `${size * 0.12}px ${size * 0.6}px ${size * 0.04}px`,
      background: color,
      color: textColor,
      fontFamily: FONT,
      fontWeight: 800,
      fontSize: size,
      lineHeight: 1.25,
      whiteSpace: "nowrap",
      transform: `rotate(${rotate}deg)`,
      ...outline(size * 0.42, Math.max(4, size * 0.13), 4),
      ...style,
    }}
  >
    {text}
  </div>
);

// Handwritten purple annotation ("internet = the data" style notes).
export const Note: React.FC<{ text: string; size?: number; color?: string; style?: React.CSSProperties }> = ({ text, size = 46, color = C.purple, style }) => (
  <div style={{ fontFamily: HAND, fontWeight: 700, fontSize: size, color, lineHeight: 1.1, ...style }}>{text}</div>
);

// A phrase whose key terms are marked: "marker" = orange highlighter behind the word,
// "pill" = solid purple pill with white text. `reveal(i)` (0..1) lets words appear as spoken.
export const RichText: React.FC<{
  text: string;
  emphasis: string[];
  size: number;
  mode?: "marker" | "pill";
  align?: "left" | "center";
  reveal?: (i: number) => number;
  hotAt?: number; // frame the key term gets its emphasis pulse
  color?: string;
}> = ({ text, emphasis, size, mode = "marker", align = "left", reveal, hotAt, color = C.ink }) => {
  const frame = useCurrentFrame();
  const words = text.split(/\s+/).filter(Boolean);
  const pulseK = hotAt !== undefined ? pulse(frame, hotAt, 14) : 0;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: align === "center" ? "center" : "flex-start",
        gap: `${size * 0.06}px ${size * 0.24}px`,
        fontFamily: FONT,
        fontWeight: 800,
        fontSize: size,
        lineHeight: 1.12,
        color,
      }}
    >
      {words.map((w, i) => {
        const p = reveal ? reveal(i) : 1;
        const key = isKey(w, emphasis);
        const base: React.CSSProperties = {
          display: "inline-block",
          opacity: Math.min(1, p * 1.5),
          transform: `translateY(${(1 - Math.min(p, 1)) * size * 0.4}px) scale(${(0.9 + 0.1 * Math.min(p, 1.05)) * (key ? 1 + 0.06 * pulseK : 1)})`,
        };
        if (!key) return <span key={i} style={base}>{w}</span>;
        if (mode === "pill")
          return (
            <span key={i} style={{ ...base, color: C.white, background: C.purple, borderRadius: size * 0.22, padding: `0 ${size * 0.18}px`, margin: `0 ${-size * 0.06}px` }}>
              {w}
            </span>
          );
        return (
          <span key={i} style={{ ...base, position: "relative" }}>
            <span
              style={{
                position: "absolute",
                left: -size * 0.08,
                right: -size * 0.08,
                top: size * 0.18,
                bottom: size * 0.02,
                background: C.orange,
                opacity: 0.85,
                borderRadius: size * 0.08,
                transformOrigin: "0 50%",
                transform: `scaleX(${Math.min(1, Math.max(0, (p - 0.4) / 0.6))})`,
              }}
            />
            <span style={{ position: "relative" }}>{w}</span>
          </span>
        );
      })}
    </div>
  );
};

// Big bold phrase revealed word-by-word on the spoken cues, key term as a pill, emoji sticker.
export const KeywordLabel: React.FC<{
  text: string;
  emphasis: string[];
  wordAt: (i: number) => number;
  emoji?: string;
  size?: number;
}> = ({ text, emphasis, wordAt, emoji, size = 96 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = text.split(/\s+/).filter(Boolean).length;
  const lastAt = wordAt(Math.max(0, n - 1));
  const sticker = pop(frame, lastAt + 4, fps);
  return (
    <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center" }}>
      <RichText text={text} emphasis={emphasis} size={size} mode="pill" align="center" reveal={(i) => pop(frame, wordAt(i), fps)} />
      {emoji ? (
        <div style={{ marginTop: 26, fontSize: 110, transform: `scale(${sticker}) rotate(${(1 - sticker) * -30}deg)`, lineHeight: 1 }}>{emoji}</div>
      ) : null}
    </div>
  );
};

export { PILL };
