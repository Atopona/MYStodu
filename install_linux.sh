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
cd "$ROOT"
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
GEMMA_AUX_REPO="${GEMMA_AUX_REPO:-DreamFast/gemma-3-12b-it-heretic-v2}"
GEMMA_TOKENIZER_MODEL="${GEMMA_TOKENIZER_MODEL:-tokenizer.model}"
GEMMA_TOKENIZER_JSON="${GEMMA_TOKENIZER_JSON:-tokenizer.json}"
GEMMA_TOKENIZER_CONFIG="${GEMMA_TOKENIZER_CONFIG:-tokenizer_config.json}"
GEMMA_SPECIAL_TOKENS_MAP="${GEMMA_SPECIAL_TOKENS_MAP:-special_tokens_map.json}"
GEMMA_CHAT_TEMPLATE="${GEMMA_CHAT_TEMPLATE:-chat_template.jinja}"
GEMMA_CONFIG="${GEMMA_CONFIG:-config.json}"
GEMMA_GENERATION_CONFIG="${GEMMA_GENERATION_CONFIG:-generation_config.json}"
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
export LLM_DIR LTX_MODEL_ROOT

usage() {
  cat <<'EOF'
Cinematic Console Linux installer

Usage:
  bash install_linux.sh [options]

Options:
  --hf-token TOKEN            Hugging Face token for gated/private repos
  --hf-token=TOKEN            Same as above
  --no-hf-token-prompt        Do not prompt for a token when HF_TOKEN is unset
  --skip-model-download       Install code/dependencies only
  --help                      Show this help

Examples:
  bash install_linux.sh --hf-token hf_xxx
  bash install_linux.sh --skip-model-download
  GEMMA_AUX_REPO=google/gemma-3-12b-it bash install_linux.sh --hf-token hf_xxx
EOF
}

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

while [ $# -gt 0 ]; do
  case "$1" in
    --hf-token)
      [ $# -ge 2 ] || { echo "--hf-token needs a value" >&2; exit 1; }
      HF_TOKEN="$2"
      export HF_TOKEN
      shift 2
      ;;
    --hf-token=*)
      HF_TOKEN="${1#--hf-token=}"
      export HF_TOKEN
      shift
      ;;
    --no-hf-token-prompt)
      HF_TOKEN_PROMPT=0
      export HF_TOKEN_PROMPT
      shift
      ;;
    --skip-model-download)
      SKIP_MODEL_DOWNLOAD=1
      export SKIP_MODEL_DOWNLOAD
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd python3
need_cmd curl

load_hf_token() {
  if [ -n "${HF_TOKEN:-}" ]; then
    export HF_TOKEN
    log "HF_TOKEN detected in environment for gated/private Hugging Face files"
    return
  fi
  if [ "${SKIP_MODEL_DOWNLOAD:-0}" = "1" ]; then
    return
  fi
  if [ "${HF_TOKEN_PROMPT:-1}" = "0" ]; then
    return
  fi
  if [ -t 0 ]; then
    printf '\033[1;33m[install_linux]\033[0m Hugging Face token (optional; press Enter to skip): '
    IFS= read -r -s token_input || true
    printf '\n'
    if [ -n "${token_input:-}" ]; then
      HF_TOKEN="$token_input"
      export HF_TOKEN
      log "HF_TOKEN loaded for this installer run"
    fi
  else
    warn "HF_TOKEN not set and stdin is not interactive; gated repos will fail unless you export HF_TOKEN first"
  fi
}

load_hf_token

mkdir -p "$LLM_DIR" "$LTX_MODEL_ROOT" "$TMP_DIR" "$ROOT/tools" "$ROOT/data"
{
  printf 'export LLM_DIR=%q\n' "$LLM_DIR"
  printf 'export LTX_MODEL_ROOT=%q\n' "$LTX_MODEL_ROOT"
} > "$ROOT/data/local_paths.env"

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

log "installing Gemma tokenizer runtime dependencies"
"$PIP" install --upgrade sentencepiece protobuf

log "installing official LTX-2 local pipeline"
need_cmd git
if [ ! -d "$LTX_DIR/.git" ]; then
  git clone --depth 1 "$LTX_REPO_URL" "$LTX_DIR"
else
  log "using existing $LTX_DIR"
