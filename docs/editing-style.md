# ReelForge editing style

How a ReelForge video is cut, and how to direct it from a script. The goal: every cut, animation,
caption and sound has a reason that comes from the narration.

## Visual identity

- **Palette:** ink navy `#1B1446 → #07061A`, mint accent `#4DF0C8` (key terms, active caption
  word, the "after" state), pink accent `#FF6B9A` (markers, the twist, ratios), white type.
- **Type:** Lato Black for headlines, captions and kinetic type; Fira Code for terminal footage.
- **Motion language:** springs (no linear slides), one camera move per scene, hard cuts by default.
- **Backgrounds:** `glow` (statements, numbers, kinetic type), `grid` (explaining, charts),
  `terminal` (footage), `paper` (source screenshots), `accent` (the twist only).

## Editing grammar (`reelforge/visuals/director.py`)

| Situation | Treatment |
|---|---|
| Same idea continues (same section) | hard cut |
| New idea (new section) | whip or zoom, never the same twice in a row |
| Impact beat (number, twist, meme) starts a section | white flash + shake + impact sound |
| Hook / twist / payoff | fast pace (≈1.8–2.4 s per visual) |
| Explanations | slower (≈3.4 s), or held while steps reveal on their words |
| Kinetic typography / meme | captions hidden (the words are already on screen) |
| Footage, evidence, charts, kinetic type | avatar off screen |
| Hook, reactions, short explainers, CTA | avatar on screen (center / corner / big reaction) |

Camera: `push` on typography and numbers, `drift` on explainers, `track` to the highlighted
line or sentence on footage, `punch` on memes, none on diagrams and charts (they must be read).

## Sound follows picture

| Sound | When |
|---|---|
| whoosh | only on whip/zoom cuts, peaking on the cut |
| impact | flash cuts, and the frame a big number lands |
| riser + music drop | the second before "but here's the catch"; music returns ~1.3 s later |
| key clicks | exactly while a terminal command is being typed |
| shutter | a source screenshot landing |
| pop | emphasised words in kinetic typography (max one per 0.8 s) |

Music is a quiet generated bed, sidechain-ducked under the voice, faded out at the end. All
sounds are synthesized by `reelforge/rendering/sound.py` (no licensed samples).

## Directing from the script

A section's first `>` line is its main visual; every further `> at: <spoken phrase> | scene: …`
starts a new visual exactly when that phrase is spoken.

```
[number]
At sixteen-bit precision, every parameter takes two bytes. So seven billion parameters need about fourteen gigabytes.
> scene: terminal | cast: casts/weights_2_bytes.json | headline: A real model file on this laptop | quote: 2 bytes each
> at: So seven billion | scene: stat | value: 14 | suffix: GB | label: 7B weights at 16-bit
```

Scene types: `kinetic`, `terminal`, `evidence`, `bars`, `photo`, `meme`, `stat`, `diagram`,
`comparison`, `explain`, `twist`, `cta` (plus older `hook`, `reveal`, `demo`, `analogy`).

| Type | Hint keys |
|---|---|
| `kinetic` | none - shows the spoken words |
| `terminal` | `cast:` (recorded file), `headline:`, `quote:` (output text to highlight) |
| `evidence` | `source:` URL, `quote:` exact sentence on that page |
| `bars` | `items: label = value ; label = value`, `suffix:`, `headline:` |
| `photo` | `headline:`, `left:`, `right:` |
| `meme` | `top:`, `bottom:`, `expression:` |
| `stat` | `value:`, `suffix:`, `label:`, `headline:` |

## Real footage only

- **Terminal footage** comes from `reelforge capture-terminal`, which really runs the commands on
  your machine and saves their real output and timing (home directory and username removed).
  Scripts can only *reference* a cast; the planner never runs commands. A `terminal` scene
  without a cast is turned into a normal explainer rather than faked.

  ```bash
  python -m reelforge.main capture-terminal --out examples/casts/weights_2_bytes.json \
      --cwd ~/models/qwen2.5-0.5b --cmd "du -hL model.safetensors" \
      --cmd "python3 inspect_weights.py model.safetensors"
  ```

- **Evidence** is a real screenshot of the cited page, captured at planning time by Remotion's
  bundled Chrome at a phone-width viewport, with the quoted sentence located and highlighted. If
  the page can't be fetched (offline, changed text), the scene becomes a plain quote card labelled
  "Quoted from …", never a fake screenshot.

Both carry an on-screen label ("Real output · recorded on this laptop · date",
"Screenshot · domain · date").

## Performance

Everything is transforms, gradients and SVG - no CSS blur or video decoding. On the i5-5300U a
360×640 preview of a 55 s reel renders in ~2–2.5 min; the 1080×1920 final in ~6–10 min depending
on desktop load.
