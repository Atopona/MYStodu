"""Required local model files for the default Cinematic Console workflows."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def basename(filename: str) -> str:
    return Path(filename).name


def required_llm_files() -> List[Dict[str, str]]:
    prompt_repo = _env("PROMPT_REPO", "SulphurAI/Sulphur-2-base")
    return [
        {
            "key": "prompt_gguf",
            "label": "Sulphur Prompt Enhancer GGUF",
            "category": "llm",
            "repo": prompt_repo,
            "filename": _env(
                "PROMPT_GGUF",
                "prompt_enhancer_uncensored/prompt_enhancer_uncensored-q8_0.gguf",
            ),
        },
        {
            "key": "prompt_mmproj",
            "label": "Sulphur Prompt Enhancer mmproj",
            "category": "llm",
            "repo": prompt_repo,
            "filename": _env(
                "PROMPT_MMPROJ",
                "prompt_enhancer_uncensored/mmproj-prompt_enhancer_uncensored.gguf",
            ),
        },
    ]


def required_render_files() -> List[Dict[str, str]]:
    return [
        {
            "key": "i2v_checkpoint",
            "label": "I2V 10Eros checkpoint",
            "category": "checkpoints",
            "repo": _env("I2V_REPO", "TenStrip/LTX2.3-10Eros"),
            "filename": _env("I2V_CHECKPOINT", "10Eros_v1-fp8mixed_learned.safetensors"),
        },
        {
            "key": "text_encoder",
            "label": "Gemma 3 12B text encoder",
            "category": "text_encoders",
            "repo": _env("TEXT_ENCODER_REPO", "Comfy-Org/ltx-2"),
            "filename": _env(
                "TEXT_ENCODER_MODEL",
                "split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
            ),
        },
        {
            "key": "text_projection",
            "label": "LTX 2.3 text projection",
            "category": "text_encoders",
            "repo": _env("TEXT_PROJECTION_REPO", "Kijai/LTX2.3_comfy"),
            "filename": _env(
                "TEXT_PROJECTION_MODEL",
                "text_encoders/ltx-2.3_text_projection_bf16.safetensors",
            ),
        },
        {
            "key": "t2v_checkpoint",
            "label": "T2V Sulphur checkpoint",
            "category": "checkpoints",
            "repo": _env("T2V_REPO", "SulphurAI/Sulphur-2-base"),
            "filename": _env("T2V_CHECKPOINT", "sulphur_dev_fp8mixed.safetensors"),
        },
        {
            "key": "spatial_upscaler",
            "label": "LTX 2.3 x2 spatial upscaler",
            "category": "upscale_models",
            "repo": _env("BASE_REPO", "Lightricks/LTX-2.3"),
            "filename": _env("UPSCALER_MODEL", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),
        },
        {
            "key": "audio_vae",
            "label": "LTX audio VAE",
            "category": "vae",
            "repo": _env("AUDIO_VAE_REPO", "novoluz/ltx2_audio_vae_bf16"),
            "filename": _env("AUDIO_VAE_MODEL", "LTX2_audio_vae_bf16.safetensors"),
        },
        {
            "key": "distil_lora",
            "label": "LTX 2.3 cond_safe distill LoRA",
            "category": "loras",
            "repo": _env("DISTIL_REPO", "TenStrip/LTX2.3_Distilled_Lora_1.1_Experiments"),
            "filename": _env(
                "DISTIL_LORA",
                "ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors",
            ),
        },
    ]


def required_model_files() -> List[Dict[str, str]]:
    return required_llm_files() + required_render_files()


def public_entry(entry: Dict[str, str]) -> Dict[str, str]:
    return {
        **entry,
        "name": basename(entry["filename"]),
        "url": f"https://huggingface.co/{entry['repo']}/resolve/main/{entry['filename']}",
    }
