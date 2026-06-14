# Cinematic Console LD

Cinematic Console LD is a local WebUI for LTX 2.3 video generation. It serves a FastAPI backend and a Vite/React control surface at `http://127.0.0.1:7860`.

The current render path is local LTX only: no ComfyUI server is required, and there is no fake or demo renderer. If the LTX dependencies, CUDA device, or model files are missing, the UI reports the exact missing item instead of producing a fake video.

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

Local diagnostics after installation:

```bash
python -m backend.ltx_diagnose
python -m backend.ltx_diagnose --json
```

Diagnostics also open the downloaded `.safetensors` headers without loading
tensors into memory. They verify individual files and the complete component
bundle expected by the official loader: transformer, Video VAE, Audio VAE,
vocoder, text projection, and spatial upscaler.

Full real-render verification on Linux/GPU:

```bash
bash verify_linux.sh
```

`verify_linux.sh` runs diagnostics, starts or reuses the WebUI service, submits
one short T2V render and one short I2V render with a synthetic reference card,
then waits until each job writes a decodable MP4 under `outputs/`. It does not
use fake rendering. To only check installation readiness without
launching renders:

```bash
bash verify_linux.sh --skip-render
```

Windows development start:

```bat
start.bat
```

Windows can launch the WebUI, but the fully automated model and LTX dependency installer is `install_linux.sh`.

## GPU Requirement

Real LTX-2.3 rendering requires an NVIDIA CUDA GPU. Diagnostics and `/api/render`
now fail early when `torch.cuda.is_available()` is false, so the UI will not
enqueue a job that can only spin without producing a usable MP4.

For installation or command-construction debugging only, you can bypass this
gate with:

```bash
LTX_ALLOW_CPU=1 bash start_linux.sh
```

CPU rendering is not considered a passing verification target; `verify_linux.sh`
should be run on a CUDA machine and must produce decodable T2V and I2V MP4 files.

## Architecture

- `backend/main.py`: FastAPI app, REST API, WebSocket status/log events.
- `backend/llm_embedded.py`: in-process llama.cpp GGUF runtime through `llama-cpp-python`.
- `backend/llm_manager.py`: managed `llama-server` compatibility mode.
- `backend/ltx_local_renderer.py`: validates local model files and launches real LTX render jobs.
- `backend/ltx_runner.py`: programmatic wrapper around official `TI2VidTwoStagesHQPipeline` and `DistilledPipeline`; it loads the selected checkpoint together with split text projection / audio VAE / optional Video VAE files, and merges split-file metadata before calling the official builders.
- `backend/local_models.py`: scans `models/ltx/` and `models/llm/` for actual local files.
- `backend/jobs.py`: one-at-a-time render queue, cancellation, WebSocket progress, and final video/thumbnail persistence.
- `frontend/src/`: four-panel console UI.
- `outputs/`: generated MP4 files and thumbnails.
- `uploads/`: uploaded I2V reference images.
- `verify_linux.sh`: Linux/GPU end-to-end verifier for diagnostics plus real T2V/I2V MP4 output.

## Local LTX Renderer

The renderer uses the official Lightricks packages:

- `ltx-core`
- `ltx-pipelines`
- PyTorch / torchaudio
- `av`
- `openimageio`
- `sentencepiece` / `protobuf` for local Gemma tokenizer loading

`install_linux.sh` clones `https://github.com/Lightricks/LTX-2.git` into `tools/LTX-2` and installs:

```bash
pip install -e tools/LTX-2/packages/ltx-core -e tools/LTX-2/packages/ltx-pipelines
```

The backend launches:

```bash
python -m backend.ltx_runner ...
```

This wrapper still uses official LTX pipelines. Non-distilled checkpoints run through `TI2VidTwoStagesHQPipeline` with the selected cond-safe distill LoRA; complete distilled checkpoints run through `DistilledPipeline` without a distill LoRA.

## Required Model Files

The installer downloads exact files only. It does not snapshot full 100GB+ repositories.
The list below is the default install and diagnostics manifest; the Pipeline
panel can still select equivalent local files with different filenames, and the
render API validates the selected files instead of forcing default basenames.

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
models/ltx/video_vae/        # optional split Video VAE files
models/ltx/loras/
```

The default Sulphur and 10Eros checkpoints include `vae.*`, `audio_vae.*`,
`vocoder.*`, and `text_embedding_projection.*` keys in their safetensors
headers, so the default installer does not download an extra Video VAE file.
Only transformer-only checkpoints, such as Kijai split diffusion models, need
a matching split Video VAE selected in the Pipeline panel.

Required render files:

```text
I2V checkpoint:
  TenStrip/LTX2.3-10Eros/10Eros_v1-fp8mixed_learned.safetensors

