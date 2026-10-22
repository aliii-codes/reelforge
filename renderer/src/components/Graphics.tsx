// Explanatory graphics: bar comparison, the "photo vs JPEG" analogy, and meme text.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { BarsMeta, Scene, Theme } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const local = (scene: Scene, kind: string, index = 0) => {
  const c = scene.cues.find((x) => x.kind === kind && x.index === index);
  return c ? c.frame - scene.start_frame : undefined;
};

const Title: React.FC<{ text: string; theme: Theme; top?: number }> = ({ text, theme, top = 250 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 15 } });
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 60,
        right: 60,
        textAlign: "center",
        fontFamily: theme.font_family,
        fontWeight: 900,
        fontSize: 72,
        lineHeight: 1.05,
        color: theme.text,
        opacity: s,
        transform: `translateY(${(1 - s) * 30}px)`,
      }}
    >
      {text}
    </div>
  );
};

export const BarsScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = scene.meta as unknown as BarsMeta;
  const bars = meta.bars || [];
  const max = Math.max(...bars.map((b) => b.value), 1);
  const min = Math.min(...bars.map((b) => b.value));
  const ratio = min > 0 ? max / min : 0;
  const lastAt = local(scene, "item", bars.length - 1) ?? 20;
  const badge = spring({ frame: frame - lastAt - 10, fps, config: { damping: 9, stiffness: 200 } });
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Title text={scene.headline} theme={theme} />
      <div style={{ position: "absolute", top: 520, left: 80, right: 80, display: "flex", flexDirection: "column", gap: 70 }}>
        {bars.map((b, i) => {
          const at = local(scene, "item", i) ?? 6 + i * 14;
          const g = spring({ frame: frame - at, fps, config: { damping: 18, stiffness: 90 } });
          const last = i === bars.length - 1;
          const color = last ? theme.accent : "#8E8BB8";
          return (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", fontFamily: theme.font_family, fontWeight: 800, fontSize: 44, color: theme.text, marginBottom: 14 }}>
                <span>{b.label}</span>
                <span style={{ color, opacity: g }}>
                  {(b.value * Math.min(1, g)).toFixed(Number.isInteger(b.value) ? 0 : 1)} {meta.suffix}
                </span>
              </div>
              <div style={{ height: 70, borderRadius: 18, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                <div style={{ width: `${(b.value / max) * 100 * Math.min(1, g)}%`, height: "100%", borderRadius: 18, background: color, boxShadow: last ? `0 0 40px ${theme.accent}88` : "none" }} />
              </div>
            </div>
          );
        })}
      </div>
      {ratio >= 1.5 ? (
        <div style={{ position: "absolute", top: 980, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
          <div
            style={{
              transform: `scale(${badge}) rotate(${(1 - badge) * -8}deg)`,
              background: theme.accent2,
              color: "#FFFFFF",
              fontFamily: theme.font_family,
              fontWeight: 900,
              fontSize: 64,
              padding: "14px 40px",
              borderRadius: 999,
            }}
          >
            {Number.isInteger(ratio) ? ratio : ratio.toFixed(1)}× smaller
          </div>
        </div>
      ) : null}
    </div>
  );
};

// One procedural landscape, sampled finely ("original") or coarsely ("compressed"), so the right
// image genuinely is a lower-resolution version of the left one.
const sceneColor = (u: number, v: number): [number, number, number] => {
  const sunD = Math.hypot(u - 0.7, v - 0.28);
  if (sunD < 0.09) return [255, 214, 120];
  const ridge = 0.55 + 0.08 * Math.sin(u * 9) + 0.05 * Math.sin(u * 23 + 1);
  const ridge2 = 0.66 + 0.05 * Math.sin(u * 6 + 2);
  if (v > 0.8) {
    const w = 0.5 + 0.5 * Math.sin(u * 40 + v * 30);
    return [40 + 30 * w, 90 + 40 * w, 150 + 40 * w];
  }
  if (v > ridge2) return [46, 94, 70];
  if (v > ridge) return [92, 104, 150];
  const sky = v / 0.6;
  return [255 - 120 * (1 - sky), 150 + 60 * sky, 200 - 40 * sky].map((x) => Math.max(0, Math.min(255, x))) as [number, number, number];
};

const Pixels: React.FC<{ w: number; h: number; cell: number }> = ({ w, h, cell }) =>
  React.useMemo(() => <PixelGrid w={w} h={h} cell={cell} />, [w, h, cell]);

const PixelGrid: React.FC<{ w: number; h: number; cell: number }> = ({ w, h, cell }) => {
  const cols = Math.ceil(w / cell);
  const rows = Math.ceil(h / cell);
  const out: React.ReactNode[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const [R, G, B] = sceneColor((c + 0.5) / cols, (r + 0.5) / rows);
      out.push(<rect key={`${r}-${c}`} x={c * cell} y={r * cell} width={cell + 0.5} height={cell + 0.5} fill={`rgb(${R | 0},${G | 0},${B | 0})`} />);
    }
  }
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      {out}
    </svg>
  );
};

export const PhotoScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = local(scene, "item", 1) ?? 20;
  const a = spring({ frame: frame - 2, fps, config: { damping: 15 } });
  const b = spring({ frame: frame - at, fps, config: { damping: 13 } });
  const W = 820;
  const H = 400;
  const card = (label: string, cell: number, s: number, accent: string) => (
    <div style={{ opacity: s, transform: `translateY(${(1 - s) * 50}px)` }}>
      <div style={{ borderRadius: 24, overflow: "hidden", border: `4px solid ${accent}`, width: W, height: H }}>
        <Pixels w={W} h={H} cell={cell} />
      </div>
      <div style={{ marginTop: 14, fontFamily: theme.font_family, fontWeight: 800, fontSize: 40, color: theme.text }}>{label}</div>
    </div>
  );
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Title text={scene.headline} theme={theme} top={200} />
      <div style={{ position: "absolute", top: 380, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 34 }}>
        {card(scene.left || "Original", 8, a, "rgba(255,255,255,0.25)")}
        {card(scene.right || "Compressed", 34, b, theme.accent)}
      </div>
    </div>
  );
};

export const MemeScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const top = spring({ frame, fps, config: { damping: 10, stiffness: 220 } });
  const bottomAt = Math.round((scene.end_frame - scene.start_frame) * 0.35);
  const bottom = spring({ frame: frame - bottomAt, fps, config: { damping: 9, stiffness: 240 } });
  const text = (t: string, s: number, y: number) => (
    <div
      style={{
        position: "absolute",
        top: y,
        left: 40,
        right: 40,
        textAlign: "center",
        fontFamily: theme.font_family,
        fontWeight: 900,
        fontSize: 104,
        lineHeight: 1,
        textTransform: "uppercase",
        color: "#FFFFFF",
        WebkitTextStroke: "6px #0B0A16",
        paintOrder: "stroke fill",
        transform: `scale(${0.6 + 0.4 * s})`,
        opacity: Math.min(1, s * 1.5),
      }}
    >
      {t}
    </div>
  );
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {text(scene.headline, top, 250)}
      {scene.subtext ? text(scene.subtext, bottom, 1400) : null}
    </div>
  );
};
