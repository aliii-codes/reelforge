import React from "react";
import { AbsoluteFill } from "remotion";
import type { SceneManifest } from "../types";
import { ExplainerBackground } from "./ExplainerBackground";
import { RichText } from "./KeywordLabel";
import { PresenterAvatar } from "./PresenterAvatar";
import { C, card, ensureFonts } from "./theme";

ensureFonts();

// Still cover in the explainer style. Everything sits in the centre band, since Reels grid
// thumbnails crop the 9:16 cover to roughly 3:4.
export const ExplainerCover: React.FC<SceneManifest> = (m) => {
  const words = m.cover_title.split(/\s+/).filter(Boolean);
  const key = [...words].sort((a, b) => b.length - a.length)[0] ?? "";
  const still = { ...m.avatar, mouth_open: [0], visemes: ["rest" as const], blink_frames: [], emphasis_frames: [], nod_frames: [] };
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <ExplainerBackground />
      <div style={{ position: "absolute", top: 400, left: 70, width: 940, ...card(36), padding: "40px 44px", transform: "rotate(-1.5deg)" }}>
        <RichText text={m.cover_title} emphasis={[key]} size={m.cover_title.length > 28 ? 92 : 108} align="center" />
      </div>
      <PresenterAvatar
        track={still}
        expression="happy"
        prevExpression="happy"
        pose="point"
        prevPose="point"
        beatStart={-30}
        beatEnd={1000}
        placement={{ x: 540, y: 820, size: 520, lookX: 0, lookY: -6 }}
      />
    </AbsoluteFill>
  );
};
