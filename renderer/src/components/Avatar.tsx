import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { AvatarTrack, Expression, Theme, Viseme } from "../types";

// "Forge": ReelForge's original avatar. Every shape is drawn here in code; no external art.
// Mouth opening comes from the narration loudness envelope (computed in Python), mouth
// *shape* from a coarse viseme guess derived from the word being spoken. This is an
// approximation, not true phoneme-accurate lip-sync.

const SKIN = "#F2C29E";
const SKIN_SHADE = "#E2A983";
const HAIR = "#1F1A2E";
const HOODIE = "#262A4F";
const HOODIE_SHADE = "#1C1F3D";
const PHONES = "#34386A";

interface ExpressionPose {
  browLeftY: number;
  browRightY: number;
  browLeftRot: number;
  browRightRot: number;
  eyeScaleY: number;
  pupilDx: number;
  pupilDy: number;
  smile: number; // curvature of the closed mouth, + = smile
}

const POSES: Record<Expression, ExpressionPose> = {
  neutral: { browLeftY: 0, browRightY: 0, browLeftRot: 0, browRightRot: 0, eyeScaleY: 1, pupilDx: 0, pupilDy: 0, smile: 6 },
  surprised: { browLeftY: -16, browRightY: -16, browLeftRot: -4, browRightRot: 4, eyeScaleY: 1.18, pupilDx: 0, pupilDy: 0, smile: 0 },
  thoughtful: { browLeftY: -12, browRightY: 3, browLeftRot: -8, browRightRot: 6, eyeScaleY: 0.92, pupilDx: 7, pupilDy: -8, smile: 2 },
  happy: { browLeftY: -6, browRightY: -6, browLeftRot: 3, browRightRot: -3, eyeScaleY: 0.62, pupilDx: 0, pupilDy: 2, smile: 16 },
  skeptical: { browLeftY: 4, browRightY: -13, browLeftRot: 8, browRightRot: -6, eyeScaleY: 0.85, pupilDx: -6, pupilDy: 0, smile: -3 },
};

const mix = (a: number, b: number, t: number) => a + (b - a) * t;

const blendPose = (from: ExpressionPose, to: ExpressionPose, t: number): ExpressionPose => ({
  browLeftY: mix(from.browLeftY, to.browLeftY, t),
  browRightY: mix(from.browRightY, to.browRightY, t),
  browLeftRot: mix(from.browLeftRot, to.browLeftRot, t),
  browRightRot: mix(from.browRightRot, to.browRightRot, t),
  eyeScaleY: mix(from.eyeScaleY, to.eyeScaleY, t),
  pupilDx: mix(from.pupilDx, to.pupilDx, t),
  pupilDy: mix(from.pupilDy, to.pupilDy, t),
  smile: mix(from.smile, to.smile, t),
});

const MOUTH_WIDTH: Record<Viseme, number> = { rest: 44, mbp: 42, ee: 60, aa: 52, oo: 30, fv: 48 };

const Mouth: React.FC<{ open: number; viseme: Viseme; smile: number }> = ({ open, viseme, smile }) => {
  const cx = 200;
  const cy = 272;
  const talking = open > 0.06 && viseme !== "mbp" && viseme !== "rest";
  if (!talking) {
    const w = 46;
    return (
      <path
        d={`M ${cx - w / 2} ${cy} Q ${cx} ${cy + smile} ${cx + w / 2} ${cy}`}
        stroke="#6B2433"
        strokeWidth={6}
        strokeLinecap="round"
        fill="none"
      />
    );
  }
  const w = MOUTH_WIDTH[viseme];
  const minH = viseme === "oo" ? 16 : 8;
  const h = minH + open * (viseme === "ee" || viseme === "fv" ? 22 : 40);
  const top = cy - h * 0.35;
  const bottom = cy + h * 0.65;
  const d = `M ${cx - w / 2} ${cy}
    C ${cx - w / 2} ${top - 4}, ${cx + w / 2} ${top - 4}, ${cx + w / 2} ${cy}
    C ${cx + w / 2} ${bottom + 6}, ${cx - w / 2} ${bottom + 6}, ${cx - w / 2} ${cy} Z`;
  return (
    <g>
      <clipPath id="mouthClip">
        <path d={d} />
      </clipPath>
      <path d={d} fill="#5A1A28" stroke="#6B2433" strokeWidth={3} />
      <g clipPath="url(#mouthClip)">
        {h > 12 && viseme !== "oo" ? (
          <rect x={cx - w / 2} y={top - 6} width={w} height={Math.min(10, h * 0.28) + 6} fill="#FFFFFF" />
        ) : null}
        {viseme === "fv" ? <rect x={cx - w / 2} y={cy + h * 0.2} width={w} height={8} fill="#FFFFFF" /> : null}
        {h > 18 ? <ellipse cx={cx} cy={bottom + 4} rx={w * 0.32} ry={h * 0.3} fill="#E0697A" /> : null}
      </g>
    </g>
  );
};