fi
if command -v nvidia-smi >/dev/null 2>&1; then
  "$PIP" install --upgrade "torch~=2.7" torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
fi
"$PIP" install -e "$LTX_DIR/packages/ltx-core" -e "$LTX_DIR/packages/ltx-pipelines"

log "verifying local LTX runtime imports"
"$PY" - <<'PY'
import importlib
import sys

required = [
    ("torch", "torch"),
    ("torchvision", "torchvision"),
    ("torchaudio", "torchaudio"),
    ("transformers", "transformers"),
    ("safetensors", "safetensors"),
    ("accelerate", "accelerate"),
    ("scipy", "scipy"),
    ("einops", "einops"),
    ("sentencepiece", "sentencepiece"),
    ("av", "av"),
    ("imageio_ffmpeg", "imageio-ffmpeg"),
    ("OpenImageIO", "openimageio"),
    ("tqdm", "tqdm"),
    ("ltx_core.loader", "ltx-core"),
    ("ltx_pipelines.ti2vid_two_stages_hq", "ltx-pipelines"),
    ("ltx_pipelines.distilled", "ltx-pipelines"),
]

failed = []
for module, package in required:
    try:
        importlib.import_module(module)
    except Exception as exc:
        failed.append((module, package, exc))

if failed:
    print("[install_linux] local LTX runtime import check failed:", file=sys.stderr)
    for module, package, exc in failed:
        print(f"  - {package} ({module}): {exc}", file=sys.stderr)
    raise SystemExit(1)
print("[install_linux] local LTX runtime import check OK")
PY

case "${LTX_ALLOW_CPU:-0}" in
  1|true|TRUE|yes|YES|on|ON)
    ALLOW_CPU_RENDER=1
    ;;
  *)
    ALLOW_CPU_RENDER=0
    ;;
esac

if [ "$ALLOW_CPU_RENDER" != "1" ]; then
  log "verifying CUDA GPU for real LTX rendering"
  "$PY" - <<'PY'
import sys

import torch

if not torch.cuda.is_available():
    build = torch.version.cuda or "CPU-only PyTorch"
    print(
        "[install_linux] CUDA GPU is required for usable LTX-2.3 rendering. "
        f"Current PyTorch CUDA build: {build}. "
        "Install an NVIDIA driver/CUDA PyTorch stack, or set LTX_ALLOW_CPU=1 only for slow diagnostics.",
        file=sys.stderr,
    )
    raise SystemExit(1)

idx = torch.cuda.current_device()
props = torch.cuda.get_device_properties(idx)
print(
    "[install_linux] CUDA OK: "
    f"{props.name} ({props.total_memory / 1024 / 1024 / 1024:.1f} GB VRAM)"
)
PY
else
  warn "LTX_ALLOW_CPU=1 set; CUDA gate is bypassed for debugging only"
fi

log "verifying project LTX runner entrypoint"
"$PY" -m backend.ltx_runner --help >/dev/null

if command -v npm >/dev/null 2>&1; then
  log "installing/building frontend"
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit && npm run build)
elif [ -f "$ROOT/frontend/dist/index.html" ]; then
  warn "npm not found; using existing frontend/dist build"
else
  echo "[install_linux] npm not found and frontend/dist is missing; install Node.js/npm or provide a built frontend/dist before starting the WebUI." >&2
  exit 1
fi

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
  log "downloading required model files only"
  export PROMPT_REPO PROMPT_GGUF PROMPT_MMPROJ BASE_REPO UPSCALER_MODEL TEXT_ENCODER_REPO TEXT_ENCODER_MODEL GEMMA_AUX_REPO GEMMA_TOKENIZER_MODEL GEMMA_TOKENIZER_JSON GEMMA_TOKENIZER_CONFIG GEMMA_SPECIAL_TOKENS_MAP GEMMA_CHAT_TEMPLATE GEMMA_CONFIG GEMMA_GENERATION_CONFIG TEXT_PROJECTION_REPO TEXT_PROJECTION_MODEL I2V_REPO I2V_CHECKPOINT T2V_REPO T2V_CHECKPOINT DISTIL_REPO DISTIL_LORA AUDIO_VAE_REPO AUDIO_VAE_MODEL
  "$PY" - "$ROOT" "$LLM_DIR" "$LTX_MODEL_ROOT" <<'PY'
import json
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

