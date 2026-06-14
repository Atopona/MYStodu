"""Mock engine: canned prompt generation + simulated render, used when the real
LLM / ComfyUI are unreachable (or forced via settings). Keeps the whole UI
flow demonstrable end-to-end on a bare machine."""
import base64
import io
import math
import os
import random
import re
import shutil
import subprocess
from typing import Callable, List, Optional

from PIL import Image, ImageDraw, ImageFilter

from . import prompt_engine

# ----------------------------------------------------------------- ffmpeg


def find_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


# ----------------------------------------------------------- mock model zoo

MOCK_COMFY_MODELS = {
    "text_encoders": [
        "gemma_3_12b_it_fp8_scaled.safetensors",
        "gemma_3_12b_it_bf16.safetensors",
        "t5xxl_fp16.safetensors",
    ],
    "text_projections": [
        "ltx-2.3_text_projection_bf16.safetensors",
        "ltx-2.3_text_projection_fp8.safetensors",
    ],
    "upscalers": [
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        "ltx-2.3-spatial-upscaler-x2-1.0.safetensors",
        "ltxv-spatial-upscaler-0.9.7.safetensors",
    ],
    "audio_vaes": [
        "LTX23_audio_vae_bf16.safetensors",
        "LTX23_audio_vae_fp8.safetensors",
    ],
    "preview_vaes": [
        "taedhz2_1.safetensors",
        "taehv_v1.safetensors",
    ],
    "checkpoints": [
        "10eros+sulphurexperimental0.25_str.safetensors",
        "LTX2.3-10Eros_bf16.safetensors",
        "LTX2.3-10Eros_fp8_mixed_learned.safetensors",
        "sulphur-2-base_fp8mixed.safetensors",
        "sulphur-2-base_bf16_dev.safetensors",
        "ltx-2.3-22b-distilled_FULL_bf16.safetensors",
        "ltx-2.3-dev_bf16.safetensors",
    ],
    "loras": [
        "ltx-2.3-22b-distilled-lora-384-1.1_cond_safe.safetensors",
        "ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
        "sulphur-2_distill_lora_v1_cond_safe.safetensors",
        "ltx23_camera_static_v1.safetensors",
        "ltx23_camera_dolly_in_v1.safetensors",
        "ltx23_camera_dolly_out_v1.safetensors",
        "ltx23_handheld_organic_v1.safetensors",
        "10eros_detail_boost_v2.safetensors",
    ],
}

MOCK_LLM_SUGGESTIONS = {
    "ggufs": [
        "sulphur-prompt-enhancer-9b-Q4_K_M.gguf",
        "gemma-3-12b-it-Q4_K_M.gguf",
    ],
    "mmprojs": [
        "sulphur-prompt-enhancer-mmproj-f16.gguf",
        "mmproj-gemma-3-12b-it-f16.gguf",
    ],
}

# ------------------------------------------------------------ mock prompts

_SPACE_BEATS = [
    {
        "motion": "DOLLY IN",
        "text": (
            "{lead}A lone woman in a worn olive flight suit stands at a massive reinforced "
            "observation window aboard a dim spacecraft cabin, her pale face lit by the cold "
            "glow of a swirling white storm on the planet below, dark consoles pulsing faint "
            "green behind her. {shot}The camera begins a slow dolly in from a medium shot, "
            "drifting a fraction closer to the reinforced glass, the frame moving steadily toward her."
        ),
        "sounds": "soft friction of flight suit fabric, low electric hum intensifies.",
        "vocal": ("Woman (intense, low)", "But you know what's happening down there."),
    },
    {
        "motion": "PUSH IN",
        "text": (
            "The frame pushes in further to a tight close-up on her eyes, which are glassy and "
            "reflecting the swirling white storm of the planet. She does not blink, her gaze "
            "fixed on the void as the camera continues its steady, tight press toward her features.{fov}"
        ),
        "sounds": "heavy, rhythmic breathing, subtle electronic beep from the console.",
        "vocal": ("Woman (whispering, strained)", "The chaos... it follows us everywhere."),
    },
    {
        "motion": "HOLD",
        "text": (
            "The camera holds a tight close-up on her face as her expression shifts from "
            "contemplation to a grim realization, her lips trembling slightly. She remains "
            "motionless, her eyes locked on the window, the framing staying locked and tight "
            "on her sweating skin and intense stare."
        ),
        "sounds": "deep, slow intake of breath, hum of the ship remains constant.",
        "vocal": ("Woman (hollow, breathy)", "Even in the silence of the stars."),
    },
    {
        "motion": "PULL OUT",
        "text": (
            "The camera begins a slow glide, pulling out from the tight close-up back to a "
            "medium shot, revealing her lonely figure against the massive, indifferent window. "
            "She turns her head slightly away from the glass, looking down at the dark control "
            "panel as the frame retreats.{choreo}"
        ),
        "sounds": "long, exhaled breath, ship hum fades into a low drone.",
        "vocal": ("Woman (resigned, quiet)", "We're just drifting."),
    },
    {
        "motion": "STATIC",
        "text": (
            "The frame settles static and wide: her small silhouette against the immense "
            "storm-lit window, the cabin lights flickering once before holding steady, the "
            "planet's slow churn filling the glass behind her."
        ),
        "sounds": "distant structural creak, the drone settling into near silence.",
        "vocal": ("Woman (barely audible)", "Keep watching."),
    },
]


