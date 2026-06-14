"""Local model directory scanner.

The UI reflects files that are actually present on disk and never invents
example model names when the renderer is unavailable.
"""
from __future__ import annotations

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


def _all_files(root: str) -> List[Path]:
    base = Path(root)
    if not base.exists():
        return []
    return sorted((p for p in base.rglob("*") if p.is_file()), key=lambda p: str(p).lower())


def _render_roots() -> List[str]:
    return [root for root in config.RENDER_MODEL_DIRS if root]


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
    existing = {p.name.lower() for root in roots for p in _all_files(root)}
    missing = []
    for item in required:
        name = model_manifest.basename(item["filename"])
        if name.lower() not in existing:
            missing.append(model_manifest.public_entry(item))
    return missing


def scan_render_models() -> dict:
    roots = _render_roots()
    files = [p for root in roots for p in _files(root)]

    loras = [p for p in files if _contains(p, "lora")]
    upscalers = [p for p in files if _contains(p, "upscaler", "upscale_models")]
    audio_vaes = [p for p in files if _contains(p, "audio_vae", "vae")]
    preview_vaes = [p for p in files if _contains(p, "tae", "preview")]
    text_projections = [p for p in files if _contains(p, "projection", "text_projection")]
    text_encoders = [
        p for p in files
        if p not in text_projections and _contains(p, "gemma", "clip", "t5", "text_encoder")
    ]
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
    missing = _missing(model_manifest.required_render_files(), roots)

    return {
        "text_encoders": _names(text_encoders),
        "text_projections": _names(text_projections),
        "upscalers": _names(upscalers),
        "audio_vaes": _names(audio_vaes),
        "preview_vaes": _names(preview_vaes),
        "checkpoints": _names(checkpoints),
        "loras": _names(loras),
        "source": "local",
        "model_root": " ; ".join(roots),
        "required": required,
        "missing_required": missing,
        "ready": not missing,
    }


def find_render_model(name: str) -> Path | None:
    if not name:
        return None
    path = Path(name)
    if path.is_absolute() and path.exists():
        return path
    for root in _render_roots():
        for item in _files(root):
            if item.name.lower() == name.lower():
                return item
    return None


def find_required_render_file(key: str) -> Path | None:
    entry = next((item for item in model_manifest.required_render_files() if item["key"] == key), None)
    if entry is None:
        return None
    name = model_manifest.basename(entry["filename"]).lower()
    for root in _render_roots():
        for item in _all_files(root):
            if item.name.lower() == name:
                return item
    return None


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
