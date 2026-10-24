// The explainer treatments, one per beat (scene.visual, chosen in reelforge/visuals/explainer.py
// from what the narration says). Each renders inside the stage box between the header/tabs and
// the presenter; frame 0 = the beat's first frame. Reveals are tied to the beat's cue frames
// (the word that names a step, the number being said), falling back to an even stagger.
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { BarsMeta, Cue, EvidenceMeta, Scene, TerminalMeta } from "../types";
import { ComparisonPanel, ScaleComparison } from "./ComparisonPanel";
import { ConnectionArrow, DiagramNode } from "./Diagram";
import { InfoCard } from "./InfoCard";
import { KeywordLabel, Note, Pill, RichText } from "./KeywordLabel";
import { StatCallout } from "./StatCallout";
import { StepList } from "./StepProgress";
import { C, card, CYCLE, draw, FONT, hash, MONO, outline, pop, pulse } from "./theme";

export interface VisualProps {
  scene: Scene;
  continued: boolean; // same visual continues from the previous beat: skip its entrance
  handle: string;
}

const cueAt = (s: Scene, kind: Cue["kind"], index = 0): number | undefined => {
  const c = s.cues.find((x) => x.kind === kind && x.index === index);
  return c ? c.frame - s.start_frame : undefined;
};
const dur = (s: Scene) => s.end_frame - s.start_frame;
const staggered = (s: Scene, kind: Cue["kind"], n: number, first = 4): number[] => {
  const step = Math.max(6, Math.min(16, Math.floor((dur(s) * 0.55) / Math.max(n, 1))));
  return Array.from({ length: n }, (_, i) => cueAt(s, kind, i) ?? first + i * step);
};
const emphasisFrames = (s: Scene) => s.cues.filter((c) => c.kind === "emphasis").map((c) => c.frame - s.start_frame);

const Column: React.FC<{ children: React.ReactNode; gap?: number }> = ({ children, gap = 34 }) => (
  <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap }}>{children}</div>
);

const Title: React.FC<{ s: Scene; size?: number; delay?: number }> = ({ s, size = 62, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!s.headline) return null;
  return (
    <div style={{ width: 940 }}>
      <RichText text={s.headline} emphasis={s.emphasis} size={size} align="center" reveal={(i) => pop(frame, delay + i * 2, fps)} />
    </div>
  );
};

const Sticker: React.FC<{ emoji: string; at: number; style?: React.CSSProperties; size?: number }> = ({ emoji, at, style, size = 96 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at, fps);
  if (!emoji) return null;
  return <div style={{ position: "absolute", fontSize: size, lineHeight: 1, transform: `scale(${p}) rotate(${(1 - p) * 40 - 8}deg)`, ...style }}>{emoji}</div>;
};

// ------------------------------------------------------------------ hook / cta / reaction

const Hook: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, 0, fps);
  const words = s.headline.split(/\s+/).filter(Boolean);
  const at = words.map((_, i) => cueAt(s, "word", i) ?? 2 + i * 3);
  return (
    <Column gap={26}>
      {s.subtext ? <Pill text={s.subtext} color={C.purple} textColor={C.white} size={40} rotate={-2} style={{ transform: `scale(${pop(frame, 6, fps)}) rotate(-2deg)` }} /> : null}
      <div style={{ position: "relative", width: 940, ...card(34), padding: "34px 40px", transform: `rotate(-1deg) scale(${0.92 + 0.08 * Math.min(p, 1)})`, opacity: Math.min(1, p * 1.5) }}>
        <RichText text={s.headline} emphasis={s.emphasis} size={s.headline.length > 34 ? 74 : 86} align="center" reveal={(i) => pop(frame, at[i], fps)} />
        <Sticker emoji={s.emoji ?? ""} at={at[at.length - 1] + 6} style={{ right: -30, top: -60 }} />
      </div>
    </Column>
  );
};

