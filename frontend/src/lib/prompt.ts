import { Beat } from "../types";

const BEAT_RE = /\[\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*s?\s*\]/gi;

const MOTIONS: Array<[string, string]> = [
  ["whip pan", "WHIP PAN"],
  ["dolly in", "DOLLY IN"],
  ["dollies in", "DOLLY IN"],
  ["dolly out", "DOLLY OUT"],
  ["dollies out", "DOLLY OUT"],
  ["push in", "PUSH IN"],
  ["pushes in", "PUSH IN"],
  ["pushing in", "PUSH IN"],
  ["pull out", "PULL OUT"],
  ["pulls out", "PULL OUT"],
  ["pulling out", "PULL OUT"],
  ["pull back", "PULL OUT"],
  ["pulls back", "PULL OUT"],
  ["zoom in", "ZOOM IN"],
  ["zooms in", "ZOOM IN"],
  ["zoom out", "ZOOM OUT"],
  ["zooms out", "ZOOM OUT"],
  ["crane up", "CRANE UP"],
  ["crane down", "CRANE DOWN"],
  ["pan left", "PAN LEFT"],
  ["pans left", "PAN LEFT"],
  ["pan right", "PAN RIGHT"],
  ["pans right", "PAN RIGHT"],
  ["tilt up", "TILT UP"],
  ["tilts up", "TILT UP"],
  ["tilt down", "TILT DOWN"],
  ["tilts down", "TILT DOWN"],
  ["orbit", "ORBIT"],
  ["arcs around", "ORBIT"],
  ["tracking shot", "TRACKING"],
  ["tracks alongside", "TRACKING"],
  ["tracking", "TRACKING"],
  ["handheld", "HANDHELD"],
  ["glide", "GLIDE"],
  ["drifts", "DRIFT"],
  ["static", "STATIC"],
  ["locked", "HOLD"],
  ["holds", "HOLD"],
  ["hold", "HOLD"],
  ["remains still", "HOLD"],
];

export function detectMotion(body: string): string {
  const probe = body.toLowerCase().slice(0, 420);
  for (const [kw, label] of MOTIONS) {
    if (probe.includes(kw)) return label;
  }
  return "SHOT";
}

export function parseBeats(text: string): Beat[] {
  const beats: Beat[] = [];
  if (!text) return beats;
  const matches = [...text.matchAll(BEAT_RE)];
  matches.forEach((m, i) => {
    const start = parseFloat(m[1]);
    const end = parseFloat(m[2]);
    const bodyStart = (m.index ?? 0) + m[0].length;
    const bodyEnd = i + 1 < matches.length ? matches[i + 1].index! : text.length;
    const body = text.slice(bodyStart, bodyEnd).trim();
    beats.push({ start, end, motion: detectMotion(body), text: body });
  });
  return beats;
}

export function wordCount(text: string): number {
  return (text.match(/\S+/g) || []).length;
}

export function snapFrames(duration: number, fps: number): number {
  const raw = Math.max(1, Math.round(duration * fps));
  const n = Math.max(1, Math.round((raw - 1) / 8));
  return 8 * n + 1;
}

export function randomSeed(): string {
  return String(
    Math.floor(1e11 + Math.random() * 9e11)
  );
}

export function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Build highlighted HTML mirror of the prompt for the backdrop layer. */
export function highlightPrompt(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(
    /\[\s*\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\s*s?\s*\]/gi,
    (m) => `<b class="ts">${m}</b>`
  );
  html = html.replace(/^(Sounds:)/gim, '<i class="cue">$1</i>');
  html = html.replace(/^(Vocal:)/gim, '<i class="vox">$1</i>');
  return html + "\n";
}
