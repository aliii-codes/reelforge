import React from "react";
import { AbsoluteFill } from "remotion";
import { Avatar } from "./components/Avatar";
import { Background } from "./components/Background";
import { ExplainerCover } from "./explainer/ExplainerCover";
import type { SceneManifest } from "./types";

// Static cover (rendered as a still at frame 0). Text stays inside the centre-safe area
// because Reels grid thumbnails crop the 9:16 cover to roughly 3:4.
export const Cover: React.FC<SceneManifest> = (m) => (m.style === "explainer" ? <ExplainerCover {...m} /> : <CreatorCover {...m} />);

const CreatorCover: React.FC<SceneManifest> = (m) => {
  const words = m.cover_title.split(/\s+/);
  const size = m.cover_title.length > 28 ? 104 : 124;
  const still = { ...m.avatar, mouth_open: [0], visemes: ["rest" as const], blink_frames: [], center_y: 1180, size: 520 };
  return (
    <AbsoluteFill style={{ backgroundColor: m.theme.bg_to }}>
      <Background theme={m.theme} scene={m.scenes[0]} />
      <div
        style={{
          position: "absolute",
          top: 380,
          left: 90,
          right: 90,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: `0 ${size * 0.25}px`,
          fontFamily: m.theme.font_family,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1.04,
          color: m.theme.text,
          textAlign: "center",
          letterSpacing: -2,
          textShadow: "0 10px 40px rgba(0,0,0,0.5)",
        }}
      >
        {words.map((w, i) => (
          <span key={i} style={{ color: i === words.length - 1 ? m.theme.accent : m.theme.text }}>
            {w}
          </span>
        ))}
      </div>
      <Avatar track={still} expression="surprised" expressionStartFrame={-100} previousExpression="surprised" theme={m.theme} />
      {m.handle ? (
        <div style={{ position: "absolute", top: 1490, left: 0, right: 0, textAlign: "center", fontFamily: m.theme.font_family, fontWeight: 800, fontSize: 40, color: m.theme.muted }}>
          {m.handle}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