T2V checkpoint:
  SulphurAI/Sulphur-2-base/sulphur_dev_fp8mixed.safetensors

Gemma text encoder weights:
  Comfy-Org/ltx-2/split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors

Gemma auxiliary files:
  DreamFast/gemma-3-12b-it-heretic-v2/tokenizer.model
  DreamFast/gemma-3-12b-it-heretic-v2/tokenizer.json
  DreamFast/gemma-3-12b-it-heretic-v2/tokenizer_config.json
  DreamFast/gemma-3-12b-it-heretic-v2/special_tokens_map.json
  DreamFast/gemma-3-12b-it-heretic-v2/chat_template.jinja
  DreamFast/gemma-3-12b-it-heretic-v2/config.json
  DreamFast/gemma-3-12b-it-heretic-v2/generation_config.json

Gemma image processor config:
  models/ltx/gemma/preprocessor_config.json is generated locally by install_linux.sh
  with the Gemma3 image processor settings required by the official LTX loader.

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

`install_linux.sh` prompts for a Hugging Face token when run interactively.
For non-interactive runs, or if a Hugging Face repository is gated/private, set:

```bash
export HF_TOKEN=...
```

Every repo and filename can be overridden before running the installer:

```bash
I2V_REPO=... I2V_CHECKPOINT=... bash install_linux.sh
T2V_REPO=... T2V_CHECKPOINT=... bash install_linux.sh
LTX_MODEL_ROOT=/mnt/models/ltx bash install_linux.sh
GEMMA_AUX_REPO=google/gemma-3-12b-it GEMMA_CHAT_TEMPLATE=chat_template.json HF_TOKEN=... bash install_linux.sh
```

When `LTX_MODEL_ROOT` or `LLM_DIR` is set during installation, the installer writes
`data/local_paths.env`. `start_linux.sh` sources that file automatically, so the
backend scans the same model directories that the installer populated. At the
end of a successful model download, `install_linux.sh` prints every required
LLM/render file with its local path and size.

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
- CUDA must be available unless `LTX_ALLOW_CPU=1` is explicitly set for debugging.
- Video VAE is optional in the Pipeline panel. When selected, it is added to the official LTX loader bundle. The runner accepts both bundled `vae.encoder/vae.decoder` keys and split `encoder/decoder` Video VAE files.
- Before a render is queued, the backend opens safetensors headers and refuses combinations that do not contain the required transformer, Video VAE, Audio VAE, vocoder, text projection, and upscaler pieces.
- Distill LoRA and a complete distilled checkpoint are mutually exclusive; when a complete distilled checkpoint is selected and both Distil switches are off, the backend uses official `DistilledPipeline`.
- Additional LoRAs selected in the Pipeline panel are passed to both render stages.
- The UI strips `[0-12s]` timestamps before rendering by default; this is configurable in Settings.
- A job is marked complete only after the LTX process writes an MP4 that ffmpeg can decode.
- History playback only exposes completed `local-ltx` jobs whose MP4 still exists and can be decoded.

## Troubleshooting

- Render status is red: open the Pipeline panel and read the missing model list, or run `bash install_linux.sh`.
- GPU status is blocked: install/repair the NVIDIA driver and CUDA-enabled PyTorch. `python -m backend.ltx_diagnose` shows the detected torch/CUDA build and GPU memory.
- LLM status is red: install/download the GGUF and mmproj, then click the LLM status light or load/restart in Settings.
- CUDA out of memory: lower resolution first. On Linux you can also try `LTX_OFFLOAD=cpu bash start_linux.sh`.
- Hugging Face download returns 401: accept the model license if required, then enter `HF_TOKEN` when `install_linux.sh` prompts or export it before running.
- Frontend missing: install Node.js/npm and run `npm install && npm run build` inside `frontend/`.

## Cloudflare Tunnel

`start_linux.sh --tunnel` downloads `cloudflared` if needed and starts a free temporary `https://*.trycloudflare.com` tunnel to the local WebUI.

Useful options:

```bash
bash start_linux.sh --host 127.0.0.1 --port 7860
bash start_linux.sh --tunnel --no-browser
CC_PORT=9000 bash start_linux.sh --tunnel
```
