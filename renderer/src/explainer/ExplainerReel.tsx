import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { AvatarMode, Pose, Scene, SceneManifest } from "../types";
import { ExplainerBackground } from "./ExplainerBackground";
import { Pill } from "./KeywordLabel";
import { type Placement, PresenterAvatar } from "./PresenterAvatar";
import { type Move, SectionTransition, EXIT_FRAMES } from "./SectionTransition";
import { type BubbleAnchor, SpeechBubble } from "./SpeechBubble";
import { ChapterTabs } from "./StepProgress";
import { C, ensureFonts, PILL, pop } from "./theme";
import { VISUALS } from "./Visuals";

ensureFonts();

// Layout of the 1080x1920 canvas (top 200 px and bottom 380 px stay clear for platform UI, and
// nothing that must be read goes right of x≈940 below y≈1100, where the like/share buttons sit):
//   header pill        y 222-290
//   chapter tabs       y 312-394 (only when the script defines steps)
//   stage              y 330/430 → 1150 (corner presenter) or → 790 (centred presenter)
//   presenter (corner) x 25-325, y 1185-1545, its speech bubble to the right (x 350-940)
//   presenter (centre) x 305-775, y 800-1360, bubble underneath (y ~1380)
const HEADER_TOP = 222;
const TABS_TOP = 312;
const SIDE = 60;

const PLACE: Record<AvatarMode, Placement> = {
  corner: { x: 175, y: 1185, size: 300, lookX: 6, lookY: -6 },
  center: { x: 540, y: 800, size: 470, lookX: 0, lookY: 0 },
  reaction: { x: 540, y: 760, size: 520, lookX: 0, lookY: 0 },
  hidden: { x: 175, y: 1185, size: 300, lookX: 6, lookY: -6 },
};
const BUBBLE: Record<"corner" | "center", BubbleAnchor> = {
  corner: { x: 352, y: 1222, side: "left", maxWidth: 590, fontSize: 54 },
  center: { x: 540, y: 1372, side: "below", maxWidth: 860, fontSize: 58 },
};
const stageFor = (s: Scene, tabs: boolean) => {
  const top = s.label || tabs ? (tabs ? 424 : 318) : 236;
  const bottom = s.avatar === "corner" || s.avatar === "hidden" ? 1160 : s.avatar === "reaction" ? 740 : 790;
  return { top, height: bottom - top };
};

const useScene = (scenes: Scene[]) => {
  const frame = useCurrentFrame();
  const idx = Math.max(0, scenes.findIndex((s) => frame >= s.start_frame && frame < s.end_frame));
  const i = frame >= scenes[scenes.length - 1].end_frame ? scenes.length - 1 : idx;
  return { i, scene: scenes[i], prev: i > 0 ? scenes[i - 1] : undefined };
};

const continues = (a: Scene | undefined, b: Scene) =>
  !!a && b.transition === "cut" && a.visual === b.visual && ["dials", "network", "datastream"].includes(b.visual ?? "");

const moveOf = (s: Scene | undefined): Move => (s?.transition === "slide" ? "slide" : s?.transition === "wipe" ? "wipe" : s?.transition === "pop" ? "pop" : "cut");

