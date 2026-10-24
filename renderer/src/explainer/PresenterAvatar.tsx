import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { AvatarTrack, Expression, Pose, Viseme } from "../types";
import { C, mix, pulse } from "./theme";

// "Forge", explainer edition: an original flat, outlined presenter drawn entirely in SVG.
// Mouth opening follows the narration loudness envelope and a coarse viseme guess (computed in
// Python); blinks, brow raises and nods come from the same audio-derived track. Arms take one of
// a few poses per beat (point at the diagram, think, wave, shrug) and blend between them.

const HAIR = "#2B2238";
const HOODIE = C.purple;
const HOODIE_DARK = "#5233D9";
const STROKE = 7;

interface Face {
  browL: number;
  browR: number;
  rotL: number;
  rotR: number;
  eyeY: number;
  pdx: number;
  pdy: number;
  smile: number;
}
const FACES: Record<Expression, Face> = {
  neutral: { browL: 0, browR: 0, rotL: 0, rotR: 0, eyeY: 1, pdx: 0, pdy: 0, smile: 9 },
  happy: { browL: -6, browR: -6, rotL: 4, rotR: -4, eyeY: 0.7, pdx: 0, pdy: 2, smile: 18 },
  surprised: { browL: -15, browR: -15, rotL: -5, rotR: 5, eyeY: 1.15, pdx: 0, pdy: 0, smile: 0 },
  thoughtful: { browL: -11, browR: 3, rotL: -8, rotR: 6, eyeY: 0.92, pdx: 6, pdy: -7, smile: 3 },
  skeptical: { browL: 4, browR: -12, rotL: 9, rotR: -7, eyeY: 0.86, pdx: -5, pdy: 0, smile: -4 },
};
const blendFace = (a: Face, b: Face, t: number): Face => ({
  browL: mix(a.browL, b.browL, t),
  browR: mix(a.browR, b.browR, t),
  rotL: mix(a.rotL, b.rotL, t),
  rotR: mix(a.rotR, b.rotR, t),
  eyeY: mix(a.eyeY, b.eyeY, t),
  pdx: mix(a.pdx, b.pdx, t),
  pdy: mix(a.pdy, b.pdy, t),
  smile: mix(a.smile, b.smile, t),
});

// Arm = [upper-arm angle, forearm angle] in degrees (0 = right, 90 = down), per side.
type Arms = { r: [number, number]; l: [number, number] };
const DOWN: Arms = { r: [84, 90], l: [96, 90] };
const POSES: Record<Pose, Arms> = {
  idle: DOWN,
  point: { r: [-35, -60], l: DOWN.l },
  think: { r: [135, -95], l: DOWN.l },
  wave: { r: [-45, -80], l: DOWN.l },
  shrug: { r: [20, -55], l: [160, -125] },
};
const SHOULDER = { r: [292, 352], l: [108, 352] } as const;
// A lowered arm hangs at the side, behind the torso; a raised one is drawn in front.
const raised = (sy: number, a: [number, number]) => sy + 78 * Math.sin(rad(a[0])) + 84 * Math.sin(rad(a[1])) < sy + 90;
const lerpArms = (a: Arms, b: Arms, t: number): Arms => ({
  r: [mix(a.r[0], b.r[0], t), mix(a.r[1], b.r[1], t)],
  l: [mix(a.l[0], b.l[0], t), mix(a.l[1], b.l[1], t)],
});
// Gestures that shouldn't be held for a whole long beat relax after this many frames.
const GESTURE_HOLD: Partial<Record<Pose, number>> = { point: 60, wave: 50, shrug: 45 };

const rad = (d: number) => (d * Math.PI) / 180;

const Arm: React.FC<{ sx: number; sy: number; a: [number, number]; finger: boolean }> = ({ sx, sy, a, finger }) => {
  const ex = sx + 78 * Math.cos(rad(a[0]));
  const ey = sy + 78 * Math.sin(rad(a[0]));
  const hx = ex + 84 * Math.cos(rad(a[1]));
  const hy = ey + 84 * Math.sin(rad(a[1]));
  const fx = hx + 26 * Math.cos(rad(a[1]));
  const fy = hy + 26 * Math.sin(rad(a[1]));
  const d = `M ${sx} ${sy} L ${ex} ${ey} L ${hx} ${hy}`;
  return (
    <g>
      <path d={d} stroke={C.ink} strokeWidth={36} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d={d} stroke={HOODIE} strokeWidth={22} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      {finger ? (
        <>
          <line x1={hx} y1={hy} x2={fx} y2={fy} stroke={C.ink} strokeWidth={15} strokeLinecap="round" />
          <line x1={hx} y1={hy} x2={fx} y2={fy} stroke={C.skin} strokeWidth={6} strokeLinecap="round" />
        </>
      ) : null}
      <circle cx={hx} cy={hy} r={17} fill={C.skin} stroke={C.ink} strokeWidth={5} />
    </g>
  );
};

const MOUTH_W: Record<Viseme, number> = { rest: 40, mbp: 38, ee: 54, aa: 46, oo: 28, fv: 44 };

