#!/usr/bin/env bash
set -euo pipefail

# Cinematic Console Linux installer.
#
# What it does:
# - creates .venv and installs backend dependencies
# - installs llama-cpp-python for in-process GGUF inference (no external LLM service)
# - installs the official Lightricks LTX-2 local pipeline packages
# - installs/builds the React frontend when npm is available
# - downloads only the required Prompt Enhancer and LTX model files
# - writes default settings for embedded LLM mode
#
# The model downloads are still large, but this script downloads exact files,
# not full Hugging Face repositories. Set SKIP_MODEL_DOWNLOAD=1 to install code only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

LLM_DIR="${LLM_DIR:-$ROOT/models/llm}"
LTX_MODEL_ROOT="${LTX_MODEL_ROOT:-$ROOT/models/ltx}"
TMP_DIR="${TMP_DIR:-$ROOT/.tmp/linux-install}"
LTX_REPO_URL="${LTX_REPO_URL:-https://github.com/Lightricks/LTX-2.git}"
LTX_DIR="${LTX_DIR:-$ROOT/tools/LTX-2}"

PROMPT_REPO="${PROMPT_REPO:-SulphurAI/Sulphur-2-base}"
PROMPT_GGUF="${PROMPT_GGUF:-prompt_enhancer_uncensored/prompt_enhancer_uncensored-q8_0.gguf}"
PROMPT_MMPROJ="${PROMPT_MMPROJ:-prompt_enhancer_uncensored/mmproj-prompt_enhancer_uncensored.gguf}"
BASE_REPO="${BASE_REPO:-Lightricks/LTX-2.3}"
UPSCALER_MODEL="${UPSCALER_MODEL:-ltx-2.3-spatial-upscaler-x2-1.1.safetensors}"
TEXT_ENCODER_REPO="${TEXT_ENCODER_REPO:-Comfy-Org/ltx-2}"
TEXT_ENCODER_MODEL="${TEXT_ENCODER_MODEL:-split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors}"
GEMMA_AUX_REPO="${GEMMA_AUX_REPO:-google/gemma-3-12b-it}"
GEMMA_TOKENIZER_MODEL="${GEMMA_TOKENIZER_MODEL:-tokenizer.model}"
GEMMA_TOKENIZER_CONFIG="${GEMMA_TOKENIZER_CONFIG:-tokenizer_config.json}"
GEMMA_PREPROCESSOR_CONFIG="${GEMMA_PREPROCESSOR_CONFIG:-preprocessor_config.json}"
TEXT_PROJECTION_REPO="${TEXT_PROJECTION_REPO:-Kijai/LTX2.3_comfy}"
TEXT_PROJECTION_MODEL="${TEXT_PROJECTION_MODEL:-text_encoders/ltx-2.3_text_projection_bf16.safetensors}"
I2V_REPO="${I2V_REPO:-TenStrip/LTX2.3-10Eros}"
I2V_CHECKPOINT="${I2V_CHECKPOINT:-10Eros_v1-fp8mixed_learned.safetensors}"
T2V_REPO="${T2V_REPO:-SulphurAI/Sulphur-2-base}"
T2V_CHECKPOINT="${T2V_CHECKPOINT:-sulphur_dev_fp8mixed.safetensors}"
DISTIL_REPO="${DISTIL_REPO:-TenStrip/LTX2.3_Distilled_Lora_1.1_Experiments}"
DISTIL_LORA="${DISTIL_LORA:-ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors}"
AUDIO_VAE_REPO="${AUDIO_VAE_REPO:-novoluz/ltx2_audio_vae_bf16}"
AUDIO_VAE_MODEL="${AUDIO_VAE_MODEL:-LTX2_audio_vae_bf16.safetensors}"

SKIP_MODEL_DOWNLOAD="${SKIP_MODEL_DOWNLOAD:-0}"

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

mkdir -p "$LLM_DIR" "$LTX_MODEL_ROOT" "$TMP_DIR" "$ROOT/tools"

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

log "installing official LTX-2 local pipeline"
need_cmd git
if [ ! -d "$LTX_DIR/.git" ]; then
  git clone --depth 1 "$LTX_REPO_URL" "$LTX_DIR"
else
  log "using existing $LTX_DIR"
fi
if command -v nvidia-smi >/dev/null 2>&1; then
  "$PIP" install --upgrade "torch~=2.7" torchaudio --index-url https://download.pytorch.org/whl/cu128
