// Mirror of reelforge/visuals/scene_manifest.py (SceneManifest). The Python side validates
// the manifest with Pydantic before it reaches Remotion; keep the two in sync.

export type SceneType =
  | "hook"
  | "explain"
  | "stat"
  | "analogy"
  | "diagram"
  | "comparison"
  | "twist"
  | "cta"
  | "demo"
  | "reveal"
  | "kinetic"
  | "terminal"
  | "evidence"
  | "bars"
  | "meme"
  | "photo";

export type Expression = "neutral" | "surprised" | "thoughtful" | "happy" | "skeptical";
export type Transition = "fade" | "slide" | "pop" | "wipe" | "cut" | "whip" | "zoom" | "flash";
export type BackgroundMode = "grid" | "glow" | "accent" | "terminal" | "paper";
export type Camera = "none" | "push" | "drift" | "punch" | "track";
export type AvatarMode = "hidden" | "center" | "corner" | "reaction";
export type Viseme = "rest" | "mbp" | "ee" | "aa" | "oo" | "fv";
export type Layout = "center" | "focus";
export type CueKind = "emphasis" | "item" | "count" | "word" | "line" | "output" | "highlight";

// A visual change inside a scene, at the absolute frame its word is spoken.
export interface Cue {
  frame: number;
  kind: CueKind;
  index: number;
}

export interface SfxCue {
  frame: number;
  kind: "whoosh" | "tick" | "impact" | "riser" | "pop" | "keys" | "shutter";
  duration_frames: number;
}

export interface MusicCue {
  frame: number;
  kind: "drop" | "return";
}

// Per-type scene data (scene.meta), produced by the Python planner.
export interface CastStep {
  command: string;
  output: string[];
  exit_code: number;
  seconds: number;
}
export interface TerminalMeta {
  cast: { recorded_at: string; host: string; cwd: string; steps: CastStep[] };
  timing: { type_start: number; type_end: number; out_at: number }[];
  highlight: string;
}
export interface EvidenceMeta {
  rects?: { x: number; y: number; w: number; h: number }[];
  width?: number;
  height?: number;
  captured_at?: string;
  title?: string;
  quote: string;
  domain: string;
  fallback?: boolean;
}
export interface KineticMeta {
  phrases: { words: { text: string; frame: number; emph: boolean }[] }[];
}
export interface BarsMeta {
  bars: { label: string; value: number }[];
  suffix: string;
}

export interface StatData {
  value: number;
  decimals: number;
  prefix: string;
  suffix: string;
  label: string;
}

export interface Scene {
  id: string;
  type: SceneType;
  start_frame: number;
  end_frame: number;
  headline: string;
  subtext: string;
  emphasis: string[];
  items: string[];
  left: string | null;
  right: string | null;
  stat: StatData | null;
  expression: Expression;
  transition: Transition;
  source_label: string | null;
  icon: string;
  layout: Layout;
  background: BackgroundMode;
  camera: Camera;
  avatar: AvatarMode;
  hide_captions: boolean;
  asset: string | null;
  meta: Record<string, unknown>;
  cues: Cue[];
  lines: string[];
}

export interface CaptionWord {
  text: string;
  start_frame: number;
  end_frame: number;
  emphasis: boolean;
}

export interface CaptionGroup {
  start_frame: number;
  end_frame: number;
  words: CaptionWord[];
}

export interface Theme {
  bg_from: string;
  bg_to: string;
  accent: string;
  accent2: string;
  text: string;
  muted: string;
  panel: string;
  font_family: string;
}

export interface CaptionStyle {
  font_size: number;
  center_y: number;
  highlight: string;
  uppercase: boolean;
  max_width: number;
}

export interface AvatarTrack {
  mouth_open: number[];
  visemes: Viseme[];
  blink_frames: number[];
  emphasis_frames: number[];
  nod_frames: number[];
  center_x: number;
  center_y: number;
  size: number;
}

export type SceneManifest = {
  schema_version: number;
  job_id: string;
  title: string;
  cover_title: string;
  width: number;
  height: number;
  fps: number;
  duration_frames: number;
  handle: string;
  audio_src: string | null;
  theme: Theme;
  caption_style: CaptionStyle;
  scenes: Scene[];
  caption_groups: CaptionGroup[];
  avatar: AvatarTrack;
  sfx_cues: SfxCue[];
  music_cues: MusicCue[];
};