const Cta: React.FC<VisualProps> = ({ scene: s, handle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flipAt = Math.round(dur(s) * 0.45);
  const followed = frame >= flipAt;
  const flip = pop(frame, flipAt, fps);
  const top = s.subtext || s.headline;
  const pillText = s.subtext ? s.headline : "";
  return (
    <Column gap={24}>
      <div style={{ width: 940 }}>
        <RichText text={top} emphasis={[]} size={58} align="center" reveal={(i) => pop(frame, 2 + i * 2, fps)} />
      </div>
      {pillText ? (
        <div style={{ maxWidth: 900, background: C.orange, ...outline(22, 6, 4), padding: "8px 26px 2px", fontFamily: FONT, fontWeight: 800, fontSize: 46, lineHeight: 1.15, textAlign: "center", transform: `scale(${pop(frame, 10, fps)}) rotate(-1deg)` }}>
          {pillText} {s.emoji}
        </div>
      ) : null}
      {handle ? (
        <div style={{ display: "flex", alignItems: "center", gap: 30, background: C.white, ...outline(24, 6, 4), padding: "14px 18px 14px 30px", transform: `scale(${pop(frame, 16, fps)})` }}>
          <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 42, color: C.ink }}>{handle}</div>
          <div
            style={{
              fontFamily: FONT,
              fontWeight: 800,
              fontSize: 36,
              padding: "6px 26px 0",
              borderRadius: 16,
              background: followed ? C.white : C.purple,
              color: followed ? C.ink : C.white,
              border: `4px solid ${followed ? C.ink : C.purple}`,
              transform: `scale(${followed ? 0.9 + 0.1 * Math.min(flip, 1.1) : 1})`,
            }}
          >
            {followed ? "Following ✓" : "Follow"}
          </div>
        </div>
      ) : null}
    </Column>
  );
};

const Reaction: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Column gap={22}>
      {s.headline ? (
        <div style={{ transform: `scale(${pop(frame, 0, fps)}) rotate(-2deg)` }}>
          <div style={{ maxWidth: 900, background: C.purple, color: C.white, ...outline(26, 7, 4), padding: "14px 36px 6px", fontFamily: FONT, fontWeight: 800, fontSize: 76, lineHeight: 1.1, textAlign: "center" }}>
            {s.headline}
          </div>
        </div>
      ) : null}
      {s.subtext ? <Pill text={s.subtext} color={C.pink} textColor={C.white} size={48} rotate={2} style={{ transform: `scale(${pop(frame, 10, fps)}) rotate(2deg)` }} /> : null}
    </Column>
  );
};

// ------------------------------------------------------------------ words

const Keyword: React.FC<VisualProps> = ({ scene: s }) => {
  const words = s.headline.split(/\s+/).filter(Boolean);
  const at = words.map((_, i) => cueAt(s, "word", i) ?? 2 + i * 4);
  return (
    <Column>
      <div style={{ width: 960 }}>
        <KeywordLabel text={s.headline} emphasis={s.emphasis} wordAt={(i) => at[Math.min(i, at.length - 1)]} emoji={s.emoji} size={s.headline.length > 30 ? 84 : 100} />
      </div>
    </Column>
  );
};

const CardV: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const hot = emphasisFrames(s)[0];
  return (
    <Column gap={30}>
      <InfoCard emoji={s.emoji || "💡"} headline={s.headline} emphasis={s.emphasis} note={s.subtext} hotAt={hot} tileColor={CYCLE[(s.id.charCodeAt(2) + s.id.charCodeAt(1)) % 3]} />
      {s.items.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 18, justifyContent: "center", width: 940 }}>
          {s.items.map((it, i) => (
            <Pill key={i} text={it} color={C.white} size={40} style={{ transform: `scale(${pop(frame, 12 + i * 5, fps)})` }} />
          ))}
        </div>
      ) : null}
    </Column>
  );
};

const Twist: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, 0, fps);
  const shake = frame < 10 ? Math.sin(frame * 2.7) * (10 - frame) * 1.4 : 0;
  return (
    <Column gap={40}>
      <div style={{ transform: `translateX(${shake}px) scale(${p}) rotate(-3deg)` }}>
        <Pill text={`${s.subtext || "but…"} 😮`} color={C.pink} textColor={C.white} size={92} />
      </div>
      <InfoCard emoji={s.emoji || "⚠️"} headline={s.headline} emphasis={s.emphasis} tileColor={C.yellow} enterAt={8} hotAt={emphasisFrames(s)[0]} />
    </Column>
  );
};

