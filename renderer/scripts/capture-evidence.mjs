// Capture a REAL screenshot of a source page with the cited sentence located on it.
//
//   node scripts/capture-evidence.mjs <url> <quote> <out.png>
//
// Uses Remotion's pinned Chrome Headless Shell over the DevTools protocol (Node 22's built-in
// WebSocket, no extra packages). Prints JSON: {ok, rects:[{x,y,w,h}], width, height, title, ...}.
// The page is not modified; the renderer draws the highlight over the reported rectangles.
import { spawn } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const [url, quote, out] = process.argv.slice(2);
if (!url || !quote || !out) {
  console.error("usage: capture-evidence.mjs <url> <quote> <out.png>");
  process.exit(2);
}
const here = dirname(fileURLToPath(import.meta.url));
const shellRoot = join(here, "..", "node_modules", ".remotion", "chrome-headless-shell");
const platformDir = readdirSync(shellRoot, { withFileTypes: true }).find((d) => d.isDirectory()).name;
const inner = readdirSync(join(shellRoot, platformDir)).find((d) => d.startsWith("chrome-headless-shell"));
const chromePath = join(shellRoot, platformDir, inner, "chrome-headless-shell");

// Phone-width viewport at 2x: page text stays large enough to read in a 9:16 video.
const WIDTH = 540;
const HEIGHT = 960;
const SCALE = 2;
const profile = mkdtempSync(join(tmpdir(), "rf-evidence-"));
const chrome = spawn(chromePath, [
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  "--no-first-run",
  "--hide-scrollbars",
  "--disable-gpu",
  `--window-size=${WIDTH},${HEIGHT}`,
  "about:blank",
]);

const fail = (msg) => {
  console.log(JSON.stringify({ ok: false, error: msg }));
  cleanup(1);
};
const cleanup = (code) => {
  try {
    chrome.kill("SIGKILL");
  } catch {}
  try {
    rmSync(profile, { recursive: true, force: true });
  } catch {}
  process.exit(code);
};
setTimeout(() => fail("timed out"), 60000);

const wsUrl = await new Promise((resolve) => {
  let buf = "";
  chrome.stderr.on("data", (d) => {
    buf += d.toString();
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) resolve(m[1]);
  });
});

const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let nextId = 1;
const pending = new Map();
const listeners = [];
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  } else if (msg.method) {
    listeners.forEach((l) => l(msg));
  }
});
const send = (method, params = {}, sessionId) =>
  new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });

try {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => send(m, p, sessionId);
  await s("Page.enable");
  await s("Emulation.setDeviceMetricsOverride", { width: WIDTH, height: HEIGHT, deviceScaleFactor: SCALE, mobile: true });
  const loaded = new Promise((r) => listeners.push((m) => m.method === "Page.loadEventFired" && m.sessionId === sessionId && r()));
  await s("Page.navigate", { url });
  await Promise.race([loaded, new Promise((r) => setTimeout(r, 20000))]);
  await new Promise((r) => setTimeout(r, 1200));
  const expr = `(() => {
    const want = ${JSON.stringify(quote)}.toLowerCase().replace(/\\s+/g, " ").trim();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = []; let text = "";
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const st = n.parentElement && getComputedStyle(n.parentElement);
      if (st && (st.display === "none" || st.visibility === "hidden")) continue;
      nodes.push([n, text.length]); text += n.nodeValue;
    }
    // whitespace-insensitive search: map normalised positions back to raw ones
    let norm = "", map = [];
    for (let i = 0; i < text.length; i++) {
      const c = /\\s/.test(text[i]) ? " " : text[i].toLowerCase();
      if (c === " " && norm.endsWith(" ")) continue;
      norm += c; map.push(i);
    }
    const at = norm.indexOf(want);
    if (at < 0) return { found: false };
    const start = map[at], end = map[at + want.length - 1] + 1;
    const locate = (pos) => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= pos) return [nodes[k][0], pos - nodes[k][1]]; };
    const range = document.createRange();
    const [sn, so] = locate(start), [en, eo] = locate(end - 1);
    range.setStart(sn, so); range.setEnd(en, eo + 1);
    const el = sn.parentElement;
    el.scrollIntoView({ block: "center" });
    window.scrollBy(0, -${Math.round(HEIGHT * 0.08)});
    const rects = [...range.getClientRects()].filter(r => r.width > 2).map(r => ({ x: r.x, y: r.y, w: r.width, h: r.height }));
    return { found: true, rects, title: document.title };
  })()`;
  const res = await s("Runtime.evaluate", { expression: expr, returnByValue: true });
  const v = res.result.value || { found: false };
  if (!v.found) fail("quote not found on page");
  const shot = await s("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log(
    JSON.stringify({
      ok: true,
      url,
      quote,
      title: v.title,
      rects: v.rects.map((r) => ({ x: r.x * SCALE, y: r.y * SCALE, w: r.w * SCALE, h: r.h * SCALE })),
      width: Math.round(WIDTH * SCALE),
      height: Math.round(HEIGHT * SCALE),
      captured_at: new Date().toISOString(),
    }),
  );
  cleanup(0);
} catch (e) {
  fail(String(e && e.message ? e.message : e));
}
