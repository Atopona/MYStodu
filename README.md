# Cinematic Console LD

Cinematic Console LD is a local WebUI for LTX 2.3 video generation. It runs a FastAPI backend and a Vite/React control surface at `http://127.0.0.1:7860`, with embedded LLM support and local Mock rendering so the whole flow can be tested on a clean machine. The UI is bilingual English/Chinese for the main workflow controls.

## Quick Start

```bat
start.bat
```

or:

```bat
python run.py
```

`start.bat` creates `.venv`, installs Python dependencies, builds the frontend when needed, then starts the backend. The backend serves the built React app from `frontend/dist`.

Linux install:

```bash
bash install_linux.sh
bash start_linux.sh
```

`install_linux.sh` installs the embedded LLM runtime (`llama-cpp-python`), builds the frontend when `npm` is available, and downloads only the exact GGUF/mmproj plus LTX/10Eros/Sulphur files required by the default workflows. The current Windows workspace does not need to run it unless you intentionally want to download those large files here.

Linux daily start:

```bash
bash start_linux.sh
```

The start script creates `.venv` if needed, installs backend dependencies when missing, builds `frontend/dist` when needed, then starts the WebUI on `http://127.0.0.1:7860`.

## Cloudflare Free Tunnel

For a temporary public URL without configuring a domain or a Cloudflare account, use Cloudflare Quick Tunnel:

```bash
bash start_linux.sh --tunnel
```

or:

```bash
CC_TUNNEL=cloudflare bash start_linux.sh
```

The script downloads `cloudflared` into `tools/cloudflared/` if it is not already installed, starts:

```bash
cloudflared tunnel --url http://127.0.0.1:7860
```

and prints the generated `https://*.trycloudflare.com` URL. Useful options:

```bash
bash start_linux.sh --host 127.0.0.1 --port 9000 --tunnel
CC_TUNNEL_TARGET=http://127.0.0.1:9000 bash start_linux.sh --port 9000 --tunnel
CLOUDFLARED_BIN=/usr/local/bin/cloudflared bash start_linux.sh --tunnel
```

Quick Tunnel URLs are temporary. For production or a stable custom hostname, use Cloudflare named tunnels outside this script.

## Architecture

- `backend/main.py`: FastAPI app, REST endpoints, WebSocket status/log stream, static frontend hosting.
- `backend/llm_embedded.py`: preferred in-process llama.cpp runtime via `llama-cpp-python`; this loads GGUF inside the backend process and does not require an external LLM service.
- `backend/llm_manager.py`: compatibility fallback for a project-local `llama-server` subprocess.
- `backend/llm_client.py`: OpenAI-compatible chat completions, including base64 `image_url` input.
- `backend/local_models.py`: direct local model scanning for `models/llm/` and `models/comfyui/`.
- `backend/comfy_client.py`: optional ComfyUI `/prompt`, `/ws`, `/history`, upload and download helpers for real external rendering.
- `backend/jobs.py`: one-at-a-time render queue, WebSocket progress, mock and real render paths.
- `backend/db.py`: SQLite settings and render history in `data/console.db`.
- `backend/workflows/`: API-format ComfyUI templates plus node mapping.
- `frontend/src/`: four-column React console: Pipeline, Director Input, Generated Prompt, Render Bay.

## Mock Flow

Mock mode is the default fallback when LLM or ComfyUI are unreachable. In the UI:

1. Upload a reference image in I2V mode.
2. Click `GENERATE` to produce a beat-based prompt.
3. Enter a Refine instruction and click `REFINE`.
4. Adjust sliders or pipeline options.
5. Click `RENDER`.
6. Watch queue progress, live preview frames, final placeholder video, and history reuse.

The mock renderer uses `ffmpeg` through `imageio-ffmpeg` when system ffmpeg is unavailable.

### Local Model Detection

The Pipeline panel and LLM selector scan local disk directly. They show only files that actually exist under `models/comfyui/` and `models/llm/`. If required files are missing, the UI lists the missing filenames instead of showing placeholder model names.

## Embedded LLM And Prompt Enhancer Setup

The preferred mode is `embedded`: the backend process loads the GGUF directly with `llama-cpp-python`. You do not need to start llama-server, LM Studio, Ollama, or any external OpenAI-compatible service.

On Linux, run:

```bash
bash install_linux.sh
```

Useful Linux environment variables:

```bash
HF_TOKEN=hf_xxx bash install_linux.sh
SKIP_MODEL_DOWNLOAD=1 bash install_linux.sh
PROMPT_REPO=SulphurAI/Sulphur-2-base bash install_linux.sh
COMFY_MODEL_ROOT=/mnt/models/comfyui bash install_linux.sh
DISTIL_REPO=TenStrip/LTX2.3_Distilled_Lora_1.1_Experiments bash install_linux.sh
```

The script downloads exact required files, not full model repositories. Prompt Enhancer files go to `models/llm/`; render model files go to `models/comfyui/checkpoints/`, `models/comfyui/upscale_models/`, `models/comfyui/vae/`, and `models/comfyui/loras/`. It also writes `llm_mode=embedded` into `data/console.db`.

Verified default Hugging Face sources:

