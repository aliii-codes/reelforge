import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { Note, RichText } from "./KeywordLabel";
import { C, card, outline, pop } from "./theme";

// Outlined card: an emoji tile that springs in, the headline with its key term highlighted
// (marker sweeps in as the words land), and an optional handwritten note underneath.
export const InfoCard: React.FC<{
  emoji: string;
  headline: string;
  emphasis: string[];
  note?: string;
  tileColor?: string;
  enterAt?: number;
  hotAt?: number;
  width?: number;
}> = ({ emoji, headline, emphasis, note, tileColor = C.orange, enterAt = 0, hotAt, width = 940 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, enterAt, fps);
  const tile = pop(frame, enterAt + 4, fps);
  const size = headline.length > 34 ? 62 : 72;
  return (
    <div
      style={{
        width,
        ...card(32),
        padding: "34px 36px 30px",
        display: "flex",
        flexDirection: "column",
        gap: 22,
        opacity: Math.min(1, p * 1.5),
        transform: `translateY(${(1 - p) * 50}px) scale(${0.94 + 0.06 * p})`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
        <div
          style={{
            flexShrink: 0,
            width: 150,
            height: 150,
            background: tileColor,
            ...outline(30, 6, 4),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 92,
            transform: `scale(${tile}) rotate(${(1 - tile) * -24}deg)`,
          }}
        >
          {emoji}
        </div>
        <RichText text={headline} emphasis={emphasis} size={size} reveal={(i) => pop(frame, enterAt + 6 + i * 2, fps)} hotAt={hotAt} />
      </div>
      {note ? <Note text={note} style={{ opacity: Math.min(1, pop(frame, enterAt + 16, fps)) }} /> : null}
    </div>
  );
};
