"""Required local model files for the default Cinematic Console pipelines."""
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
    gemma_aux_repo = _env("GEMMA_AUX_REPO", "DreamFast/gemma-3-12b-it-heretic-v2")
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
            "category": "gemma",
            "repo": _env("TEXT_ENCODER_REPO", "Comfy-Org/ltx-2"),
            "filename": _env(
                "TEXT_ENCODER_MODEL",
                "split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors",
            ),
        },
        {
            "key": "gemma_tokenizer",
            "label": "Gemma tokenizer",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_TOKENIZER_MODEL", "tokenizer.model"),
        },
        {
            "key": "gemma_tokenizer_json",
            "label": "Gemma tokenizer JSON",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_TOKENIZER_JSON", "tokenizer.json"),
        },
        {
            "key": "gemma_tokenizer_config",
            "label": "Gemma tokenizer config",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_TOKENIZER_CONFIG", "tokenizer_config.json"),
        },
        {
            "key": "gemma_special_tokens",
            "label": "Gemma special tokens map",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_SPECIAL_TOKENS_MAP", "special_tokens_map.json"),
        },
        {
            "key": "gemma_chat_template",
            "label": "Gemma chat template",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_CHAT_TEMPLATE", "chat_template.jinja"),
        },
        {
            "key": "gemma_config",
            "label": "Gemma model config",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_CONFIG", "config.json"),
        },
        {
            "key": "gemma_generation_config",
            "label": "Gemma generation config",
            "category": "gemma",
            "repo": gemma_aux_repo,
            "filename": _env("GEMMA_GENERATION_CONFIG", "generation_config.json"),
        },
        {
            "key": "text_projection",
            "label": "LTX 2.3 text projection",
            "category": "text_projection",
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