// Header pill: the section's label. It flips when the label changes and otherwise stays put.
const Header: React.FC<{ scenes: Scene[]; i: number }> = ({ scenes, i }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = scenes[i];
  if (!s.label) return null;
  let since = s.start_frame;
  for (let k = i - 1; k >= 0 && scenes[k].label === s.label; k--) since = scenes[k].start_frame;
  const p = pop(frame, since, fps);
  return (
    <div style={{ position: "absolute", top: HEADER_TOP, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
      <div style={{ transform: `scale(${0.6 + 0.4 * Math.min(p, 1.05)}) rotate(${(1 - Math.min(p, 1)) * -6}deg)`, opacity: Math.min(1, p * 2) }}>
        <Pill text={s.label} color={PILL[s.label_color ?? "orange"]} textColor={s.label_color === "purple" || s.label_color === "pink" ? C.white : C.ink} size={40} />
      </div>
    </div>
  );
};

const Tabs: React.FC<{ scenes: Scene[]; i: number; chapters: string[] }> = ({ scenes, i, chapters }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = scenes[i];
  if (!chapters.length || s.chapter === null || s.chapter === undefined) return null;
  let since = s.start_frame;
  for (let k = i - 1; k >= 0 && scenes[k].chapter === s.chapter; k--) since = scenes[k].start_frame;
  let shownSince = s.start_frame;
  for (let k = i - 1; k >= 0 && scenes[k].chapter !== null && scenes[k].chapter !== undefined; k--) shownSince = scenes[k].start_frame;
  const p = spring({ frame: frame - shownSince, fps, config: { damping: 200 }, durationInFrames: 12 });
  return (
    <div style={{ position: "absolute", top: TABS_TOP, left: SIDE, opacity: p, transform: `translateY(${(1 - p) * -30}px)` }}>
      <ChapterTabs chapters={chapters} active={s.chapter} activeSince={since} />
    </div>
  );
};

const Presenter: React.FC<{ m: SceneManifest; i: number }> = ({ m, i }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = m.scenes[i];
  const prev = i > 0 ? m.scenes[i - 1] : undefined;
  const to = PLACE[s.avatar];
  const from = prev ? PLACE[prev.avatar] : to;
  const t = spring({ frame: frame - s.start_frame, fps, config: { damping: 200 }, durationInFrames: 16 });
  const intro = i === 0 ? pop(frame, 0, fps) : 1;
  const place: Placement = {
    x: interpolate(t, [0, 1], [from.x, to.x]),
    y: interpolate(t, [0, 1], [from.y, to.y]) + (1 - Math.min(intro, 1)) * 200,
    size: interpolate(t, [0, 1], [from.size, to.size]),
    lookX: interpolate(t, [0, 1], [from.lookX, to.lookX]),
    lookY: interpolate(t, [0, 1], [from.lookY, to.lookY]),
  };
  return (
    <PresenterAvatar
      track={m.avatar}
      expression={s.expression}
      prevExpression={prev?.expression ?? "neutral"}
      pose={(s.pose ?? "idle") as Pose}
      prevPose={(prev?.pose ?? "idle") as Pose}
      beatStart={s.start_frame}
      beatEnd={s.end_frame}
      placement={place}
    />
  );
};

export const ExplainerReel: React.FC<SceneManifest> = (m) => {
  const { i, scene } = useScene(m.scenes);
  const chapters = m.chapters ?? [];
  const bubble = BUBBLE[scene.avatar === "corner" || scene.avatar === "hidden" ? "corner" : "center"];
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <ExplainerBackground />
      {m.scenes.map((s, k) => {
        const next = m.scenes[k + 1];
        const prev = k > 0 ? m.scenes[k - 1] : undefined;
        const len = Math.max(1, s.end_frame - s.start_frame);
        const exit: Move | "none" = !next || continues(s, next) ? "none" : moveOf(next);
        const stage = stageFor(s, chapters.length > 0 && s.chapter !== null && s.chapter !== undefined);
        const V = VISUALS[s.visual || "card"] ?? VISUALS.card;
        return (
          <Sequence key={s.id} from={s.start_frame} durationInFrames={len + (exit === "none" ? 0 : EXIT_FRAMES)} layout="none">
            <div style={{ position: "absolute", left: SIDE, width: 1080 - 2 * SIDE, top: stage.top, height: stage.height }}>
              <SectionTransition enter={k === 0 ? "pop" : moveOf(s)} exit={exit} continued={continues(prev, s)} durationInFrames={len}>
                <V scene={s} continued={continues(prev, s)} handle={m.handle} />
              </SectionTransition>
            </div>
          </Sequence>
        );
      })}
      <Tabs scenes={m.scenes} i={i} chapters={chapters} />
      <Header scenes={m.scenes} i={i} />
      <Presenter m={m} i={i} />
      <SpeechBubble groups={m.caption_groups} anchor={bubble} />
      {m.audio_src ? <Audio src={staticFile(m.audio_src)} /> : null}
    </AbsoluteFill>
  );
};