def mock_generate(
    *,
    intent: str,
    duration: int,
    shot_type: str,
    dialogue: bool,
    fov: bool,
    choreo: bool,
    lora_triggers: str,
    creativity: float = 0.7,
    mode: str = "i2v",
) -> str:
    bounds = prompt_engine.default_beat_bounds(duration)
    n = len(bounds)
    src = _SPACE_BEATS[:n] if n <= len(_SPACE_BEATS) else _SPACE_BEATS
    lead = ""
    trig = (lora_triggers or "").strip().strip(",")
    if trig:
        lead = f"{trig}, "
    shot = ""
    st = (shot_type or "").strip()
    if st and st.upper() != "CINEMATIC":
        shot = f"Framed as a {st.lower()} shot. "
    fov_txt = (
        " The lens compresses subtly, the field of view narrowing as the background optics fall away."
        if fov
        else ""
    )
    choreo_txt = (
        " She shifts her weight and takes one slow step back from the glass, her silhouette re-centering in the frame."
        if choreo
        else ""
    )
    blocks: List[str] = []
    for i, (a, b) in enumerate(bounds):
        beat = src[min(i, len(src) - 1)]
        body = beat["text"].format(lead=lead if i == 0 else "", shot=shot if i == 0 else "", fov=fov_txt, choreo=choreo_txt)
        lines = [f"[{a}-{b}s] {body}", f"Sounds: {beat['sounds']}"]
        if dialogue and beat.get("vocal"):
            who, line = beat["vocal"]
            lines.append(f'Vocal: {who}: "{line}"')
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


_EXTRA_VOCALS = [
    ('Woman (urgent, hushed)', "We can't look away now."),
    ('Woman (steady, cold)', "It was never going to let us go."),
    ('Woman (soft, breaking)', "I still hear them down there."),
]


def mock_refine(prompt: str, instruction: str) -> str:
    beats = prompt_engine.parse_beats(prompt)
    if not beats:
        return prompt
    instr = (instruction or "").lower()
    targets = list(range(len(beats)))
    m = re.search(r"beat\s*(\d+)", instr)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(beats):
            targets = [idx]

    def edit(i: int, body: str) -> str:
        lines = [ln for ln in body.splitlines()]
        desc_idx = 0
        if "slower" in instr or "slow" in instr:
            lines[desc_idx] += " The motion stretches slower and more deliberate, each move held a breath longer."
        if "faster" in instr or "harder cut" in instr or "harder cuts" in instr:
            lines[desc_idx] += " The pacing tightens, the move snapping harder into the next frame."
        if "more dialogue" in instr or "more vocal" in instr:
            who, line = _EXTRA_VOCALS[i % len(_EXTRA_VOCALS)]
            lines.append(f'Vocal: {who}: "{line}"')
        if "less dialogue" in instr or "no dialogue" in instr or "remove dialogue" in instr:
            lines = [ln for ln in lines if not ln.strip().lower().startswith("vocal:")]
        if "music" in instr or "score" in instr:
            for j, ln in enumerate(lines):
                if ln.strip().lower().startswith("sounds:"):
                    lines[j] = ln.rstrip(".") + ", a low synth score swelling beneath the hum."
        if not any(
            k in instr
            for k in ("slower", "slow", "faster", "harder cut", "more dialogue", "more vocal", "less dialogue", "no dialogue", "remove dialogue", "music", "score")
        ) and instruction.strip():
            lines[desc_idx] += f" The staging adjusts: {instruction.strip().rstrip('.')}."
        return "\n".join(lines)

    blocks = []
    for i, b in enumerate(beats):
        body = edit(i, b["text"]) if i in targets else b["text"]
        a, e = int(b["start"]), int(b["end"])
        blocks.append(f"[{a}-{e}s] {body}")
    return "\n\n".join(blocks)


