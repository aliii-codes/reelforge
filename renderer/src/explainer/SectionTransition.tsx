import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";

// How one beat's stage content enters and leaves. Inside a section the canvas "scrolls": the old
// card lifts up and fades while the new one rises from below (the idea continues). A new section
// slides sideways (a new idea). The twist snaps in with a small scale. A beat that continues the
// same visual (`continued`) doesn't animate at all, so diagrams stay put while labels change.
export const ENTER_FRAMES = 10;
export const EXIT_FRAMES = 8;

export type Move = "cut" | "slide" | "wipe" | "pop";

const ease = { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) } as const;

export const SectionTransition: React.FC<{
  enter: Move;
  exit: Move | "none";
  continued: boolean;
  durationInFrames: number; // beat length, excluding the exit tail
  children: React.ReactNode;
}> = ({ enter, exit, continued, durationInFrames, children }) => {
  const f = useCurrentFrame();
  let tx = 0;
  let ty = 0;
  let sc = 1;
  let op = 1;
  if (!continued) {
    const t = interpolate(f, [0, ENTER_FRAMES], [0, 1], ease);
    if (enter === "slide") {
      tx = (1 - t) * 320;
      op = t;
    } else if (enter === "wipe" || enter === "pop") {
      sc = 0.86 + 0.14 * t;
      op = Math.min(1, t * 1.6);
    } else {
      ty = (1 - t) * 90;
      op = Math.min(1, t * 1.4);
    }
  }
  if (exit !== "none" && f >= durationInFrames) {
    const t = interpolate(f - durationInFrames, [0, EXIT_FRAMES], [0, 1], { ...ease, easing: Easing.in(Easing.cubic) });
    if (exit === "slide") tx -= t * 320;
    else if (exit === "wipe" || exit === "pop") sc *= 1 - 0.1 * t;
    else ty -= t * 110;
    op *= 1 - t;
  }
  if (op <= 0.001) return null;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: op, transform: `translate(${tx}px, ${ty}px) scale(${sc})`, transformOrigin: "50% 40%" }}>
      {children}
    </div>
  );
};