fi
"$PIP" install -e "$LTX_DIR/packages/ltx-core" -e "$LTX_DIR/packages/ltx-pipelines"

if command -v npm >/dev/null 2>&1; then
  log "installing/building frontend"
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit && npm run build)
else
  warn "npm not found; backend will run, but frontend/dist will not be rebuilt"
fi

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
  log "downloading required model files only"
  export PROMPT_REPO PROMPT_GGUF PROMPT_MMPROJ BASE_REPO UPSCALER_MODEL TEXT_ENCODER_REPO TEXT_ENCODER_MODEL GEMMA_AUX_REPO GEMMA_TOKENIZER_MODEL GEMMA_TOKENIZER_CONFIG GEMMA_PREPROCESSOR_CONFIG TEXT_PROJECTION_REPO TEXT_PROJECTION_MODEL I2V_REPO I2V_CHECKPOINT T2V_REPO T2V_CHECKPOINT DISTIL_REPO DISTIL_LORA AUDIO_VAE_REPO AUDIO_VAE_MODEL
  "$PY" - "$ROOT" "$LLM_DIR" "$LTX_MODEL_ROOT" <<'PY'
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

root = Path(sys.argv[1])
llm_dir = Path(sys.argv[2])
ltx_root = Path(sys.argv[3])
sys.path.insert(0, str(root))

from backend import db, local_models, model_manifest

token = os.environ.get("HF_TOKEN") or None

def download_file(repo: str, filename: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / Path(filename).name
    if target.exists():
        print(f"[install_linux] using existing {target}")
        return target
    print(f"[install_linux] file {repo}/{filename} -> {target}")
    try:
        downloaded = Path(hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=str(dest),
            token=token,
        ))
    except Exception as exc:
        raise SystemExit(
            f"Failed to download {repo}/{filename}: {exc}\n"
            "If the repo is gated/private, set HF_TOKEN. "
            "If the path changed, override the matching *_REPO or *_MODEL variable."
        )
    if downloaded.resolve() != target.resolve():
        shutil.move(str(downloaded), target)
        parent = downloaded.parent
        while parent != dest and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return target

for item in model_manifest.required_llm_files():
    download_file(item["repo"], item["filename"], llm_dir)

for item in model_manifest.required_render_files():
    download_file(item["repo"], item["filename"], ltx_root / item["category"])

text_encoder = local_models.find_required_render_file("text_encoder")
if text_encoder is not None:
    alias = text_encoder.parent / "model.safetensors"
    if not alias.exists() and not any(text_encoder.parent.rglob("model*.safetensors")):
        try:
            alias.symlink_to(text_encoder.name)
            print(f"[install_linux] created Gemma alias {alias.name} -> {text_encoder.name}")
        except OSError:
            try:
                os.link(text_encoder, alias)
                print(f"[install_linux] created Gemma hardlink {alias.name}")
            except OSError as exc:
                raise SystemExit(
                    f"Gemma text encoder downloaded, but could not create model.safetensors alias: {exc}\n"
                    f"Create it manually in {text_encoder.parent}: ln -s {text_encoder.name} model.safetensors"
                )

ggufs = sorted(p for p in llm_dir.glob("*.gguf") if "mmproj" not in p.name.lower())
mmprojs = sorted(p for p in llm_dir.glob("*.gguf") if "mmproj" in p.name.lower())
if ggufs:
    db.update_settings({
        "llm_mode": "embedded",
        "llm_gguf": ggufs[0].name,
        "llm_mmproj": mmprojs[0].name if mmprojs else "",
    })
    print(f"[install_linux] embedded LLM default: {ggufs[0].name}")
    if mmprojs:
        print(f"[install_linux] mmproj default: {mmprojs[0].name}")
else:
    print("[install_linux] no GGUF found in prompt repo download")

render_scan = local_models.scan_render_models()
llm_scan = local_models.scan_llm_models()
missing = llm_scan["missing_required"] + render_scan["missing_required"]
if missing:
    print("[install_linux] missing required model files:")
    for item in missing:
        print(f"  - {item['label']}: {item['name']} ({item['url']})")
    raise SystemExit(1)
print("[install_linux] required model file check OK")
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
  - Rendering uses the official local LTX pipeline; no ComfyUI or placeholder renderer is started.
  - LLM default is embedded mode: GGUF loads inside the backend process.
  - Set HF_TOKEN for gated Hugging Face repositories.
EOF
