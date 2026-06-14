"""Prompt assembly + beat parsing for the director console.

A "beat" is a `[start-end s]` paragraph of the long cinematic prompt:

    [0-12s] The camera begins a slow dolly in ...
    Sounds: soft friction of flight suit fabric ...
    Vocal: Woman (intense, low): "But you know ..."
"""
import re
from typing import List, Optional

BEAT_RE = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*s?\s*\]", re.I)

# keyword -> canonical ruler label, scanned in order (longer phrases first)
_MOTIONS = [
    ("whip pan", "WHIP PAN"),
    ("dolly in", "DOLLY IN"),
    ("dollies in", "DOLLY IN"),
    ("dolly out", "DOLLY OUT"),
    ("dollies out", "DOLLY OUT"),
    ("push in", "PUSH IN"),
    ("pushes in", "PUSH IN"),
    ("pushing in", "PUSH IN"),
    ("pull out", "PULL OUT"),
    ("pulls out", "PULL OUT"),
    ("pulling out", "PULL OUT"),
    ("pull back", "PULL OUT"),
    ("pulls back", "PULL OUT"),
    ("zoom in", "ZOOM IN"),
    ("zooms in", "ZOOM IN"),
    ("zoom out", "ZOOM OUT"),
    ("zooms out", "ZOOM OUT"),
    ("crane up", "CRANE UP"),
    ("crane down", "CRANE DOWN"),
    ("pan left", "PAN LEFT"),
    ("pans left", "PAN LEFT"),
    ("pan right", "PAN RIGHT"),
    ("pans right", "PAN RIGHT"),
    ("tilt up", "TILT UP"),
    ("tilts up", "TILT UP"),
    ("tilt down", "TILT DOWN"),
    ("tilts down", "TILT DOWN"),
    ("orbit", "ORBIT"),
    ("arcs around", "ORBIT"),
    ("tracking shot", "TRACKING"),
    ("tracks alongside", "TRACKING"),
    ("tracking", "TRACKING"),
    ("handheld", "HANDHELD"),
    ("glide", "GLIDE"),
    ("drifts", "DRIFT"),
    ("static", "STATIC"),
    ("locked", "HOLD"),
    ("holds", "HOLD"),
    ("hold", "HOLD"),
    ("remains still", "HOLD"),
]


def detect_motion(body: str) -> str:
    probe = body.lower()[:420]
    for kw, label in _MOTIONS:
        if kw in probe:
            return label
    return "SHOT"


def parse_beats(text: str) -> List[dict]:
    """Slice prompt text into beats by [a-bs] markers."""
    beats: List[dict] = []
    matches = list(BEAT_RE.finditer(text or ""))
    for i, m in enumerate(matches):
        start, end = float(m.group(1)), float(m.group(2))
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():body_end].strip()
        beats.append(
            {
                "start": start,
                "end": end,
                "motion": detect_motion(body),
                "text": body,
            }
        )
    return beats


def strip_timestamps(text: str) -> str:
    """Remove [a-bs] markers -> sequential long-form prompt the model expects."""
    out = BEAT_RE.sub("", text or "")
    lines = [ln.strip() for ln in out.splitlines()]
    paragraphs: List[str] = []
    buf: List[str] = []
    for ln in lines:
        if ln:
            buf.append(ln)
        elif buf:
            paragraphs.append(" ".join(buf))
            buf = []
    if buf:
        paragraphs.append(" ".join(buf))
    return "\n\n".join(paragraphs).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def default_beat_bounds(duration: float) -> List[tuple]:
    """Cut a clip into screenplay-ish beats (mirrors the 0-12/12-18/18-24/24-30 layout)."""
    d = max(2.0, float(duration))
    if d <= 8:
        cuts = [0, d]
    elif d <= 14:
        cuts = [0, round(d * 0.55), d]
    elif d <= 22:
        cuts = [0, round(d * 0.4), round(d * 0.72), d]
    else:
        cuts = [0, round(d * 0.4), round(d * 0.6), round(d * 0.8), d]
    bounds = []
    for i in range(len(cuts) - 1):
        a, b = int(cuts[i]), int(cuts[i + 1])
        if b > a:
            bounds.append((a, b))
    return bounds


