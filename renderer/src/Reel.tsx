import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Avatar, type AvatarPlacement } from "./components/Avatar";
import { Background } from "./components/Background";
import { Captions } from "./components/Captions";
import { SceneView } from "./components/Scenes";
import type { AvatarMode, SceneManifest } from "./types";

// Where the avatar sits for each staging mode. "hidden" parks it below the frame, so switching
// to/from it animates as a quick exit/entrance.
const PLACEMENT: Record<AvatarMode, AvatarPlacement> = {
  center: { x: 540, y: 1105, size: 440, lookX: 0, lookY: 0 },
  // small, bottom-left, looking up-right at the graphics
  corner: { x: 175, y: 1222, size: 220, lookX: 6, lookY: -6 },
  // big reaction shot for meme beats
  reaction: { x: 540, y: 950, size: 640, lookX: 0, lookY: 0 },
  hidden: { x: 540, y: 2400, size: 440, lookX: 0, lookY: 0 },
};

const usePlacement = (layout: AvatarMode, prev: AvatarMode | undefined, startFrame: number): AvatarPlacement => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const to = PLACEMENT[layout];
  const from = prev ? PLACEMENT[prev] : to;
  const t = spring({ frame: frame - startFrame, fps, config: { damping: 18, stiffness: 120 }, durationInFrames: 14 });
  const mix = (a: number, b: number) => interpolate(t, [0, 1], [a, b]);
  return { x: mix(from.x, to.x), y: mix(from.y, to.y), size: mix(from.size, to.size), lookX: mix(from.lookX, to.lookX), lookY: mix(from.lookY, to.lookY) };
};

const ProgressBar: React.FC<{ total: number; color: string }> = ({ total, color }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", top: 0, left: 0, height: 10, width: `${(frame / Math.max(total, 1)) * 100}%`, background: color }} />
  );
};

const Handle: React.FC<{ text: string; font: string }> = ({ text, font }) =>
  text ? (
    <div
      style={{
        position: "absolute",
        top: 120,
        left: 0,
        right: 0,
        textAlign: "center",
        fontFamily: font,
        fontWeight: 700,
        fontSize: 30,
        letterSpacing: 2,
        color: "rgba(255,255,255,0.55)",
      }}
    >
      {text}
    </div>
  ) : null;

export const Reel: React.FC<SceneManifest> = (m) => {
  const frame = useCurrentFrame();
  const sceneIdx = m.scenes.findIndex((s) => frame >= s.start_frame && frame < s.end_frame);
  const scene = sceneIdx >= 0 ? m.scenes[sceneIdx] : m.scenes[m.scenes.length - 1];
  const prev = sceneIdx > 0 ? m.scenes[sceneIdx - 1] : undefined;
  const mode: AvatarMode = scene?.avatar ?? "center";
  const placement = usePlacement(mode, prev?.avatar, scene?.start_frame ?? 0);
  const avatarVisible = !(mode === "hidden" && (!prev || prev.avatar === "hidden" || frame - scene.start_frame > 14));
  const flash = scene && scene.transition === "flash" ? Math.max(0, 1 - (frame - scene.start_frame) / 7) : 0;
  return (
    <AbsoluteFill style={{ backgroundColor: m.theme.bg_to }}>
      <Background theme={m.theme} scene={scene} />
      <Handle text={m.handle} font={m.theme.font_family} />
      {m.scenes.map((s) => (
        <Sequence key={s.id} from={s.start_frame} durationInFrames={Math.max(1, s.end_frame - s.start_frame)} layout="none">
          <SceneView scene={s} theme={m.theme} />
        </Sequence>
      ))}
      {scene && avatarVisible ? (
        <Avatar
          track={m.avatar}
          expression={scene.expression}
          expressionStartFrame={scene.start_frame}
          previousExpression={prev ? prev.expression : "neutral"}
          theme={m.theme}
          placement={placement}
        />
      ) : null}
      <Captions
        groups={m.caption_groups}
        style={m.caption_style}
        theme={m.theme}
        hidden={!!scene?.hide_captions || scene?.type === "meme"}
        backing={scene?.background === "paper"}
      />
      {flash > 0 ? <AbsoluteFill style={{ background: "#FFFFFF", opacity: flash * 0.9 }} /> : null}
      <ProgressBar total={m.duration_frames} color={m.theme.accent} />
      {/* Audio only matters in Remotion Studio previews; final renders are --muted and the
          narration/music mix is muxed by FFmpeg in Python. */}
      {m.audio_src ? <Audio src={staticFile(m.audio_src)} /> : null}
    </AbsoluteFill>
  );
};