const Mouth: React.FC<{ open: number; viseme: Viseme; smile: number }> = ({ open, viseme, smile }) => {
  const cx = 200;
  const cy = 242;
  if (open <= 0.06 || viseme === "mbp" || viseme === "rest") {
    const w = 42;
    return (
      <path d={`M ${cx - w / 2} ${cy} Q ${cx} ${cy + smile} ${cx + w / 2} ${cy}`} stroke={C.ink} strokeWidth={6} strokeLinecap="round" fill="none" />
    );
  }
  const w = MOUTH_W[viseme];
  const h = (viseme === "oo" ? 16 : 8) + open * (viseme === "ee" || viseme === "fv" ? 20 : 34);
  const top = cy - h * 0.3;
  const bot = cy + h * 0.7;
  const d = `M ${cx - w / 2} ${cy} C ${cx - w / 2} ${top - 3}, ${cx + w / 2} ${top - 3}, ${cx + w / 2} ${cy}
    C ${cx + w / 2} ${bot + 5}, ${cx - w / 2} ${bot + 5}, ${cx - w / 2} ${cy} Z`;
  return (
    <g>
      <clipPath id="pMouth">
        <path d={d} />
      </clipPath>
      <path d={d} fill="#4A1726" />
      <g clipPath="url(#pMouth)">
        {h > 12 && viseme !== "oo" ? <rect x={cx - w / 2} y={top - 6} width={w} height={Math.min(9, h * 0.26) + 6} fill="#FFFFFF" /> : null}
        {h > 16 ? <ellipse cx={cx} cy={bot + 3} rx={w * 0.3} ry={h * 0.28} fill="#E36A7E" /> : null}
      </g>
      <path d={d} fill="none" stroke={C.ink} strokeWidth={5} strokeLinejoin="round" />
    </g>
  );
};

export interface Placement {
  x: number; // centre x of the character
  y: number; // top of the character box
  size: number; // box width (height = 1.2 * size)
  lookX: number;
  lookY: number;
}

