// Footage scenes: REAL terminal output recorded with `reelforge capture-terminal`, and REAL
// screenshots of cited sources. Both carry an on-screen provenance label.
import React from "react";
import { Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { EvidenceMeta, Scene, TerminalMeta, Theme } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const MONO = "'Fira Code', 'DejaVu Sans Mono', monospace";

const niceDate = (iso?: string) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};

const Badge: React.FC<{ text: string; theme: Theme; light?: boolean }> = ({ text, theme, light }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 18px",
      borderRadius: 999,
      background: light ? "rgba(14,11,31,0.86)" : "rgba(255,255,255,0.1)",
      border: `1.5px solid ${light ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.18)"}`,
      fontFamily: theme.font_family,
      fontWeight: 700,
      fontSize: 24,
      letterSpacing: 0.5,
      color: "#FFFFFF",
    }}
  >
    <span style={{ width: 10, height: 10, borderRadius: 5, background: theme.accent }} />
    {text}
  </div>
);

export const TerminalScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = scene.meta as unknown as TerminalMeta;
  const abs = frame + scene.start_frame;
  const steps = meta.cast.steps;
  const timing = meta.timing;
  const lineH = 54;
  const want = (meta.highlight || "").toLowerCase();

  // Lay out every line that will exist, so the camera can aim at the highlighted one.
  type Row = { kind: "cmd" | "out"; text: string; step: number; at: number; idx: number };
  const rows: Row[] = [];
  steps.forEach((st, k) => {
    rows.push({ kind: "cmd", text: st.command, step: k, at: timing[k].type_start, idx: 0 });
    st.output.forEach((line, i) => rows.push({ kind: "out", text: line, step: k, at: timing[k].out_at + i * 2, idx: i }));
  });
  const visible = rows.filter((r) => abs >= r.at);
  const hiRow = rows.findIndex((r) => r.kind === "out" && want && r.text.toLowerCase().includes(want));
  const hiCue = scene.cues.find((c) => c.kind === "highlight");
  const hiAt = hiCue ? hiCue.frame - scene.start_frame : 99999;
  const zoom = interpolate(frame - hiAt, [0, 14], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  // keep the newest line in view (window shows ~13 lines), then zoom towards the highlighted line
  const scrollRows = Math.max(0, visible.length - 13);
  const focusY = hiRow >= 0 ? 120 + (hiRow - scrollRows) * lineH : 400;
  const win = spring({ frame, fps, config: { damping: 16 } });

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div
        style={{
          position: "absolute",
          top: 190,
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: theme.font_family,
          fontWeight: 900,
          fontSize: 54,
          color: theme.text,
          opacity: win,
        }}
      >
        {scene.headline}
      </div>
      <div
        style={{
          position: "absolute",
          left: 40,
          right: 40,
          top: 290,
          height: Math.min(880, 150 + Math.min(rows.length, 13) * lineH),
          borderRadius: 28,
          overflow: "hidden",
          background: "#0C0D12",
          border: "2px solid rgba(255,255,255,0.12)",
          boxShadow: `0 40px 90px rgba(0,0,0,0.55), 0 0 60px ${theme.accent}18`,
          transform: `translateY(${(1 - win) * 50}px)`,
          opacity: win,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "18px 24px", background: "#1A1B22" }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <div key={c} style={{ width: 20, height: 20, borderRadius: 10, background: c }} />
          ))}
          <div style={{ marginLeft: 14, fontFamily: MONO, fontSize: 24, color: "#8B8DA3" }}>~/{meta.cast.cwd}</div>
        </div>
        <div
          style={{
            padding: "26px 30px",
            transformOrigin: `0% ${focusY}px`,
            transform: `translateY(${-scrollRows * lineH}px) scale(${1 + 0.07 * zoom})`,
          }}
        >
          {visible.map((r, i) => {
            const isHi = rows.indexOf(r) === hiRow && frame >= hiAt;
            if (r.kind === "cmd") {
              const t = timing[r.step];
              const n = Math.round(interpolate(abs, [t.type_start, t.type_end], [0, r.text.length], clamp));
              const typing = abs < t.type_end;
              return (
                <div key={i} style={{ fontFamily: MONO, fontSize: 32, lineHeight: `${lineH}px`, color: "#E8E9F3", whiteSpace: "pre" }}>
                  <span style={{ color: theme.accent }}>$ </span>
                  {r.text.slice(0, n)}
                  {typing || (r.step === steps.length - 1 && abs < t.out_at) ? (
                    <span style={{ color: theme.accent, opacity: Math.floor(frame / 6) % 2 ? 0 : 1 }}>▋</span>
                  ) : null}
                </div>
              );
            }
            const sweep = isHi ? interpolate(frame - hiAt, [0, 8], [0, 100], clamp) : 0;
            return (
              <div
                key={i}
                style={{
                  fontFamily: MONO,
                  fontSize: 32,
                  lineHeight: `${lineH}px`,
                  whiteSpace: "pre",
                  color: isHi && sweep > 60 ? "#0E0B1F" : isHi ? "#FFFFFF" : "#B9BCD0",
                  background: isHi
                    ? `linear-gradient(90deg, ${theme.accent} ${sweep}%, transparent ${sweep}%)`
                    : "transparent",
                  borderRadius: 8,
                  padding: "0 8px",
                  margin: "0 -8px",
                  fontWeight: isHi ? 700 : 400,
                }}
              >
                {r.text}
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ position: "absolute", top: 290 + Math.min(880, 150 + Math.min(rows.length, 13) * lineH) + 28, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: win }}>
        <Badge text={`Real output · recorded on this laptop · ${niceDate(meta.cast.recorded_at)}`} theme={theme} />
      </div>
    </div>
  );
};