// ------------------------------------------------------------------ processes

const Steps: React.FC<VisualProps> = ({ scene: s }) => {
  const at = staggered(s, "item", s.items.length);
  return (
    <Column gap={28}>
      {s.headline ? <Note text={s.headline} size={56} /> : null}
      <StepList items={s.items} at={at} />
    </Column>
  );
};

const Chain: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = staggered(s, "item", s.items.length);
  const n = s.items.length;
  return (
    <Column>
      <div style={{ width: 940, ...card(32), padding: "28px 34px 36px", transform: `scale(${0.94 + 0.06 * Math.min(1, pop(frame, 0, fps))})` }}>
        {s.headline ? <Note text={`${s.headline} ${s.emoji ?? ""}`} size={50} style={{ marginBottom: 22 }} /> : null}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "22px 14px" }}>
          {s.items.map((it, i) => {
            const p = pop(frame, at[i], fps);
            const last = i === n - 1;
            return (
              <React.Fragment key={i}>
                {i > 0 ? (
                  <svg width={66} height={40} style={{ opacity: p > 0.05 ? 1 : 0 }}>
                    <ConnectionArrow x1={6} y1={20} x2={58} y2={20} p={draw(frame, at[i] - 4, 6)} color={C.purple} width={6} />
                  </svg>
                ) : null}
                <div
                  style={{
                    background: last ? C.pink : C.white,
                    color: last ? C.white : C.ink,
                    ...outline(18, 5, 4),
                    padding: "8px 26px 2px",
                    fontFamily: FONT,
                    fontWeight: 800,
                    fontSize: 50,
                    opacity: Math.min(1, p * 1.5),
                    transform: `scale(${0.8 + 0.2 * Math.min(p, 1.05)})`,
                  }}
                >
                  {it}
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </Column>
  );
};

const Checklist: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = staggered(s, "item", s.items.length, 10);
  return (
    <Column gap={24}>
      {s.headline ? <Pill text={s.headline} color={C.orange} size={42} /> : null}
      <div style={{ width: 900, ...card(28), padding: "26px 32px", display: "flex", flexDirection: "column", gap: 20 }}>
        {s.items.map((it, i) => {
          const on = pop(frame, at[i], fps);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 22, opacity: 0.35 + 0.65 * Math.min(1, on * 1.5) }}>
              <div style={{ width: 58, height: 58, borderRadius: 12, border: `4px solid ${C.ink}`, background: frame >= at[i] ? C.green : C.white, display: "flex", alignItems: "center", justifyContent: "center", color: C.white, fontSize: 40, fontWeight: 800 }}>
                <span style={{ transform: `scale(${on})` }}>✓</span>
              </div>
              <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 50, color: C.ink }}>{it}</div>
            </div>
          );
        })}
      </div>
    </Column>
  );
};

// ------------------------------------------------------------------ diagrams