```text
LLM GGUF:        SulphurAI/Sulphur-2-base/prompt_enhancer_uncensored/prompt_enhancer_uncensored-q8_0.gguf
LLM mmproj:      SulphurAI/Sulphur-2-base/prompt_enhancer_uncensored/mmproj-prompt_enhancer_uncensored.gguf
I2V checkpoint:  TenStrip/LTX2.3-10Eros/10Eros_v1-fp8mixed_learned.safetensors
T2V checkpoint:  SulphurAI/Sulphur-2-base/sulphur_dev_fp8mixed.safetensors
Spatial upscale: Lightricks/LTX-2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors
Audio VAE:       novoluz/ltx2_audio_vae_bf16/LTX2_audio_vae_bf16.safetensors
Distill LoRA:    TenStrip/LTX2.3_Distilled_Lora_1.1_Experiments/ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors
```

If you prefer the non-uncensored Prompt Enhancer variant, override:

```bash
PROMPT_GGUF=prompt_enhancer/sulphur_prompt_enhancer_model-q8_0.gguf \
PROMPT_MMPROJ=prompt_enhancer/mmproj-BF16.gguf \
bash install_linux.sh
```

## Windows llama.cpp Compatibility Setup

Run:

```bat
setup_llm.bat
```

The Windows helper remains as a compatibility path. It downloads a Windows llama.cpp release, installs `llama-server.exe` under `tools/llama.cpp/`, downloads the selected GGUF and mmproj files to `models/llm/`, and writes those choices to the console settings database. For the no-external-service path, use embedded mode with `llama-cpp-python`.

Useful variants:

```bat
set HF_TOKEN=hf_xxx
setup_llm.bat
```

```bat
set CC_LLM_REPO=SulphurAI/Sulphur-2-base
setup_llm.bat
```

```bat
setup_llm.bat -Gguf https://huggingface.co/<repo>/resolve/main/model.gguf -Mmproj https://huggingface.co/<repo>/resolve/main/mmproj.gguf
```

The intended default model is the SulphurAI Prompt Enhancer GGUF plus its matching mmproj. In embedded mode, it is loaded directly inside the backend process. For Sulphur Prompt Enhancer style, the backend sends only user text and optional image content. For generic VLMs, set `Prompt style` to `director` in Settings to enable the built-in director system prompt.

External OpenAI-compatible endpoints are kept only for old/debug configurations and are not the normal product path.

## Render Models

External ComfyUI is optional. Without it, the project still works in local Mock render mode: upload image, generate/refine prompts, simulate progress, produce placeholder MP4s, and reuse history. Model detection does not require ComfyUI; `/api/models` scans `models/comfyui/` directly.

For real LTX rendering, set the ComfyUI URL in Settings, default:

```text
http://127.0.0.1:8188
```

The default workflow templates require only these render-side files:

- `checkpoints/10Eros_v1-fp8mixed_learned.safetensors`
- `checkpoints/sulphur_dev_fp8mixed.safetensors`
- `upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors`
- `vae/LTX2_audio_vae_bf16.safetensors`
- `loras/ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors`

Important: do not stack a distill LoRA on top of a complete distilled checkpoint. The UI and backend validate this and will show a conflict error.

On Linux, `install_linux.sh` downloads only those files. You can set `COMFY_MODEL_ROOT` to a shared model storage path before running the script.

## Workflow Templates

Templates live in:

```text
backend/workflows/i2v_10eros.json
backend/workflows/t2v_sulphur.json
backend/workflows/node_map.json
```

To use your own workflow:

1. In ComfyUI, export with `Save (API format)`.
2. Put the JSON file in `backend/workflows/`.
3. Edit `node_map.json` and set the `template` field.
4. Map logical inputs such as `positive_prompt`, `negative_prompt`, `seed`, `width`, `height`, `frames`, `fps`, `image`, `checkpoint`, model loaders, and pass progress nodes to your node ids and input names.

`decode_tile` can switch the mapped decode node to `VAEDecodeTiled` for low-VRAM recovery. Parameters not present in a stock workflow can be mapped to custom nodes as needed.

## Outputs And History

- Uploaded reference images: `uploads/`
- Rendered videos: `outputs/`
- Thumbnails: `outputs/thumbs/`
- Settings and history: `data/console.db`

The history modal can play finished renders, inspect prompt snapshots, reuse parameters, and delete records.

## Troubleshooting

- LLM light red: in embedded mode, run `install_linux.sh` or install `llama-cpp-python`, verify GGUF/mmproj paths in Settings, then click `load / restart llm`.
- Pipeline lists are empty: the app scanned `models/comfyui/` and did not find local render models. Run `bash install_linux.sh` or place the required files under the category folders listed above.
- Render status is yellow/red: local Mock render still allows full UI testing. Configure an external ComfyUI URL only if you want real LTX rendering through ComfyUI.
- VRAM/OOM: set `decode tile` to `512`, lower resolution, or use fp8/quantized model variants.
- Frontend missing: run `npm install` and `npm run build` inside `frontend/`, or rerun `start.bat`.
- Gated Hugging Face models: set `HF_TOKEN` before running `install_linux.sh` or `setup_llm.bat`.