export const EvidenceScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = scene.meta as unknown as EvidenceMeta;
  const land = spring({ frame, fps, config: { damping: 15, stiffness: 120 } });
  const hiCue = scene.cues.find((c) => c.kind === "highlight");
  const hiAt = hiCue ? hiCue.frame - scene.start_frame : 12;

  if (!scene.asset || meta.fallback || !meta.rects?.length) {
    // Honest fallback: a quote card, clearly not a screenshot.
    return (
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 900, padding: "56px 60px", background: "#FFFFFF", borderRadius: 32, transform: `scale(${0.9 + 0.1 * land})`, opacity: land, boxShadow: "0 30px 70px rgba(0,0,0,0.25)" }}>
          <div style={{ fontFamily: "Georgia, serif", fontSize: 140, lineHeight: 0.6, color: theme.accent2 }}>“</div>
          <div style={{ fontFamily: "Georgia, serif", fontSize: 50, lineHeight: 1.3, color: "#1D1D1F" }}>{meta.quote}</div>
          <div style={{ marginTop: 30, fontFamily: theme.font_family, fontSize: 28, fontWeight: 700, color: "#6E6E73" }}>
            Quoted from {meta.domain}
          </div>
        </div>
      </div>
    );
  }

  // Screenshot is width x height (1080 x 1800). Show it at 960 px wide in a browser frame, then
  // move the camera onto the cited sentence.
  const scale0 = 960 / (meta.width || 1080);
  const rects = meta.rects;
  const minX = Math.min(...rects.map((r) => r.x));
  const maxX = Math.max(...rects.map((r) => r.x + r.w));
  const minY = Math.min(...rects.map((r) => r.y));
  const maxY = Math.max(...rects.map((r) => r.y + r.h));
  const cx = ((minX + maxX) / 2) * scale0;
  const cy = ((minY + maxY) / 2) * scale0;
  const viewW = 960;
  const viewH = 1030;
  const targetZoom = Math.min(2.4, Math.max(1.0, (viewW * 0.92) / Math.max((maxX - minX) * scale0, 1)));
  const t = interpolate(frame, [4, hiAt + 16], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const zoom = 1 + (targetZoom - 1) * t;
  // Aim at the quote, but keep its first characters in view and never pan past the image edges.
  const imgW = viewW;
  const imgH = (meta.height || 1920) * scale0;
  const clampX = (x: number, z: number) => Math.min(0, Math.max(viewW - imgW * z, x));
  const clampY = (y: number, z: number) => Math.min(0, Math.max(viewH - imgH * z, y));
  const leftAligned = 28 - minX * scale0 * zoom;
  const centred = viewW / 2 - cx * zoom;
  const tx = clampX(Math.max(leftAligned, centred), zoom);
  const ty = clampY(viewH * 0.42 - cy * zoom, zoom);
  const startTy = clampY(viewH * 0.42 - cy, 1);
  const curTy = startTy + (ty - startTy) * t;
  const curTx = clampX(tx * t, zoom);
  const sweep = interpolate(frame - hiAt, [0, 10], [0, 1], clamp);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div
        style={{
          position: "absolute",
          left: 60,
          top: 210,
          width: viewW,
          height: viewH + 64,
          borderRadius: 26,
          overflow: "hidden",
          background: "#FFFFFF",
          boxShadow: "0 30px 80px rgba(20,20,40,0.28)",
          transform: `translateY(${(1 - land) * 80}px) rotate(${(1 - land) * 3}deg)`,
          opacity: land,
        }}
      >
        <div style={{ height: 64, display: "flex", alignItems: "center", gap: 14, padding: "0 24px", background: "#F2F2F5", borderBottom: "1px solid #E1E1E6" }}>
          <div style={{ width: 16, height: 16, borderRadius: 8, background: "#C7C7CC" }} />
          <div style={{ flex: 1, height: 40, borderRadius: 20, background: "#FFFFFF", display: "flex", alignItems: "center", padding: "0 18px", fontFamily: theme.font_family, fontSize: 24, color: "#3A3A3C" }}>
            🔒 {meta.domain}
          </div>
        </div>
        <div style={{ position: "relative", width: viewW, height: viewH, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: 0, transformOrigin: "0 0", transform: `translate(${curTx}px, ${curTy}px) scale(${zoom})` }}>
            <Img src={staticFile(scene.asset)} style={{ width: viewW, display: "block" }} />
            {rects.map((r, i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: r.x * scale0 - 4,
                  top: r.y * scale0 - 2,
                  width: (r.w * scale0 + 8) * sweep,
                  height: r.h * scale0 + 4,
                  background: "rgba(255, 214, 10, 0.55)",
                  mixBlendMode: "multiply",
                  borderRadius: 4,
                }}
              />
            ))}
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", top: 1320, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: land }}>
        <Badge text={`Screenshot · ${meta.domain} · ${niceDate(meta.captured_at)}`} theme={theme} light />
      </div>
    </div>
  );
};