def ensure_beats(text: str, duration: float) -> str:
    """Guarantee the editor/ruler always has [a-bs] markers.

    If the LLM returned plain paragraphs, spread them over the duration.
    """
    if BEAT_RE.search(text or ""):
        return text.strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if not paras:
        return text.strip()
    bounds = default_beat_bounds(duration)
    # merge/spread paragraphs into len(bounds) chunks
    n = len(bounds)
    chunks: List[List[str]] = [[] for _ in range(n)]
    for i, p in enumerate(paras):
        chunks[min(i * n // max(1, len(paras)), n - 1)].append(p)
    out = []
    for (a, b), chunk in zip(bounds, chunks):
        body = "\n".join(chunk).strip()
        if body:
            out.append(f"[{a}-{b}s] {body}")
    return "\n\n".join(out)


# ------------------------------------------------------------------ LLM I/O

DIRECTOR_SYSTEM_PROMPT = """You are a film director writing generation prompts for the LTX-2 video+audio model.
LTX has weak self-inference: the first frame, every subsequent action, all dialogue and all audio MUST be written out explicitly, in chronological order.

Write ONE continuous cinematic prompt split into time-coded beats. Strict format, one block per beat:

[<start>-<end>s] <Concise description of the frame: subject, appearance, composition, pose, background. Then the camera move and the action evolving naturally through this beat.>
Sounds: <ambient/foley/natural audio cues paired with the on-screen action; background-music style only when it fits.>
Vocal: <Speaker (tone)>: "<exact line>"   — only when dialogue is requested.

Rules:
- Beat 1 must open with a complete description of the initial frame before any motion.
- Describe actions as continuous evolution; never reference "the previous shot".
- Quote every spoken line verbatim with the speaker's tone in parentheses, placed inside the beat where it is spoken.
- Keep audio cues physical and synchronized with the action.
- No meta commentary, no markdown, no camera jargon outside the description, no extra blank sections.
- Cover the FULL requested duration with contiguous beats and respect the requested beat structure."""


def build_generation_user_text(
    *,
    intent: str,
    duration: int,
    fps: int,
    shot_type: str,
    dialogue: bool,
    fov: bool,
    choreo: bool,
    lora_triggers: str,
    mode: str,
    has_image: bool,
) -> str:
    bounds = default_beat_bounds(duration)
    beat_str = ", ".join(f"[{a}-{b}s]" for a, b in bounds)
    lines = [
        f"Director intent: {intent.strip() or 'an amazing cinematic performance'}",
        f"Clip length: {duration}s at {fps} fps. Split into exactly {len(bounds)} beats: {beat_str}.",
        f"Shot style: {shot_type}.",
    ]
    if mode == "i2v" and has_image:
        lines.append(
            "A reference image is attached: it is the exact first frame. Describe it precisely in beat 1, then evolve from it."
        )
    else:
        lines.append("No reference image: invent and fully describe the opening frame in beat 1.")
    lines.append(
        "Dialogue: " + (
            "include spoken lines (Vocal: Speaker (tone): \"line\") placed inside the beats."
            if dialogue else "NO dialogue, no Vocal lines — performance and audio only."
        )
    )
    if fov:
        lines.append("FOV: include at least one deliberate field-of-view change (lens push, widen, or compression).")
    if choreo:
        lines.append("Choreography: block the subject's movement through the frame explicitly (positions, turns, gestures).")
    if lora_triggers.strip():
        lines.append(
            f"Insert these trigger words verbatim, naturally, early in beat 1: {lora_triggers.strip()}"
        )
    lines.append("Every beat needs a Sounds: line. Output only the beats, nothing else.")
    return "\n".join(lines)


def build_refine_user_text(current_prompt: str, instruction: str) -> str:
    return (
        "Here is the current time-coded cinematic prompt:\n\n"
        f"{current_prompt.strip()}\n\n"
        f"Revision note from the director: {instruction.strip()}\n\n"
        "Rewrite the FULL prompt applying the note. Keep the same [start-end s] beat format, "
        "keep everything that still works, change only what the note demands. Output only the beats."
    )
