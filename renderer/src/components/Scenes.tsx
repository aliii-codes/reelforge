import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, Layout, Scene, Theme } from "../types";
import { Icon } from "./Icon";
import { EvidenceScene, TerminalScene } from "./Footage";
import { BarsScene, MemeScene, PhotoScene } from "./Graphics";
import { KineticScene } from "./Kinetic";
import { cameraStyle, enterStyle, punchScale, shake } from "./Motion";

// Scene graphics live in the upper "panel". "center" layout: y 210..910 with the big avatar
// below; "focus" layout: y 200..1080 with a small avatar bottom-left. Captions sit at y~1430 and
// the bottom ~380 px stay clear for Reels/Shorts UI.
export const PANEL = { left: 70, top: 210, width: 940, height: 700 };
export const panelFor = (layout: Layout) =>
  layout === "focus" ? { left: 70, top: 200, width: 940, height: 880 } : PANEL;

const clean = (w: string) => w.toLowerCase().replace(/[^a-z0-9%$.]/g, "");

// Cue frames are absolute; inside a scene's <Sequence> useCurrentFrame() is scene-local.
const cueLocal = (scene: Scene, kind: Cue["kind"], index = 0): number | undefined => {
  const c = scene.cues.find((x) => x.kind === kind && x.index === index);
  return c ? c.frame - scene.start_frame : undefined;
};

// Small zoom pulse when an emphasised word (number, key term) is spoken.
const usePunch = (scene: Scene): number => {
  const frame = useCurrentFrame();
  let p = 0;
  for (const c of scene.cues) {
    if (c.kind !== "emphasis") continue;
    const d = frame - (c.frame - scene.start_frame);
    if (d >= 0 && d < 12) p = Math.max(p, Math.sin((d / 12) * Math.PI));
  }
  return 1 + p * 0.035;
};

const Headline: React.FC<{
  text: string;
  emphasis: string[];
  theme: Theme;
  size: number;
  delay?: number;
  align?: "center" | "left";
}> = ({ text, emphasis, theme, size, delay = 0, align = "center" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const emph = new Set(emphasis.map(clean));
  const words = text.split(/\s+/).filter(Boolean);
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: align === "center" ? "center" : "flex-start",
        gap: `0 ${size * 0.26}px`,
        fontFamily: theme.font_family,
        fontWeight: 900,
        fontSize: size,
        lineHeight: 1.08,
        color: theme.text,
        letterSpacing: -1,
      }}
    >
      {words.map((w, i) => {
        const s = spring({ frame: frame - delay - i * 2, fps, config: { damping: 13, stiffness: 160 } });
        const hot = emph.has(clean(w));
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: s,
              transform: `translateY(${(1 - s) * 30}px)`,
              color: hot ? theme.accent : theme.text,
            }}
          >
            {w}
          </span>
        );
      })}
    </div>
  );
};

const Kicker: React.FC<{ text: string; theme: Theme; color?: string }> = ({ text, theme, color }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  if (!text) return null;
  return (
    <div style={{ display: "flex", justifyContent: "center", opacity: o, marginBottom: 28 }}>
      <div
        style={{
          fontFamily: theme.font_family,
          fontWeight: 800,
          fontSize: 34,
          letterSpacing: 4,
          textTransform: "uppercase",
          color: "#0E0B1F",
          background: color ?? theme.accent,
          padding: "10px 26px",
          borderRadius: 999,
        }}
      >
        {text}
      </div>
    </div>
  );
};

const Card: React.FC<{ theme: Theme; children: React.ReactNode; style?: React.CSSProperties }> = ({ theme, children, style }) => (
  <div
    style={{
      background: theme.panel,
      border: "2px solid rgba(255,255,255,0.12)",
      borderRadius: 36,
      padding: "34px 38px",
      boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
      ...style,
    }}
  >
    {children}
  </div>
);

const Sub: React.FC<{ text: string; theme: Theme; delay?: number }> = ({ text, theme, delay = 6 }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame - delay, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  if (!text) return null;
  return (
    <div
      style={{
        opacity: o,
        marginTop: 26,
        fontFamily: theme.font_family,
        fontWeight: 600,
        fontSize: 42,
        lineHeight: 1.25,
        color: theme.muted,
        textAlign: "center",
      }}
    >
      {text}
    </div>
  );
};

const HookScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => (
  <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
    <Kicker text={scene.subtext} theme={theme} />
    <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={98} />
  </div>
);

const ExplainScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 12 } });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
      <div
        style={{
          transform: `scale(${s}) rotate(${(1 - s) * -12}deg)`,
          background: theme.panel,
          borderRadius: 44,
          padding: 26,
          marginBottom: 38,
          border: `3px solid ${theme.accent}66`,
          boxShadow: `0 0 60px ${theme.accent}44`,
        }}
      >
        <Icon name={scene.icon} size={150} color={theme.text} accent={theme.accent} />
      </div>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={78} delay={4} />
      <Sub text={scene.subtext} theme={theme} />
    </div>
  );
};

const formatNumber = (v: number, decimals: number) =>
  v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const StatScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const stat = scene.stat;
  const at = cueLocal(scene, "count") ?? 4;
  const p = spring({ frame: frame - at, fps, config: { damping: 30, stiffness: 70 }, durationInFrames: 22 });
  const pop = spring({ frame: frame - at, fps, config: { damping: 9, stiffness: 220 } });
  const value = stat ? stat.value * p : 0;
  const bar = interpolate(frame - at, [0, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const text = stat ? `${stat.prefix}${formatNumber(value, stat.decimals)}${stat.suffix}` : scene.headline;
  const fontSize = Math.min(240, (PANEL.width * 1.6) / Math.max(text.length, 1));
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
      {scene.headline && stat ? <Kicker text={scene.headline} theme={theme} /> : null}
      <div
        style={{
          fontFamily: theme.font_family,
          fontWeight: 900,
          fontSize,
          lineHeight: 1,
          color: theme.accent,
          opacity: frame < at ? 0 : 1,
          transform: `scale(${frame < at ? 0.85 : 2.1 - 1.1 * Math.min(1, pop)})`,
          textShadow: `0 0 50px ${theme.accent}66`,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {text}
      </div>
      <div style={{ width: 520 * bar, height: 12, borderRadius: 6, background: theme.accent2, margin: "26px 0 30px" }} />
      {stat ? <Headline text={stat.label} emphasis={scene.emphasis} theme={theme} size={58} delay={4} /> : null}
      <Sub text={scene.subtext} theme={theme} delay={14} />
    </div>
  );
};

const AnalogyScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rightAt = cueLocal(scene, "item", 1) ?? 16;
  const a = spring({ frame: frame - 4, fps, config: { damping: 14 } });
  const b = spring({ frame: frame - rightAt, fps, config: { damping: 14 } });
  const eq = spring({ frame: frame - Math.max(6, rightAt - 6), fps, config: { damping: 10 } });
  const cardText = (t: string) => (
    <div style={{ fontFamily: theme.font_family, fontWeight: 800, fontSize: 48, lineHeight: 1.15, color: theme.text, textAlign: "center" }}>{t}</div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      <Kicker text={scene.subtext || "Think of it like this"} theme={theme} color={theme.accent2} />
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={64} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch", marginTop: 34, gap: 0 }}>
        <Card theme={theme} style={{ opacity: a, transform: `translateX(${(1 - a) * -80}px)` }}>
          {cardText(scene.left ?? "")}
        </Card>
        <div
          style={{
            alignSelf: "center",
            fontFamily: theme.font_family,
            fontWeight: 900,
            fontSize: 90,
            color: theme.accent2,
            transform: `scale(${eq})`,
            lineHeight: 1,
            margin: "6px 0",
          }}
        >
          ≈
        </div>
        <Card theme={theme} style={{ opacity: b, transform: `translateX(${(1 - b) * 80}px)`, borderColor: `${theme.accent2}88` }}>
          {cardText(scene.right ?? "")}
        </Card>
      </div>
    </div>
  );
};

const DiagramScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = scene.items.map((_, i) => cueLocal(scene, "item", i) ?? 6 + i * 12);
  const active = at.reduce((acc, f, i) => (frame >= f ? i : acc), -1);
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={66} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginTop: 34 }}>
        {scene.items.map((item, i) => {
          const s = spring({ frame: frame - at[i], fps, config: { damping: 14 } });
          const hot = i === active;
          return (
            <React.Fragment key={i}>
              {i > 0 ? <div style={{ width: 8, height: 40 * s, background: theme.accent, borderRadius: 4, opacity: s }} /> : null}
              <div
                style={{
                  opacity: Math.max(0.08, s),
                  transform: `scale(${(0.8 + s * 0.2) * (hot ? 1.04 : 1)})`,
                  display: "flex",
                  alignItems: "center",
                  gap: 22,
                  width: 820,
                  background: hot ? `${theme.accent}22` : theme.panel,
                  border: `3px solid ${hot ? theme.accent : "rgba(255,255,255,0.14)"}`,
                  borderRadius: 28,
                  padding: "22px 30px",
                }}
              >
                <div
                  style={{
                    width: 60,
                    height: 60,
                    borderRadius: 30,
                    background: hot ? theme.accent : "rgba(255,255,255,0.18)",
                    color: hot ? "#0E0B1F" : theme.text,
                    fontFamily: theme.font_family,
                    fontWeight: 900,
                    fontSize: 34,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </div>
                <div style={{ fontFamily: theme.font_family, fontWeight: 800, fontSize: 46, color: theme.text, lineHeight: 1.1 }}>
                  {item}
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

// Demonstration: a terminal window whose lines are typed as the narration reaches them.
const DemoScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const win = spring({ frame, fps, config: { damping: 15 } });
  const at = scene.lines.map((_, i) => cueLocal(scene, "line", i) ?? 6 + i * 20);
  const mono = "'Fira Code', 'DejaVu Sans Mono', monospace";
  const color = (line: string) =>
    line.startsWith("$") ? theme.accent : line.startsWith("#") ? theme.muted : line.startsWith("!") ? theme.accent2 : theme.text;
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={62} />
      <div
        style={{
          marginTop: 34,
          transform: `translateY(${(1 - win) * 40}px)`,
          opacity: win,
          background: "#0B0A18",
          border: "2px solid rgba(255,255,255,0.16)",
          borderRadius: 26,
          overflow: "hidden",
          boxShadow: `0 30px 70px rgba(0,0,0,0.45), 0 0 50px ${theme.accent}22`,
        }}
      >
        <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "16px 22px", background: "rgba(255,255,255,0.06)" }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <div key={c} style={{ width: 18, height: 18, borderRadius: 9, background: c }} />
          ))}
          <div style={{ marginLeft: 12, fontFamily: mono, fontSize: 24, color: theme.muted }}>terminal</div>
        </div>
        <div style={{ padding: "22px 30px 30px", minHeight: 330 }}>
          {scene.lines.map((line, i) => {
            const typed = Math.max(0, Math.floor((frame - at[i]) * 1.8));
            if (frame < at[i]) return null;
            const shown = line.slice(0, typed);
            const typing = typed < line.length;
            const isLast = i === at.filter((f) => frame >= f).length - 1;
            return (
              <div key={i} style={{ fontFamily: mono, fontSize: 38, lineHeight: 1.55, color: color(line), whiteSpace: "pre" }}>
                {shown}
                {(typing || isLast) && Math.floor(frame / 8) % 2 === 0 ? <span style={{ color: theme.accent }}>▌</span> : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// Reveal: the key phrase appears word by word exactly as it is spoken.
const RevealScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = scene.headline.split(/\s+/).filter(Boolean);
  const emph = new Set(scene.emphasis.map(clean));
  const size = words.join(" ").length > 34 ? 88 : 104;
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      {scene.subtext ? <Kicker text={scene.subtext} theme={theme} color={theme.accent2} /> : null}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: `4px ${size * 0.26}px`,
          fontFamily: theme.font_family,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1.06,
          letterSpacing: -1,
        }}
      >
        {words.map((w, i) => {
          const at = cueLocal(scene, "word", i) ?? i * 4;
          const s = spring({ frame: frame - at, fps, config: { damping: 12, stiffness: 200 } });
          const hot = emph.has(clean(w)) || /\d/.test(w);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                color: hot ? theme.accent : theme.text,
                opacity: 0.16 + 0.84 * Math.min(1, s),
                transform: `translateY(${(1 - Math.min(1, s)) * 24}px) scale(${0.92 + 0.08 * Math.min(1, s)})`,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const ComparisonScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame: frame - 4, fps, config: { damping: 14 } });
  const b = spring({ frame: frame - (cueLocal(scene, "item", 1) ?? 12), fps, config: { damping: 14 } });
  const col = (label: string, s: number, color: string) => (
    <Card theme={theme} style={{ flex: 1, opacity: s, transform: `translateY(${(1 - s) * 60}px)`, borderColor: `${color}AA`, minHeight: 260, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontFamily: theme.font_family, fontWeight: 800, fontSize: 46, color: theme.text, textAlign: "center", lineHeight: 1.15 }}>{label}</div>
    </Card>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={68} />
      <div style={{ display: "flex", gap: 26, marginTop: 40, alignItems: "stretch" }}>
        {col(scene.left ?? "", a, theme.accent)}
        <div style={{ alignSelf: "center", fontFamily: theme.font_family, fontWeight: 900, fontSize: 52, color: theme.muted }}>vs</div>
        {col(scene.right ?? "", b, theme.accent2)}
      </div>
      <Sub text={scene.subtext} theme={theme} delay={16} />
    </div>
  );
};

const TwistScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 8, stiffness: 200 } });
  const shake = frame < 10 ? Math.sin(frame * 2.6) * (10 - frame) * 1.6 : 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
      <div
        style={{
          fontFamily: theme.font_family,
          fontWeight: 900,
          fontSize: scene.background === "accent" ? 210 : 170,
          // on the accent (pink) background the word must not be pink itself
          color: scene.background === "accent" ? "#FFFFFF" : theme.accent2,
          transform: `translateX(${shake}px) scale(${s})`,
          textShadow: scene.background === "accent" ? "8px 8px 0 #0E0B1F" : `6px 6px 0 ${theme.accent}`,
          lineHeight: 1,
          marginBottom: 36,
        }}
      >
        {scene.subtext || "BUT…"}
      </div>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={74} delay={8} />
    </div>
  );
};

