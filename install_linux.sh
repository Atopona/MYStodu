#!/usr/bin/env bash
set -euo pipefail

# Cinematic Console Linux installer.
#
# What it does:
# - creates .venv and installs backend dependencies
# - installs llama-cpp-python for in-process GGUF inference (no external LLM service)
# - installs/builds the React frontend when npm is available
# - downloads the Prompt Enhancer GGUF/mmproj and the LTX/10Eros/Sulphur model repos
# - writes default settings for embedded LLM mode
#
# Large downloads are intentional. Set SKIP_MODEL_DOWNLOAD=1 to install code only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

LLM_DIR="${LLM_DIR:-$ROOT/models/llm}"
COMFY_MODEL_ROOT="${COMFY_MODEL_ROOT:-$ROOT/models/comfyui}"
TMP_DIR="${TMP_DIR:-$ROOT/.tmp/linux-install}"

PROMPT_REPO="${PROMPT_REPO:-SulphurAI/Sulphur-2-Prompt-Enhancer-GGUF}"
BASE_REPO="${BASE_REPO:-Lightricks/LTX-2.3}"
I2V_REPO="${I2V_REPO:-TenStrip/LTX2.3-10Eros}"
T2V_REPO="${T2V_REPO:-SulphurAI/Sulphur-2-base}"
DISTIL_REPO="${DISTIL_REPO:-Kijai/LTX2.3_Distilled_Lora_1.1_Experiments}"

SKIP_MODEL_DOWNLOAD="${SKIP_MODEL_DOWNLOAD:-0}"
INSTALL_COMFYUI="${INSTALL_COMFYUI:-0}"
COMFYUI_DIR="${COMFYUI_DIR:-$ROOT/ComfyUI}"

log() {
  printf '\033[1;32m[install_linux]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[install_linux]\033[0m %s\n' "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

need_cmd python3
need_cmd curl

mkdir -p "$LLM_DIR" "$COMFY_MODEL_ROOT" "$TMP_DIR"

if [ ! -x "$PY" ]; then
  log "creating Python venv at $VENV"
  python3 -m venv "$VENV"
fi

log "installing backend dependencies"
"$PIP" install --upgrade pip wheel setuptools
"$PIP" install -r "$ROOT/requirements.txt"

log "installing embedded llama.cpp Python runtime"
if command -v nvidia-smi >/dev/null 2>&1; then
  CMAKE_ARGS="${CMAKE_ARGS:--DGGML_CUDA=on}" "$PIP" install --upgrade --force-reinstall --no-cache-dir llama-cpp-python
else
  "$PIP" install --upgrade llama-cpp-python
fi

log "installing Hugging Face downloader"
"$PIP" install --upgrade "huggingface_hub>=0.24"

if command -v npm >/dev/null 2>&1; then
  log "installing/building frontend"
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit && npm run build)
else
  warn "npm not found; backend will run, but frontend/dist will not be rebuilt"
fi

if [ "$INSTALL_COMFYUI" = "1" ]; then
  need_cmd git
  if [ ! -d "$COMFYUI_DIR/.git" ]; then
    log "cloning ComfyUI into $COMFYUI_DIR"
    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFYUI_DIR"
  fi
  if [ ! -d "$COMFYUI_DIR/custom_nodes/10S-Comfy-nodes" ]; then
    log "cloning TenStrip custom nodes"
    git clone https://github.com/TenStrip/10S-Comfy-nodes.git "$COMFYUI_DIR/custom_nodes/10S-Comfy-nodes"
  fi
fi

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
  log "downloading all configured model repos"
  "$PY" - "$LLM_DIR" "$COMFY_MODEL_ROOT" <<'PY'
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

llm_dir = Path(sys.argv[1])
comfy_root = Path(sys.argv[2])
token = os.environ.get("HF_TOKEN") or None

repos = {
    "prompt": os.environ.get("PROMPT_REPO", "SulphurAI/Sulphur-2-Prompt-Enhancer-GGUF"),
    "base": os.environ.get("BASE_REPO", "Lightricks/LTX-2.3"),
    "i2v": os.environ.get("I2V_REPO", "TenStrip/LTX2.3-10Eros"),
    "t2v": os.environ.get("T2V_REPO", "SulphurAI/Sulphur-2-base"),
    "distil": os.environ.get("DISTIL_REPO", "Kijai/LTX2.3_Distilled_Lora_1.1_Experiments"),
}

def safe_name(repo: str) -> str:
    return repo.replace("/", "__")

def snap(repo: str, dest: Path, patterns=None):
    print(f"[install_linux] snapshot {repo} -> {dest}")
    try:
        snapshot_download(
            repo_id=repo,
            local_dir=str(dest),
            local_dir_use_symlinks=False,
            allow_patterns=patterns,
            token=token,
        )
    except Exception as exc:
        raise SystemExit(
            f"Failed to download {repo}: {exc}\n"
            "If the repo is gated/private, set HF_TOKEN. "
            "If the repo id changed, override PROMPT_REPO/BASE_REPO/I2V_REPO/T2V_REPO/DISTIL_REPO."
        )

snap(repos["prompt"], llm_dir, ["*.gguf", "*.txt", "*.json", "*.md"])

model_patterns = [
    "*.safetensors", "*.gguf", "*.json", "*.txt", "*.yaml", "*.yml", "*.md",
    "*.model", "*.bin", "*.pt", "*.pth",
]
for key in ("base", "i2v", "t2v", "distil"):
    snap(repos[key], comfy_root / safe_name(repos[key]), model_patterns)

ggufs = sorted(p for p in llm_dir.glob("*.gguf") if "mmproj" not in p.name.lower())
mmprojs = sorted(p for p in llm_dir.glob("*.gguf") if "mmproj" in p.name.lower())
if ggufs:
    from backend import db

    db.update_settings({
        "llm_mode": "embedded",
        "llm_gguf": ggufs[0].name,
        "llm_mmproj": mmprojs[0].name if mmprojs else "",
        "mock_llm": "auto",
        "mock_comfy": "auto",
    })
    print(f"[install_linux] embedded LLM default: {ggufs[0].name}")
    if mmprojs:
        print(f"[install_linux] mmproj default: {mmprojs[0].name}")
else:
    print("[install_linux] no GGUF found in prompt repo download")
PY
else
  warn "SKIP_MODEL_DOWNLOAD=1, skipped model downloads"
fi

cat <<EOF

Install complete.

Start the WebUI:
  source "$VENV/bin/activate"
  bash "$ROOT/start_linux.sh"

Open:
  http://127.0.0.1:7860

Free Cloudflare tunnel:
  bash "$ROOT/start_linux.sh" --tunnel

Notes:
  - ComfyUI is optional. Without it, the project runs in Mock render mode.
  - LLM default is embedded mode: GGUF loads inside the backend process.
  - Set HF_TOKEN for gated Hugging Face repositories.
EOF
