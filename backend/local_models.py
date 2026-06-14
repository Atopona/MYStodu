"""Local model directory scanner.

The UI should reflect files that are actually present on disk. It must not
invent example model names just because ComfyUI is unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List

from . import config, model_manifest

MODEL_EXTS = {".safetensors", ".gguf", ".pt", ".pth", ".bin", ".model"}


def _files(root: str) -> List[Path]:
    base = Path(root)
    if not base.exists():
        return []
    out: List[Path] = []
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in MODEL_EXTS:
            out.append(path)
    return sorted(out, key=lambda p: str(p).lower())


def _names(paths: Iterable[Path]) -> List[str]:
    seen = set()
    out: List[str] = []
    for path in paths:
        name = path.name
        key = name.lower()
        if key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _contains(path: Path, *needles: str) -> bool:
    hay = str(path).replace("\\", "/").lower()
    return any(n.lower() in hay for n in needles)


def _missing(required: List[Dict[str, str]], roots: List[str]) -> List[Dict[str, str]]:
    existing = {p.name.lower() for root in roots for p in _files(root)}
    missing = []
    for item in required:
        name = model_manifest.basename(item["filename"])
        if name.lower() not in existing:
            missing.append(model_manifest.public_entry(item))
    return missing


def scan_render_models() -> dict:
    root = config.COMFY_MODEL_DIR
    files = _files(root)

    loras = [p for p in files if _contains(p, "lora")]
    upscalers = [p for p in files if _contains(p, "upscaler", "upscale_models")]
    audio_vaes = [p for p in files if _contains(p, "audio_vae", "vae")]
    preview_vaes = [p for p in files if _contains(p, "tae", "preview")]
    text_projections = [p for p in files if _contains(p, "projection", "text_projection")]
    text_encoders = [p for p in files if _contains(p, "gemma", "clip", "t5", "text_encoder")]
    checkpoints = [
        p for p in files
        if p.suffix.lower() == ".safetensors"
        and p not in loras
        and p not in upscalers
        and p not in audio_vaes
        and p not in preview_vaes
        and p not in text_projections
        and p not in text_encoders
    ]

    required = [model_manifest.public_entry(i) for i in model_manifest.required_render_files()]
    missing = _missing(model_manifest.required_render_files(), [root])

    return {
        "text_encoders": _names(text_encoders),
        "text_projections": _names(text_projections),
        "upscalers": _names(upscalers),
        "audio_vaes": _names(audio_vaes),
        "preview_vaes": _names(preview_vaes),
        "checkpoints": _names(checkpoints),
        "loras": _names(loras),
        "source": "local",
        "model_root": root,
        "required": required,
        "missing_required": missing,
        "ready": not missing,
    }


def scan_llm_models() -> dict:
    root = config.LLM_MODEL_DIR
    files = _files(root)
    ggufs = [p for p in files if p.suffix.lower() == ".gguf" and "mmproj" not in p.name.lower()]
    mmprojs = [p for p in files if p.suffix.lower() == ".gguf" and "mmproj" in p.name.lower()]
    required = [model_manifest.public_entry(i) for i in model_manifest.required_llm_files()]
    missing = _missing(model_manifest.required_llm_files(), [root])
    return {
        "ggufs": _names(ggufs),
        "mmprojs": _names(mmprojs),
        "suggested": False,
        "source": "local",
        "model_root": root,
        "required": required,
        "missing_required": missing,
        "ready": not missing,
    }