export const PresenterAvatar: React.FC<{
  track: AvatarTrack;
  expression: Expression;
  prevExpression: Expression;
  pose: Pose;
  prevPose: Pose;
  beatStart: number;
  beatEnd: number;
  placement: Placement;
}> = ({ track, expression, prevExpression, pose, prevPose, beatStart, beatEnd, placement }) => {
  const frame = useCurrentFrame();
  const idx = Math.min(Math.max(frame, 0), Math.max(0, track.mouth_open.length - 1));
  const open = track.mouth_open.length ? track.mouth_open[idx] : 0;
  const viseme: Viseme = track.visemes.length ? track.visemes[idx] : "rest";
  const local = frame - beatStart;

  const face = blendFace(FACES[prevExpression], FACES[expression], interpolate(local, [0, 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));

  // Arms: blend from the previous beat's pose; gestures relax back down after a while.
  const hold = GESTURE_HOLD[pose];
  const longBeat = beatEnd - beatStart > (hold ?? 0) + 24;
  const prevArms = POSES[prevPose] ?? DOWN;
  let arms = lerpArms(prevArms, POSES[pose] ?? DOWN, interpolate(local, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  if (hold && longBeat) arms = lerpArms(arms, DOWN, interpolate(local, [hold, hold + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  if (pose === "wave") {
    const w = Math.sin(local / 3.2) * 16 * interpolate(local, [0, 6, 40, 50], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    arms = { ...arms, r: [arms.r[0], arms.r[1] + w] };
  }

  let blink = 1;
  for (const b of track.blink_frames) {
    const d = frame - b;
    if (d >= 0 && d < 5) {
      blink = [0.45, 0.08, 0.08, 0.45, 0.85][d];
      break;
    }
  }
  let lift = 0;
  for (const f of track.emphasis_frames ?? []) lift = Math.max(lift, pulse(frame, f, 14));
  let nodP = 0;
  for (const f of track.nod_frames ?? []) nodP = Math.max(nodP, pulse(frame, f, 12));

  const sway = Math.sin(frame / 24) * 1.4 + lift * 2.5 + (pose === "think" ? 5 : 0);
  const nod = open * 3 + nodP * 7;
  const breathe = Math.sin(frame / 32) * 2;

  const eye = (x: number) => (
    <g transform={`translate(${x} 184) scale(1 ${face.eyeY * blink}) translate(${-x} -184)`}>
      <ellipse cx={x} cy={184} rx={20} ry={23} fill="#FFFFFF" stroke={C.ink} strokeWidth={5} />
      <circle cx={x + face.pdx + placement.lookX} cy={186 + face.pdy + placement.lookY} r={10} fill={C.ink} />
      <circle cx={x + face.pdx + placement.lookX + 3} cy={182 + face.pdy + placement.lookY} r={3.5} fill="#FFFFFF" />
    </g>
  );
  const brow = (x: number, dy: number, rot: number) => (
    <path
      d={`M ${x - 22} ${150 + dy - lift * 8} Q ${x} ${142 + dy - lift * 8} ${x + 22} ${150 + dy - lift * 8}`}
      stroke={C.ink}
      strokeWidth={9}
      strokeLinecap="round"
      fill="none"
      transform={`rotate(${rot} ${x} ${148 + dy})`}
    />
  );
  const w = placement.size;
  return (
    <svg
      width={w}
      height={w * 1.2}
      viewBox="0 0 400 480"
      style={{ position: "absolute", left: placement.x - w / 2, top: placement.y, overflow: "visible" }}
    >
      <defs>
        <linearGradient id="pFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0.8" stopColor="#fff" stopOpacity={1} />
          <stop offset="0.985" stopColor="#fff" stopOpacity={0} />
        </linearGradient>
        <mask id="pMask" maskUnits="userSpaceOnUse" x={-200} y={-100} width={800} height={580}>
          <rect x={-200} y={-100} width={800} height={580} fill="url(#pFade)" />
        </mask>
      </defs>
      <g mask="url(#pMask)">
        {raised(SHOULDER.l[1], arms.l) ? null : <Arm sx={SHOULDER.l[0]} sy={SHOULDER.l[1]} a={arms.l} finger={false} />}
        {raised(SHOULDER.r[1], arms.r) ? null : <Arm sx={SHOULDER.r[0]} sy={SHOULDER.r[1]} a={arms.r} finger={false} />}
        {/* body */}
        <g transform={`translate(0 ${breathe * 0.5 + nod * 0.3})`}>
          <rect x={178} y={262} width={44} height={50} fill={C.skinShade} stroke={C.ink} strokeWidth={STROKE} />
          <path d="M 58 500 C 62 384, 112 318, 200 314 C 288 318, 338 384, 342 500 Z" fill={HOODIE} stroke={C.ink} strokeWidth={STROKE} strokeLinejoin="round" />
          <path d="M 138 322 C 156 366, 244 366, 262 322 C 240 338, 160 338, 138 322 Z" fill={HOODIE_DARK} stroke={C.ink} strokeWidth={5} strokeLinejoin="round" />
          {/* headphones around the neck */}
          <path d="M 126 314 C 132 356, 268 356, 274 314" stroke={C.ink} strokeWidth={17} fill="none" strokeLinecap="round" />
          <path d="M 126 314 C 132 356, 268 356, 274 314" stroke={C.orange} strokeWidth={9} fill="none" strokeLinecap="round" />
          <line x1={184} y1={360} x2={180} y2={418} stroke={C.white} strokeWidth={6} strokeLinecap="round" />
          <line x1={216} y1={360} x2={220} y2={418} stroke={C.white} strokeWidth={6} strokeLinecap="round" />
          <circle cx={262} cy={404} r={16} fill={C.yellow} stroke={C.ink} strokeWidth={4} />
          <path d="M 264 393 L 256 406 L 263 406 L 260 416 L 269 402 L 262 402 Z" fill={C.ink} />
        </g>
        {/* head */}
        <g transform={`rotate(${sway} 200 300) translate(0 ${nod})`}>
          <circle cx={103} cy={190} r={19} fill={C.skin} stroke={C.ink} strokeWidth={STROKE} />
          <circle cx={297} cy={190} r={19} fill={C.skin} stroke={C.ink} strokeWidth={STROKE} />
          <ellipse cx={200} cy={180} rx={98} ry={106} fill={C.skin} stroke={C.ink} strokeWidth={STROKE} />
          <path
            d="M 100 172 C 88 84, 158 52, 214 56 C 274 60, 318 100, 302 174 C 292 134, 262 114, 228 118 C 198 122, 170 110, 152 96 C 142 128, 122 152, 100 172 Z"
            fill={HAIR}
            stroke={C.ink}
            strokeWidth={6}
            strokeLinejoin="round"
          />
          <path d="M 196 72 C 230 70, 266 84, 284 108" stroke={C.purple} strokeWidth={7} strokeLinecap="round" fill="none" />
          <ellipse cx={142} cy={222} rx={17} ry={9} fill="#F07A86" opacity={0.45} />
          <ellipse cx={258} cy={222} rx={17} ry={9} fill="#F07A86" opacity={0.45} />
          {brow(160, face.browL, face.rotL)}
          {brow(240, face.browR, face.rotR)}
          {eye(160)}
          {eye(240)}
          <path d="M 198 196 Q 190 216 202 220" stroke={C.skinShade} strokeWidth={5} fill="none" strokeLinecap="round" />
          <Mouth open={open} viseme={viseme} smile={face.smile} />
          {expression === "skeptical" ? (
            <path d="M 302 118 C 292 136, 296 148, 306 148 C 316 148, 318 136, 302 118 Z" fill="#7CC7F5" stroke={C.ink} strokeWidth={4} />
          ) : null}
        </g>
        {raised(SHOULDER.l[1], arms.l) ? <Arm sx={SHOULDER.l[0]} sy={SHOULDER.l[1]} a={arms.l} finger={false} /> : null}
        {raised(SHOULDER.r[1], arms.r) ? <Arm sx={SHOULDER.r[0]} sy={SHOULDER.r[1]} a={arms.r} finger={pose === "point"} /> : null}
      </g>
    </svg>
  );
};
