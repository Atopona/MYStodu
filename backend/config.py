"""Paths and default settings for Cinematic Console."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(ROOT, "data")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
OUTPUT_DIR = os.path.join(ROOT, "outputs")
THUMB_DIR = os.path.join(OUTPUT_DIR, "thumbs")
LLM_MODEL_DIR = os.path.join(ROOT, "models", "llm")
LTX_MODEL_DIR = os.path.join(ROOT, "models", "ltx")
RENDER_MODEL_DIRS = [LTX_MODEL_DIR]
TOOLS_DIR = os.path.join(ROOT, "tools")
FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")
DB_PATH = os.path.join(DATA_DIR, "console.db")

for _d in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, THUMB_DIR, LLM_MODEL_DIR, LTX_MODEL_DIR, TOOLS_DIR):
    os.makedirs(_d, exist_ok=True)

DEFAULT_SETTINGS = {
    # --- LLM (llama.cpp) ---
    # embedded: load GGUF in the FastAPI process via llama-cpp-python.
    # managed: compatibility fallback that spawns a project-local llama-server.
    # external: advanced/debug only; not shown as the normal UI path.
    "llm_mode": "embedded",
    "llama_server_path": os.path.join("tools", "llama.cpp", "llama-server.exe"),
    "llm_host": "127.0.0.1",
    "llm_port": 8731,
    "llm_gguf": "",                   # filename inside models/llm (or absolute path)
    "llm_mmproj": "",
    "llm_ngl": 99,
    "llm_ctx": 8192,
    "llm_extra_args": "",
    "llm_api_key": "",
    "external_llm_url": "http://127.0.0.1:8080",
    "auto_start_llm": False,
    # sulphur: Sulphur Prompt Enhancer usage — no system prompt, raw text(+image).
    # director: generic VLM — use the built-in director system prompt.
    # auto: pick by model filename (sulphur/enhancer -> sulphur style).
    "prompt_style": "auto",
    # --- Render / prompt assembly ---
    "keep_timestamps": False,          # keep [0-12s] markers in the prompt sent to LTX
    "negative_prompt": "blurry, low quality, watermark, jpeg artifacts, distorted face, glitch, text overlay, static noise",
}

SHOT_TYPES = [
    "CINEMATIC",
    "DOCUMENTARY",
    "HANDHELD",
    "STATIC LOCKED",
    "FPV DRONE",
    "STEADICAM",
    "ANAMORPHIC WIDE",
    "MACRO DETAIL",
    "SECURITY CAM",
    "MUSIC VIDEO",
]

RESOLUTIONS = [
    {"label": "1216 x 704  ·  LTX native", "width": 1216, "height": 704},
    {"label": "1024 x 576  ·  HD draft 16:9", "width": 1024, "height": 576},
    {"label": "896 x 512   ·  fast 16:9", "width": 896, "height": 512},
    {"label": "768 x 448   ·  low VRAM 12:7", "width": 768, "height": 448},
    {"label": "768 x 1152  ·  portrait 2:3", "width": 768, "height": 1152},
    {"label": "704 x 1216  ·  portrait 9:16", "width": 704, "height": 1216},
    {"label": "768 x 768   ·  square", "width": 768, "height": 768},
]


def snap_frames(duration_s: float, fps: int) -> int:
    """LTX wants frame counts of the form 8n+1."""
    raw = max(1, round(duration_s * fps))
    n = max(1, round((raw - 1) / 8))
    return 8 * n + 1