# --------------------------------------------------------- preview frames


def make_preview_frame(step: int, total: int, phase: str, seed: int, w: int = 416, h: int = 234) -> str:
    """Procedural sci-fi-ish preview frame -> base64 JPEG."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (7, 12, 8))
    dr = ImageDraw.Draw(img)
    # nebula glow drifting with step
    cx = int(w * (0.3 + 0.4 * (step / max(1, total))))
    cy = int(h * 0.45)
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    for r, a in ((150, 30), (110, 50), (70, 80), (40, 120)):
        gd.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=a)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    tint = Image.new("RGB", (w, h), (60, 160, 70))
    img = Image.composite(tint, img, glow)
    dr = ImageDraw.Draw(img)
    # stars
    for _ in range(90):
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        v = rnd.randint(60, 200)
        dr.point((x, y), fill=(v, min(255, v + 30), v))
    # window strut
    dr.rectangle([0, int(h * 0.82), w, h], fill=(10, 16, 11))
    dr.line([(0, int(h * 0.82)), (w, int(h * 0.82))], fill=(40, 70, 40), width=2)
    # scanlines
    for y in range(0, h, 3):
        dr.line([(0, y), (w, y)], fill=(0, 0, 0), width=1)
    # hud
    dr.rectangle([6, 6, 150, 22], outline=(80, 140, 60))
    dr.text((12, 9), f"{phase} {step}/{total}", fill=(190, 245, 120))
    pct = step / max(1, total)
    dr.rectangle([6, h - 14, 6 + int((w - 12) * pct), h - 8], fill=(160, 235, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ------------------------------------------------------------- mock video


def make_mock_video(
    out_path: str,
    *,
    width: int,
    height: int,
    fps: int,
    duration: float,
    seed: int = 0,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Synthesize a placeholder mp4 (drifting green gradients + low sine drone)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        if log:
            log("ffmpeg not found — cannot synthesize mock video")
        return False
    dur = max(2.0, min(float(duration), 60.0))
    w = width - (width % 2)
    h = height - (height % 2)
    vsrc = (
        f"gradients=size={w}x{h}:rate={fps}:duration={dur:.2f}:speed=0.035:"
        f"nb_colors=4:c0=0x040d06:c1=0x123a18:c2=0x77d02f:c3=0x0a1f0e:seed={seed % 2147483647}"
    )
    asrc = f"sine=frequency=82:duration={dur:.2f}"
    fade_out = max(0.0, dur - 1.0)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", vsrc,
        "-f", "lavfi", "-i", asrc,
        "-filter_complex",
        (
            "[0:v]noise=alls=7:allf=t,vignette=PI/4.5,format=yuv420p[v];"
            f"[1:a]tremolo=f=0.4:d=0.7,volume=0.4,afade=t=in:d=1.0,afade=t=out:st={fade_out:.2f}:d=1.0[a]"
        ),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        out_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            if log:
                log(f"ffmpeg mock video failed: {res.stderr[-400:]}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        if log:
            log(f"ffmpeg mock video error: {exc}")
        return False


def make_thumbnail(video_path: str, thumb_path: str, at: float = 1.0) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg or not os.path.exists(video_path):
        return False
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, at):.2f}", "-i", video_path,
        "-frames:v", "1", "-vf", "scale=360:-2", thumb_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.returncode == 0 and os.path.exists(thumb_path)
    except Exception:
        return False