const Network: React.FC<VisualProps> = ({ scene: s, continued }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const layers = ((s.meta as { layers?: number[] }).layers ?? [3, 4, 4, 2]).slice(0, 4);
  const W = 880;
  const H = 520;
  const labels = s.items.length === layers.length ? s.items : [];
  const t0 = continued ? -200 : 0;
  const step = Math.max(8, Math.min(18, Math.floor((dur(s) * 0.5) / layers.length)));
  const layerAt = layers.map((_, i) => (labels.length ? cueAt(s, "item", i) : undefined) ?? t0 + 4 + i * step);
  const doneAt = layerAt[layerAt.length - 1] + 14;
  const xs = layers.map((_, i) => 80 + (i * (W - 160)) / Math.max(1, layers.length - 1));
  const pos = layers.map((n, li) => Array.from({ length: n }, (_, k) => ({ x: xs[li], y: (labels.length ? 40 : 60) + ((k + 0.5) * (H - (labels.length ? 140 : 120))) / n })));
  // after it's built, a signal travels layer to layer (the "forward pass")
  const sig = frame >= doneAt ? Math.floor((frame - doneAt) / 10) % layers.length : -1;
  const kick = emphasisFrames(s).reduce((m, f) => Math.max(m, pulse(frame, f, 12)), 0);
  return (
    <Column gap={24}>
      {s.headline ? <Note text={`${s.headline} ${s.emoji ?? ""}`} size={54} /> : null}
      <div style={{ ...card(32), padding: 20 }}>
        <svg width={W} height={H}>
          {pos.slice(0, -1).map((col, li) =>
            col.flatMap((a, ai) =>
              pos[li + 1].map((b, bi) => (
                <ConnectionArrow
                  key={`${li}-${ai}-${bi}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  p={draw(frame, layerAt[li + 1] - 6 + ((ai + bi) % 3), 10)}
                  head={false}
                  width={sig === li ? 5 : 3}
                  color={sig === li ? C.orange : "#9EA3B3"}
                  opacity={sig === li ? 1 : 0.7}
                />
              )),
            ),
          )}
          {pos.map((col, li) =>
            col.map((pt, k) => (
              <DiagramNode
                key={`${li}-${k}`}
                x={pt.x}
                y={pt.y}
                r={30}
                color={CYCLE[li % CYCLE.length]}
                p={pop(frame, layerAt[li] + k * 2, fps)}
                active={Math.max(sig === li ? 1 : 0, kick * (hash(li * 10 + k) > 0.5 ? 1 : 0))}
              />
            )),
          )}
          {labels.map((l, li) => (
            <text key={li} x={xs[li]} y={H - 24} textAnchor="middle" fontFamily="'Baloo 2', sans-serif" fontWeight={800} fontSize={l.length > 10 ? 26 : 32} fill={C.ink} opacity={Math.min(1, pop(frame, layerAt[li] + 4, fps))}>
              {l}
            </text>
          ))}
        </svg>
      </div>
    </Column>
  );
};

const Dials: React.FC<VisualProps> = ({ scene: s, continued }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cols = 9;
  const rows = 5;
  const r = 36;
  const gap = 20;
  const t0 = continued ? -200 : 0;
  // the knobs start turning as soon as training is mentioned; spoken key terms give them a nudge
  const amp = interpolate(frame - t0, [8, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const kick = emphasisFrames(s).reduce((m, f) => Math.max(m, pulse(frame, f, 14)), 0);
  const label = ((s.meta as { label?: string }).label ?? "knobs") + " 🎛️";
  const W = cols * (2 * r + gap) - gap;
  return (
    <Column gap={28}>
      <div style={{ position: "relative", ...card(32), padding: "54px 34px 30px" }}>
        <div style={{ position: "absolute", left: 22, top: -30 }}>
          <Pill text={label} color={C.orange} size={40} style={{ transform: `scale(${pop(frame, t0 + 2, fps)})` }} />
        </div>
        <svg width={W} height={rows * (2 * r + gap) - gap}>
          {Array.from({ length: cols * rows }, (_, i) => {
            const cx = (i % cols) * (2 * r + gap) + r;
            const cy = Math.floor(i / cols) * (2 * r + gap) + r;
            const p = pop(frame, t0 + 2 + ((i % cols) + Math.floor(i / cols)) * 1.2, fps);
            const base = hash(i) * 300 - 150;
            const ang = base + amp * 55 * Math.sin(frame / (9 + hash(i + 50) * 9) + hash(i + 99) * 6) + kick * 40 * (hash(i + 7) > 0.5 ? 1 : -1);
            const color = CYCLE[Math.floor(hash(i + 13) * 4)];
            return (
              <g key={i} transform={`translate(${cx} ${cy}) scale(${Math.max(0, p)})`}>
                <circle r={r} fill={color} stroke={C.ink} strokeWidth={4} />
                <circle r={r * 0.55} fill="#FFFFFF" opacity={0.25} />
                <line x1={0} y1={0} x2={0} y2={-r + 7} stroke={C.ink} strokeWidth={6} strokeLinecap="round" transform={`rotate(${ang})`} />
                <circle r={5} fill={C.ink} />
              </g>
            );
          })}
        </svg>
      </div>
      {s.headline ? <Note text={s.headline} size={52} style={{ maxWidth: 940, textAlign: "center", opacity: Math.min(1, pop(frame, 12, fps)) }} /> : null}
    </Column>
  );
};

const DataStream: React.FC<VisualProps> = ({ scene: s, continued }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sources = (s.meta as { sources?: string[] }).sources ?? ["📚", "🌐", "📰", "💬"];
  const t0 = continued ? -200 : 0;
  const box = pop(frame, t0 + 4, fps);
  const belt = 600;
  const n = 5;
  const speed = 5;
  const eat = (frame - t0) * speed;
  const swallow = Math.max(0, Math.sin(((eat % (belt / n)) / (belt / n)) * Math.PI));
  return (
    <Column gap={26}>
      <div style={{ position: "relative", width: 940, height: 300, ...card(32), overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 30, right: 250, top: 196, height: 8, background: C.soft, borderRadius: 4 }} />
        {Array.from({ length: n }, (_, k) => {
          const x = ((eat + (k * belt) / n) % belt) - 40;
          const o = interpolate(x, [-40, 10, belt - 110, belt - 50], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const appear = pop(frame, t0 + k * 3, fps);
          return (
            <div key={k} style={{ position: "absolute", left: 40 + x, top: 100 + Math.sin(k * 1.7) * 14, fontSize: 76, opacity: o * Math.min(1, appear), transform: `scale(${1 - 0.4 * Math.max(0, (x - (belt - 160)) / 110)})` }}>
              {sources[k % sources.length]}
            </div>
          );
        })}
        <div
          style={{
            position: "absolute",
            right: 34,
            top: 50,
            width: 196,
            height: 196,
            background: C.purple,
            ...outline(36, 6, 4),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 120,
            transform: `scale(${box * (1 + 0.04 * swallow)})`,
          }}
        >
          🤖
        </div>
      </div>
      {s.headline ? <Note text={s.headline} size={54} style={{ maxWidth: 940, textAlign: "center" }} /> : null}
    </Column>
  );
};

const Scale: React.FC<VisualProps> = ({ scene: s }) => {
  const meta = s.meta as { ratio?: number; bigger?: "left" | "right" };
  return (
    <Column gap={30}>
      <Title s={s} size={60} />
      <ScaleComparison left={s.left ?? ""} right={s.right ?? ""} ratio={meta.ratio ?? 0.1} bigger={meta.bigger ?? "right"} rightAt={cueAt(s, "item", 1) ?? Math.round(dur(s) * 0.35)} />
    </Column>
  );
};

const Compare: React.FC<VisualProps> = ({ scene: s }) => (
  <Column gap={36}>
    <Title s={s} size={60} />
    <ComparisonPanel
      left={s.left ?? ""}
      right={s.right ?? ""}
      rightAt={cueAt(s, "item", 1) ?? Math.round(dur(s) * 0.35)}
      mode={s.type === "comparison" ? "vs" : "approx"}
      winner={s.type === "comparison" ? "right" : null}
    />
  </Column>
);

const Stat: React.FC<VisualProps> = ({ scene: s }) =>
  s.stat ? (
    <Column>
      <StatCallout stat={s.stat} title={s.headline} at={cueAt(s, "count") ?? 6} dots={!!(s.meta as { dots?: boolean }).dots} emoji={s.emoji} />
    </Column>
  ) : (
    <CardV scene={s} continued={false} handle="" />
  );

const Bars: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = s.meta as unknown as BarsMeta;
  const bars = meta.bars ?? [];
  const max = Math.max(...bars.map((b) => b.value), 1);
  const at = staggered(s, "item", bars.length, 6);
  return (
    <Column gap={26}>
      <Title s={s} size={58} />
      <div style={{ width: 940, ...card(30), padding: "30px 34px", display: "flex", flexDirection: "column", gap: 24 }}>
        {bars.map((b, i) => {
          const g = draw(frame, at[i], 16);
          return (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8, opacity: Math.min(1, pop(frame, at[i] - 2, fps) * 1.5) }}>
              <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 40, color: C.ink }}>{b.label}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <div style={{ height: 56, width: Math.max(12, (b.value / max) * 640 * g), background: CYCLE[i % CYCLE.length], ...outline(14, 4, 4) }} />
                <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 46, color: C.ink }}>
                  {(b.value * g).toLocaleString("en-US", { maximumFractionDigits: 1 })}
                  {meta.suffix}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Column>
  );
};

// ------------------------------------------------------------------ code / terminal / evidence

const TOKEN = /("[^"]*"|'[^']*'|#.*$|\b(?:def|return|for|in|if|else|import|from|class|while|print|const|let|function)\b|\b\d+(?:\.\d+)?\b)/g;
const colorFor = (t: string) =>
  t.startsWith("#") ? C.muted : t.startsWith('"') || t.startsWith("'") ? C.green : /^\d/.test(t) ? C.orange : C.purple;
const highlightCode = (line: string) => {
  const out: React.ReactNode[] = [];
  let last = 0;
  line.replace(TOKEN, (m, _g, off: number) => {
    if (off > last) out.push(line.slice(last, off));
    out.push(<span key={off} style={{ color: colorFor(m), fontWeight: 600 }}>{m}</span>);
    last = off + m.length;
    return m;
  });
  if (last < line.length) out.push(line.slice(last));
  return out;
};

const Window: React.FC<{ title: string; dark?: boolean; children: React.ReactNode; p: number }> = ({ title, dark, children, p }) => (
  <div style={{ width: 940, ...outline(26, 7, 4), overflow: "hidden", background: dark ? "#17151F" : C.paper, opacity: Math.min(1, p * 1.5), transform: `translateY(${(1 - p) * 40}px)` }}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 22px", background: C.white, borderBottom: `4px solid ${C.ink}` }}>
      {[C.pink, C.yellow, C.green].map((c) => (
        <div key={c} style={{ width: 22, height: 22, borderRadius: 11, background: c, border: `3px solid ${C.ink}` }} />
      ))}
      <div style={{ marginLeft: 14, fontFamily: MONO, fontSize: 26, fontWeight: 600, color: C.ink }}>{title}</div>
    </div>
    {children}
  </div>
);

const Code: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = staggered(s, "line", s.lines.length, 6);
  const typedLines = s.lines.map((l, i) => (frame < at[i] ? null : l.slice(0, Math.floor((frame - at[i]) * 1.8))));
  const cur = typedLines.reduce((acc, t, i) => (t !== null ? i : acc), -1);
  return (
    <Column gap={26}>
      <Title s={s} size={58} />
      <Window title="example.py" p={pop(frame, 0, fps)}>
        <div style={{ padding: "20px 24px 26px", minHeight: 300, position: "relative" }}>
          {s.lines.map((_, i) => (
            <div key={i} style={{ display: "flex", fontFamily: MONO, fontSize: 34, lineHeight: 1.6, color: C.ink, whiteSpace: "pre" }}>
              <span style={{ width: 52, color: C.muted, flexShrink: 0 }}>{i + 1}</span>
              <span>{typedLines[i] !== null ? highlightCode(typedLines[i] as string) : ""}</span>
              {i === cur && Math.floor(frame / 9) % 2 === 0 ? <span style={{ color: C.purple }}>▍</span> : null}
            </div>
          ))}
          <div style={{ position: "absolute", right: 20, bottom: 12, fontFamily: FONT, fontSize: 24, color: C.muted }}>illustration</div>
        </div>
      </Window>
    </Column>
  );
};

const niceDate = (iso?: string) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");

const Provenance: React.FC<{ text: string }> = ({ text }) => <Pill text={text} color={C.white} size={28} />;

const Terminal: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = s.meta as unknown as TerminalMeta;
  const steps = meta.cast.steps;
  const want = (meta.highlight || "").toLowerCase();
  const rows: { kind: "cmd" | "out"; text: string; at: number; end: number }[] = [];
  steps.forEach((st, k) => {
    const t = meta.timing[k];
    rows.push({ kind: "cmd", text: st.command, at: t.type_start - s.start_frame, end: t.type_end - s.start_frame });
    st.output.forEach((line, i) => rows.push({ kind: "out", text: line, at: t.out_at - s.start_frame + i * 2, end: 0 }));
  });
  const visible = rows.filter((r) => frame >= r.at);
  const shown = visible.slice(-8);
  return (
    <Column gap={24}>
      <Title s={s} size={56} />
      <Window title={`~/${meta.cast.cwd}`} dark p={pop(frame, 0, fps)}>
        <div style={{ padding: "18px 24px 22px", minHeight: 360 }}>
          {shown.map((r, i) => {
            const typed = r.kind === "cmd" ? r.text.slice(0, Math.max(0, Math.round(((frame - r.at) / Math.max(1, r.end - r.at)) * r.text.length))) : r.text;
            const hot = r.kind === "out" && want && r.text.toLowerCase().includes(want);
            return (
              <div
                key={`${r.at}-${i}`}
                style={{
                  fontFamily: MONO,
                  fontSize: 27,
                  lineHeight: 1.55,
                  whiteSpace: "pre",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  color: r.kind === "cmd" ? "#7DF0C6" : "#E9E8F2",
                  background: hot ? "rgba(255,201,60,0.9)" : "transparent",
                  ...(hot ? { color: C.ink, borderRadius: 6, padding: "0 6px" } : {}),
                }}
              >
                {r.kind === "cmd" ? "$ " : ""}
                {typed}
              </div>
            );
          })}
        </div>
      </Window>
      <Provenance text={`Real output · recorded on this laptop · ${niceDate(meta.cast.recorded_at)}`} />
    </Column>
  );
};

const Evidence: React.FC<VisualProps> = ({ scene: s }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meta = s.meta as unknown as EvidenceMeta;
  const p = pop(frame, 0, fps);
  if (!s.asset || meta.fallback || !meta.rects?.length) {
    return (
      <Column gap={24}>
        <div style={{ width: 920, ...card(30), padding: "40px 44px", opacity: Math.min(1, p * 1.5), transform: `scale(${0.94 + 0.06 * Math.min(p, 1)})` }}>
          <div style={{ fontFamily: "Georgia, serif", fontSize: 48, lineHeight: 1.3, color: C.ink }}>“{meta.quote}”</div>
        </div>
        <Provenance text={`Quoted from ${meta.domain}`} />
      </Column>
    );
  }
  const viewW = 900;
  const viewH = 560;
  const sc = viewW / (meta.width || 1080);
  const rects = meta.rects;
  const minY = Math.min(...rects.map((r) => r.y));
  const maxY = Math.max(...rects.map((r) => r.y + r.h));
  const imgH = (meta.height || 1920) * sc;
  const offY = Math.max(0, Math.min(imgH - viewH, ((minY + maxY) / 2) * sc - viewH / 2));
  const hi = (s.cues.find((c) => c.kind === "highlight")?.frame ?? s.start_frame + 14) - s.start_frame;
  return (
    <Column gap={24}>
      <div style={{ width: viewW, ...outline(26, 7, 4), overflow: "hidden", background: C.white, opacity: Math.min(1, p * 1.5), transform: `translateY(${(1 - p) * 40}px)` }}>
        <div style={{ padding: "12px 22px", borderBottom: `4px solid ${C.ink}`, fontFamily: FONT, fontWeight: 700, fontSize: 28, color: C.ink }}>🔒 {meta.domain}</div>
        <div style={{ position: "relative", width: viewW, height: viewH, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: -offY, width: viewW }}>
            <Img src={staticFile(s.asset)} style={{ width: viewW, display: "block" }} />
            {rects.map((r, i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: r.x * sc - 4,
                  top: r.y * sc - 2,
                  height: r.h * sc + 4,
                  width: (r.w * sc + 8) * draw(frame, hi + i * 3, 10),
                  background: "rgba(255,138,76,0.45)",
                  borderRadius: 4,
                }}
              />
            ))}
          </div>
        </div>
      </div>
      <Provenance text={`Screenshot · ${meta.domain} · ${niceDate(meta.captured_at)}`} />
    </Column>
  );
};

export const VISUALS: Record<string, React.FC<VisualProps>> = {
  hook: Hook,
  card: CardV,
  keyword: Keyword,
  steps: Steps,
  chain: Chain,
  network: Network,
  dials: Dials,
  datastream: DataStream,
  checklist: Checklist,
  stat: Stat,
  scale: Scale,
  compare: Compare,
  twist: Twist,
  code: Code,
  terminal: Terminal,
  evidence: Evidence,
  bars: Bars,
  cta: Cta,
  reaction: Reaction,
};