const CtaScene: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - 14, fps, config: { damping: 11 } });
  const pulse = 1 + Math.sin(frame / 6) * 0.025 * s;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
      <Headline text={scene.headline} emphasis={scene.emphasis} theme={theme} size={80} />
      {scene.subtext ? (
        <div
          style={{
            marginTop: 46,
            display: "flex",
            alignItems: "center",
            gap: 20,
            transform: `scale(${s * pulse})`,
            background: theme.accent,
            borderRadius: 999,
            padding: "22px 40px",
            boxShadow: `0 0 50px ${theme.accent}77`,
          }}
        >
          <Icon name="share" size={58} color="#0E0B1F" accent="#0E0B1F" />
          <div style={{ fontFamily: theme.font_family, fontWeight: 900, fontSize: 44, color: "#0E0B1F", lineHeight: 1.1, maxWidth: 680 }}>
            {scene.subtext}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const BODY: Partial<Record<Scene["type"], React.FC<{ scene: Scene; theme: Theme }>>> = {
  hook: HookScene,
  explain: ExplainScene,
  stat: StatScene,
  analogy: AnalogyScene,
  diagram: DiagramScene,
  comparison: ComparisonScene,
  twist: TwistScene,
  cta: CtaScene,
  demo: DemoScene,
  reveal: RevealScene,
};

const FULL_FRAME: Partial<Record<Scene["type"], React.FC<{ scene: Scene; theme: Theme }>>> = {
  kinetic: KineticScene,
  terminal: TerminalScene,
  evidence: EvidenceScene,
  bars: BarsScene,
  photo: PhotoScene,
  meme: MemeScene,
};

export const SceneView: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = enterStyle(scene, frame, fps);
  const camera = cameraStyle(scene, frame, fps);
  const punch = punchScale(scene, frame);
  // shake on impacts: the flash cut itself, or a number slamming in
  const count = scene.cues.find((c) => c.kind === "count");
  const since = Math.min(
    scene.transition === "flash" ? frame : 99,
    count ? frame - (count.frame - scene.start_frame) : 99,
  );
  const Full = FULL_FRAME[scene.type];
  const panel = panelFor(scene.layout);
  const Body = BODY[scene.type] ?? ExplainScene;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity: enter.opacity,
        transform: `${enter.transform} ${shake(since >= 0 ? since : 99)} ${camera} scale(${punch})`,
        transformOrigin: "50% 42%",
      }}
    >
      {Full ? (
        <Full scene={scene} theme={theme} />
      ) : (
        <div
          style={{
            position: "absolute",
            left: panel.left,
            top: panel.top,
            width: panel.width,
            height: panel.height,
            transform: scene.layout === "focus" ? "scale(1.08)" : "",
          }}
        >
          <Body scene={scene} theme={theme} />
          {scene.source_label ? (
            <div
              style={{
                position: "absolute",
                bottom: -6,
                left: 0,
                right: 0,
                textAlign: "center",
                fontFamily: theme.font_family,
                fontWeight: 600,
                fontSize: 26,
                color: "rgba(255,255,255,0.62)",
              }}
            >
              Source: {scene.source_label}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};