// A short 0->1->0 pulse lasting `len` frames after any of `frames`.
const pulse = (frame: number, frames: number[], len: number) => {
  let p = 0;
  for (const f of frames) {
    const d = frame - f;
    if (d >= 0 && d < len) p = Math.max(p, Math.sin((d / len) * Math.PI));
  }
  return p;
};

export interface AvatarPlacement {
  x: number;
  y: number;
  size: number;
  lookX: number; // pupils offset towards the graphics (focus layout)
  lookY: number;
}

export const Avatar: React.FC<{
  track: AvatarTrack;
  expression: Expression;
  expressionStartFrame: number;
  previousExpression: Expression;
  theme: Theme;
  placement?: AvatarPlacement;
}> = ({ track, expression, expressionStartFrame, previousExpression, theme, placement }) => {
  const frame = useCurrentFrame();
  const idx = Math.min(Math.max(frame, 0), track.mouth_open.length - 1);
  const open = track.mouth_open.length ? track.mouth_open[idx] : 0;
  const viseme: Viseme = track.visemes.length ? track.visemes[idx] : "rest";

  const t = interpolate(frame - expressionStartFrame, [0, 7], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pose = blendPose(POSES[previousExpression], POSES[expression], t);

  // Deterministic blinks: 4-frame close/open around each scheduled blink frame.
  let blink = 1;
  for (const b of track.blink_frames) {
    const d = frame - b;
    if (d >= 0 && d < 5) {
      blink = [0.45, 0.1, 0.1, 0.45, 0.85][d];
      break;
    }
  }
  const eyeScale = pose.eyeScaleY * blink;

  // Audio-driven gestures: brows lift + slight head tilt on emphasised words, a small nod at
  // sentence ends. Both come from the narration's word timestamps.
  const lift = pulse(frame, track.emphasis_frames ?? [], 14);
  const nodP = pulse(frame, track.nod_frames ?? [], 12);
  const browLift = -10 * lift;
  const lookX = placement?.lookX ?? 0;
  const lookY = placement?.lookY ?? 0;

  // Gentle idle sway plus a small nod driven by loudness.
  const sway = Math.sin(frame / 22) * 1.6 + lift * 3;
  const nod = open * 3.2 + nodP * 8;
  const breathe = 1 + Math.sin(frame / 30) * 0.006;

  const eye = (x: number) => (
    <g transform={`translate(${x} 198) scale(1 ${eyeScale}) translate(${-x} -198)`}>
      <ellipse cx={x} cy={198} rx={25} ry={28} fill="#FFFFFF" />
      <circle cx={x + pose.pupilDx + lookX} cy={200 + pose.pupilDy + lookY} r={13} fill="#1B1830" />
      <circle cx={x + pose.pupilDx + lookX + 4} cy={195 + pose.pupilDy + lookY} r={4.5} fill="#FFFFFF" />
    </g>
  );

  const cx = placement?.x ?? track.center_x;
  const cy = placement?.y ?? track.center_y;
  const size = placement?.size ?? track.size;
  return (
    <svg
      width={size}
      height={size * 1.1}
      viewBox="0 0 400 440"
      style={{
        position: "absolute",
        left: cx - size / 2,
        top: cy - (size * 1.1) / 2,
        overflow: "visible",
      }}
    >
      <defs>
        <radialGradient id="glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={theme.accent} stopOpacity={0.45} />
          <stop offset="100%" stopColor={theme.accent} stopOpacity={0} />
        </radialGradient>
      </defs>
      <ellipse cx={200} cy={230} rx={210} ry={200} fill="url(#glow)" />

      {/* Body / hoodie */}
      <g transform={`translate(0 ${nod * 0.3}) scale(1 ${breathe})`} style={{ transformOrigin: "200px 440px" }}>
        <path d="M 40 440 C 50 360, 110 330, 200 330 C 290 330, 350 360, 360 440 Z" fill={HOODIE} />
        <path d="M 130 336 C 150 375, 250 375, 270 336 C 250 350, 150 350, 130 336 Z" fill={HOODIE_SHADE} />
        <line x1={178} y1={360} x2={172} y2={412} stroke={theme.accent2} strokeWidth={5} strokeLinecap="round" />
        <line x1={222} y1={360} x2={228} y2={412} stroke={theme.accent2} strokeWidth={5} strokeLinecap="round" />
        <circle cx={172} cy={416} r={6} fill={theme.accent2} />
        <circle cx={228} cy={416} r={6} fill={theme.accent2} />
        <rect x={176} y={300} width={48} height={42} rx={14} fill={SKIN_SHADE} />
      </g>

      {/* Head group */}
      <g transform={`rotate(${sway} 200 330) translate(0 ${nod})`}>
        {/* Headphone band */}
        <path d="M 78 210 C 70 60, 330 60, 322 210" stroke={PHONES} strokeWidth={18} fill="none" strokeLinecap="round" />
        <ellipse cx={200} cy={190} rx={122} ry={132} fill={SKIN} />
        <ellipse cx={86} cy={205} rx={14} ry={22} fill={SKIN_SHADE} />
        <ellipse cx={314} cy={205} rx={14} ry={22} fill={SKIN_SHADE} />
        {/* Hair */}
        <path
          d="M 82 170 C 70 70, 170 40, 230 58 C 290 70, 336 110, 320 178 C 300 130, 260 112, 214 116 C 180 120, 150 104, 140 92 C 128 128, 104 150, 82 170 Z"
          fill={HAIR}
        />
        <path d="M 196 70 C 230 66, 272 82, 292 110" stroke={theme.accent} strokeWidth={7} strokeLinecap="round" fill="none" opacity={0.85} />
        {/* Ear cups */}
        <g>
          <rect x={56} y={170} width={42} height={76} rx={20} fill={PHONES} />
          <rect x={302} y={170} width={42} height={76} rx={20} fill={PHONES} />
          <rect x={64} y={186} width={8} height={44} rx={4} fill={theme.accent} opacity={0.9} />
          <rect x={328} y={186} width={8} height={44} rx={4} fill={theme.accent} opacity={0.9} />
        </g>
        {/* Cheeks */}
        <ellipse cx={128} cy={248} rx={20} ry={11} fill="#F08A8A" opacity={0.35} />
        <ellipse cx={272} cy={248} rx={20} ry={11} fill="#F08A8A" opacity={0.35} />
        {/* Brows */}
        <rect
          x={128}
          y={152 + pose.browLeftY + browLift}
          width={52}
          height={11}
          rx={5.5}
          fill={HAIR}
          transform={`rotate(${pose.browLeftRot} 154 ${157 + pose.browLeftY + browLift})`}
        />
        <rect
          x={220}
          y={152 + pose.browRightY + browLift}
          width={52}
          height={11}
          rx={5.5}
          fill={HAIR}
          transform={`rotate(${pose.browRightRot} 246 ${157 + pose.browRightY + browLift})`}
        />
        {eye(155)}
        {eye(245)}
        {/* Nose */}
        <path d="M 200 218 Q 192 240 202 244" stroke={SKIN_SHADE} strokeWidth={5} fill="none" strokeLinecap="round" />
        <Mouth open={open} viseme={viseme} smile={pose.smile} />
      </g>
    </svg>
  );
};
