# Cinematic Console LD

Cinematic Console LD is a local WebUI for LTX 2.3 video generation. It serves a FastAPI backend and a Vite/React control surface at `http://127.0.0.1:7860`.

The current render path is local LTX only: no ComfyUI server is required, and there is no placeholder renderer. If the LTX dependencies or model files are missing, the UI reports the exact missing item instead of producing a fake video.

## Quick Start

Linux:

```bash
bash install_linux.sh
bash start_linux.sh
```

Open:

```text
http://127.0.0.1:7860
```

Free Cloudflare Quick Tunnel:

```bash
bash start_linux.sh --tunnel
```

Windows development start:

```bat
start.bat
```

Windows can launch the WebUI, but the fully automated model and LTX dependency installer is `install_linux.sh`.

## Architecture

- `backend/main.py`: FastAPI app, REST API, WebSocket status/log events.
- `backend/llm_embedded.py`: in-process llama.cpp GGUF runtime through `llama-cpp-python`.
- `backend/llm_manager.py`: managed `llama-server` compatibility mode.
- `backend/ltx_local_renderer.py`: validates local model files and launches real LTX render jobs.
- `backend/ltx_runner.py`: programmatic wrapper around official `TI2VidTwoStagesHQPipeline`; it loads the selected checkpoint together with split text projection and audio VAE files.
- `backend/local_models.py`: scans `models/ltx/` and `models/llm/` for actual local files.
- `backend/jobs.py`: one-at-a-time render queue, cancellation, WebSocket progress, and final video/thumbnail persistence.
- `frontend/src/`: four-panel console UI.
- `outputs/`: generated MP4 files and thumbnails.
- `uploads/`: uploaded I2V reference images.

## Local LTX Renderer

The renderer uses the official Lightricks packages:

- `ltx-core`
- `ltx-pipelines`
- PyTorch / torchaudio
- `av`
- `openimageio`

`install_linux.sh` clones `https://github.com/Lightricks/LTX-2.git` into `tools/LTX-2` and installs:

```bash
pip install -e tools/LTX-2/packages/ltx-core -e tools/LTX-2/packages/ltx-pipelines
```

The backend launches:

```bash
python -m backend.ltx_runner ...
```

This wrapper still uses the official `TI2VidTwoStagesHQPipeline`; it only adds the project-specific model bundle plumbing needed by the UI.

## Required Model Files

The installer downloads exact files only. It does not snapshot full 100GB+ repositories.

Prompt LLM files go under:

```text
models/llm/
```

Render files go under:

```text
models/ltx/checkpoints/
models/ltx/gemma/
models/ltx/text_projection/
models/ltx/upscale_models/
models/ltx/vae/
models/ltx/loras/
```

Required render files:

```text
I2V checkpoint:
  TenStrip/LTX2.3-10Eros/10Eros_v1-fp8mixed_learned.safetensors

T2V checkpoint:
  SulphurAI/Sulphur-2-base/sulphur_dev_fp8mixed.safetensors

Gemma text encoder weights:
  Comfy-Org/ltx-2/split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors

Gemma auxiliary files:
  google/gemma-3-12b-it/tokenizer.model
  google/gemma-3-12b-it/tokenizer_config.json
  google/gemma-3-12b-it/preprocessor_config.json

Text projection:
  Kijai/LTX2.3_comfy/text_encoders/ltx-2.3_text_projection_bf16.safetensors

Spatial upscaler:
  Lightricks/LTX-2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors

Audio VAE:
  novoluz/ltx2_audio_vae_bf16/LTX2_audio_vae_bf16.safetensors

Cond-safe distill LoRA:
  TenStrip/LTX2.3_Distilled_Lora_1.1_Experiments/ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors
```

Required prompt LLM files:

```text
SulphurAI/Sulphur-2-base/prompt_enhancer_uncensored/prompt_enhancer_uncensored-q8_0.gguf
SulphurAI/Sulphur-2-base/prompt_enhancer_uncensored/mmproj-prompt_enhancer_uncensored.gguf
```

If a Hugging Face repository is gated or private, set:

```bash
export HF_TOKEN=...
```

Every repo and filename can be overridden before running the installer:

```bash
I2V_REPO=... I2V_CHECKPOINT=... bash install_linux.sh
T2V_REPO=... T2V_CHECKPOINT=... bash install_linux.sh
LTX_MODEL_ROOT=/mnt/models/ltx bash install_linux.sh
```

## Prompt LLM

Default mode is `embedded`: the backend loads the GGUF directly with `llama-cpp-python`.

The Settings panel supports:

- `embedded`: recommended local mode.
- `managed`: starts a project-local `llama-server` process.

`setup_llm.bat` remains available for Windows llama.cpp setup and GGUF/mmproj download.

## Render Rules

- I2V requires a reference image upload.
- T2V uses the selected T2V checkpoint.
- Resolution must be divisible by 64 for the two-stage LTX pipeline.
- Frame count is snapped to `8n + 1`.
- Distill LoRA and a complete distilled checkpoint are mutually exclusive.
- Additional LoRAs selected in the Pipeline panel are passed to both render stages.
- The UI strips `[0-12s]` timestamps before rendering by default; this is configurable in Settings.

## Troubleshooting

- Render status is red: open the Pipeline panel and read the missing model list, or run `bash install_linux.sh`.
- LLM status is red: install/download the GGUF and mmproj, then click the LLM status light or load/restart in Settings.
- CUDA out of memory: lower resolution first. On Linux you can also try `LTX_OFFLOAD=cpu bash start_linux.sh`.
- Hugging Face download returns 401: accept the model license if required and set `HF_TOKEN`.
- Frontend missing: install Node.js/npm and run `npm install && npm run build` inside `frontend/`.

## Cloudflare Tunnel

`start_linux.sh --tunnel` downloads `cloudflared` if needed and starts a free temporary `https://*.trycloudflare.com` tunnel to the local WebUI.

Useful options:

```bash
bash start_linux.sh --host 127.0.0.1 --port 7860
bash start_linux.sh --tunnel --no-browser
CC_PORT=9000 bash start_linux.sh --tunnel
```