GEMMA3_PREPROCESSOR_CONFIG = {
    "do_convert_rgb": True,
    "do_normalize": True,
    "do_pan_and_scan": True,
    "do_rescale": True,
    "do_resize": True,
    "image_mean": [0.5, 0.5, 0.5],
    "image_processor_type": "Gemma3ImageProcessor",
    "image_std": [0.5, 0.5, 0.5],
    "pan_and_scan_max_num_crops": 4,
    "pan_and_scan_min_crop_size": 256,
    "pan_and_scan_min_ratio_to_activate": 1.2,
    "processor_class": "Gemma3Processor",
    "resample": 2,
    "rescale_factor": 0.00392156862745098,
    "size": {"height": 896, "width": 896},
}

def download_file(repo: str, filename: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / Path(filename).name
    if target.exists():
        if target.stat().st_size <= 0:
            print(f"[install_linux] removing empty file {target}")
            target.unlink()
        else:
            print(f"[install_linux] using existing {target}")
            return target
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
            "If the repo is gated/private, set HF_TOKEN or rerun install_linux.sh and enter the token when prompted. "
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
    if not target.exists() or target.stat().st_size <= 0:
        raise SystemExit(f"Downloaded file is missing or empty: {target}")
    return target

for item in model_manifest.required_llm_files():
    download_file(item["repo"], item["filename"], llm_dir)

for item in model_manifest.required_render_files():
    download_file(item["repo"], item["filename"], ltx_root / item["category"])

text_encoder = local_models.find_required_render_file("text_encoder")
if text_encoder is not None:
    alias_dir = text_encoder.parent / "ltx_gemma_model"
    alias = alias_dir / "model.safetensors"
    if alias.exists() and alias.stat().st_size <= 0:
        alias.unlink()
    if not alias.exists() and not any(p.is_file() and p.stat().st_size > 0 for p in text_encoder.parent.rglob("model*.safetensors")):
        alias_dir.mkdir(parents=True, exist_ok=True)
        try:
            alias.symlink_to(text_encoder)
            print(f"[install_linux] created Gemma alias {alias.name} -> {text_encoder.name}")
        except OSError:
            try:
                os.link(text_encoder, alias)
                print(f"[install_linux] created Gemma hardlink {alias.name}")
            except OSError as exc:
                raise SystemExit(
                    f"Gemma text encoder downloaded, but could not create model.safetensors alias: {exc}\n"
                    f"Create it manually with: mkdir -p {alias_dir} && ln -s {text_encoder} {alias}"
                )
    if not any(p.is_file() and p.stat().st_size > 0 for p in text_encoder.parent.rglob("model*.safetensors")):
        raise SystemExit(
            "Gemma text encoder is present, but no model*.safetensors alias is visible under "
            f"{text_encoder.parent}"
        )
    preprocessor = text_encoder.parent / "preprocessor_config.json"
    if not preprocessor.exists() or preprocessor.stat().st_size <= 0:
        preprocessor.write_text(
            json.dumps(GEMMA3_PREPROCESSOR_CONFIG, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[install_linux] wrote Gemma3 image processor config -> {preprocessor}")

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

def fmt_size(path: Path) -> str:
    size = float(path.stat().st_size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return str(path.stat().st_size)

print("[install_linux] required LLM files on disk:")
for item in model_manifest.required_llm_files():
    path = local_models.find_required_llm_file(item["key"])
    print(f"  - {item['label']}: {path} ({fmt_size(path) if path else 'missing'})")

print("[install_linux] required render files on disk:")
for item in model_manifest.required_render_files():
    path = local_models.find_required_render_file(item["key"])
    print(f"  - {item['label']}: {path} ({fmt_size(path) if path else 'missing'})")
PY
  log "running full local LTX diagnostics"
  "$PY" -m backend.ltx_diagnose --fail
else
  warn "SKIP_MODEL_DOWNLOAD=1, skipped model downloads"
  "$PY" -m backend.ltx_diagnose || true
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
  - Rendering uses the official local LTX pipeline; no ComfyUI or fake/demo renderer is started.
  - Real rendering requires NVIDIA CUDA. LTX_ALLOW_CPU=1 only bypasses the gate for very slow debugging.
  - LLM default is embedded mode: GGUF loads inside the backend process.
  - HF_TOKEN can be entered when prompted, or exported before running for gated Hugging Face repositories.
EOF
