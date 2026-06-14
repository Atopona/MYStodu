"""Local LTX-2.3 renderer bridge.

The backend does not synthesize fake videos. A render job either invokes
the official Lightricks LTX two-stage pipeline with local model files, or fails
with a concrete missing-dependency / missing-model message.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import config, local_models, media, model_manifest


class LocalRenderError(RuntimeError):
    pass


@dataclass
class ResolvedRenderModels:
    checkpoint: Path
    text_encoder: Path
    text_projection: Path
    spatial_upscaler: Path
    audio_vae: Path
    video_vae: Optional[Path]
    distil_lora: Optional[Path]
    gemma_root: Path
    extra_loras: List[tuple[Path, float]] = field(default_factory=list)
    stage1_distil_strength: float = 0.0
    stage2_distil_strength: float = 1.0
    pipeline_kind: str = "hq"


@dataclass
class LocalRenderSpec:
    command: List[str]
    env: Dict[str, str]
    output_path: str
    summary: Dict[str, str]


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PCT_RE = re.compile(r"(\d{1,3})%\|")
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_REQUIRED_DEPENDENCIES = [
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
_CPU_TRUE = {"1", "true", "yes", "on"}
_GEMMA3_PREPROCESSOR_CONFIG = {
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


def cpu_render_allowed() -> bool:
    return os.environ.get("LTX_ALLOW_CPU", "").strip().lower() in _CPU_TRUE


def _required_by_key() -> Dict[str, dict]:
    return {item["key"]: item for item in model_manifest.required_render_files()}


def _deep_merge_config(left: dict, right: dict) -> dict:
    out = dict(left)
    for key, value in (right or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge_config(out[key], value)
        elif key not in out or out[key] in ({}, None):
            out[key] = value
    return out


def _safetensors_summary(path: Path) -> dict:
    from safetensors import safe_open

    with safe_open(str(path), framework="pt", device="cpu") as fh:
        keys = list(fh.keys())
        metadata = fh.metadata() or {}
        fp8_weight_count = 0
        fp8_missing_scale = []
        key_set = set(keys)
        for key in keys:
            if not key.endswith(".weight"):
                continue
            try:
                dtype = fh.get_slice(key).get_dtype()
            except Exception:  # noqa: BLE001
                continue
            if dtype != "F8_E4M3":
                continue
            fp8_weight_count += 1
            if f"{key}_scale" not in key_set:
                fp8_missing_scale.append(key)

    config_text = metadata.get("config", "")
    config_data = {}
    config_error = ""
    if config_text:
        try:
            parsed = json.loads(config_text)
            if isinstance(parsed, dict):
                config_data = parsed
            else:
                config_error = "metadata['config'] is not a JSON object"
        except Exception as exc:  # noqa: BLE001
            config_error = f"metadata['config'] is not valid JSON: {exc}"

    def any_prefix(*prefixes: str) -> bool:
        return any(any(key.startswith(prefix) for key in keys) for prefix in prefixes)

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "tensor_count": len(keys),
        "metadata_keys": sorted(metadata.keys()),
        "config": config_data,
        "config_keys": sorted(config_data.keys()),
        "config_error": config_error,
        "groups": {
            "transformer": any_prefix("model.diffusion_model.", "transformer_blocks."),
            "video_vae": any_prefix("vae.encoder.", "vae.decoder.", "encoder.", "decoder."),
            "audio_vae": any_prefix("audio_vae.encoder.", "audio_vae.decoder."),
            "vocoder": any_prefix("vocoder."),
            "text_projection": any_prefix(
                "text_embedding_projection.",
                "model.diffusion_model.video_embeddings_connector.",
                "model.diffusion_model.audio_embeddings_connector.",
            ),
            "spatial_upscaler": any_prefix("up_blocks.", "down_blocks.", "res_blocks.", "conv_in.", "layers."),
            "gemma_language": any_prefix(
                "language_model.model.",
                "language_model.layers.",
                "model.layers.",
                "model.embed_tokens.",
                "model.model.language_model.",
            ),
        },
        "fp8_weight_count": fp8_weight_count,
        "fp8_missing_scale_count": len(fp8_missing_scale),
        "fp8_missing_scale_examples": fp8_missing_scale[:8],
    }


def inspect_component_bundle(resolved: ResolvedRenderModels) -> dict:
    paths = [
        ("checkpoint", resolved.checkpoint),
        ("text_encoder", resolved.text_encoder),
        ("text_projection", resolved.text_projection),
        ("audio_vae", resolved.audio_vae),
        ("spatial_upscaler", resolved.spatial_upscaler),
    ]
    if resolved.video_vae is not None:
        paths.append(("video_vae", resolved.video_vae))

    items = []
    merged_config: dict = {}
    for role, path in paths:
        try:
            summary = _safetensors_summary(path)
            merged_config = _deep_merge_config(merged_config, summary.get("config") or {})
            items.append({"role": role, "ok": True, **summary})
        except Exception as exc:  # noqa: BLE001
            items.append({"role": role, "ok": False, "path": str(path), "error": str(exc), "groups": {}})

    def group_present(name: str) -> bool:
        return any((item.get("groups") or {}).get(name) for item in items if item.get("ok"))

    errors: List[str] = []
    for item in items:
        if not item.get("ok"):
            errors.append(f"{item.get('role')} 文件无法打开：{item.get('error')}")
        elif item.get("tensor_count", 0) <= 0:
            errors.append(f"{item.get('role')} 文件没有 tensor：{item.get('path')}")
        elif item.get("config_error"):
            errors.append(f"{item.get('role')} metadata config 无效：{item.get('config_error')}")

    required_config = {
        "transformer": "主 diffusion transformer",
        "vae": "Video VAE",
        "audio_vae": "Audio VAE",
        "vocoder": "vocoder",
    }
    for key, label in required_config.items():
        if key not in merged_config:
            errors.append(f"当前模型组合缺少 {label} 配置 metadata['config'].{key}")

    required_groups = {
        "transformer": "主 diffusion transformer 权重",
        "gemma_language": "Gemma language text encoder 权重",
        "video_vae": "Video VAE encoder/decoder 权重",
        "audio_vae": "Audio VAE encoder/decoder 权重",
        "vocoder": "vocoder 权重",
        "text_projection": "LTX text projection 权重",
    }
    for key, label in required_groups.items():
        if not group_present(key):
            errors.append(f"当前模型组合缺少 {label}")

    upscaler = next((item for item in items if item.get("role") == "spatial_upscaler"), None)
    if upscaler and upscaler.get("ok") and "config" not in (upscaler.get("metadata_keys") or []):
        errors.append("spatial upscaler 缺少 metadata['config']，官方 upsampler 无法可靠构建")

    text_encoder = next((item for item in items if item.get("role") == "text_encoder"), None)
    if text_encoder and text_encoder.get("ok") and text_encoder.get("fp8_missing_scale_count", 0):
        examples = ", ".join(text_encoder.get("fp8_missing_scale_examples") or [])
        errors.append(
            "Gemma text encoder FP8 权重缺少对应 .weight_scale，无法还原真实权重"
            + (f"：{examples}" if examples else "")
        )

    return {
        "ok": not errors,
        "errors": errors,
        "config_keys": sorted(merged_config.keys()),
        "items": items,
    }


def _validate_component_bundle(resolved: ResolvedRenderModels) -> None:
    report = inspect_component_bundle(resolved)
    if not report["ok"]:
        detail = "\n".join(f"- {err}" for err in report["errors"])
        raise LocalRenderError(
            "本地 LTX 模型组合不能被官方管线完整加载，已停止渲染以避免假成功或空转：\n"
            + detail
            + "\n请运行 install_linux.sh 获取默认完整组合，或在 PIPELINE 中选择匹配的 split 组件。"
        )


def dependency_report() -> List[dict]:
    report = []
    for module, package in _REQUIRED_DEPENDENCIES:
        try:
            importlib.import_module(module)
            report.append({"module": module, "package": package, "ok": True, "error": ""})
        except Exception as exc:  # noqa: BLE001
            report.append({"module": module, "package": package, "ok": False, "error": str(exc)})
    return report


def device_report() -> dict:
    allow_cpu = cpu_render_allowed()
    report = {
        "ready": False,
        "allow_cpu": allow_cpu,
        "torch_available": False,
        "torch_version": "",
        "torch_cuda_version": "",
        "cuda_available": False,
        "cuda_device_count": 0,
        "current_device": None,
        "devices": [],
        "nvidia_smi": {"available": False, "summary": [], "error": ""},
        "detail": "",
    }
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        report["detail"] = f"无法导入 PyTorch，因此不能检查 CUDA：{exc}"
        return report

    report["torch_available"] = True
    report["torch_version"] = getattr(torch, "__version__", "")
    report["torch_cuda_version"] = getattr(getattr(torch, "version", None), "cuda", "") or ""
    try:
        cuda_available = bool(torch.cuda.is_available())
        report["cuda_available"] = cuda_available
        report["cuda_device_count"] = int(torch.cuda.device_count()) if cuda_available else 0
        if cuda_available:
            current = int(torch.cuda.current_device())
            report["current_device"] = current
            for idx in range(report["cuda_device_count"]):
                props = torch.cuda.get_device_properties(idx)
                item = {
                    "index": idx,
                    "name": props.name,
                    "capability": f"{props.major}.{props.minor}",
                    "total_memory": int(props.total_memory),
                }
                if idx == current:
                    try:
                        free, total = torch.cuda.mem_get_info(idx)
                        item["free_memory"] = int(free)
                        item["runtime_total_memory"] = int(total)
                    except Exception:  # noqa: BLE001
                        pass
                report["devices"].append(item)
    except Exception as exc:  # noqa: BLE001
        report["detail"] = f"CUDA 检查失败：{exc}"

    smi = shutil.which("nvidia-smi")
    if smi:
        report["nvidia_smi"]["available"] = True
        try:
            proc = subprocess.run(
                [
                    smi,
                    "--query-gpu=name,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0:
                report["nvidia_smi"]["summary"] = [
                    line.strip() for line in proc.stdout.splitlines() if line.strip()
                ]
            else:
                report["nvidia_smi"]["error"] = (proc.stderr or proc.stdout or "").strip()
        except Exception as exc:  # noqa: BLE001
            report["nvidia_smi"]["error"] = str(exc)

    if report["cuda_available"]:
        report["ready"] = True
        names = ", ".join(d["name"] for d in report["devices"]) or "CUDA device"
        report["detail"] = f"CUDA ready: {names}"
    elif allow_cpu:
        report["ready"] = True
        report["detail"] = "LTX_ALLOW_CPU=1 已启用：允许 CPU 调试渲染，但会非常慢且可能失败"
    else:
        cuda_build = report["torch_cuda_version"] or "CPU-only PyTorch"
        report["detail"] = (
            "未检测到可用 CUDA GPU；官方 LTX-2.3 本地渲染需要 NVIDIA CUDA。"
            f"当前 PyTorch CUDA 构建：{cuda_build}。如仅需调试，可设置 LTX_ALLOW_CPU=1。"
        )
    return report


def _device_errors() -> List[str]:
    report = device_report()
    if report.get("ready"):
        return []
    return [str(report.get("detail") or "本地 LTX 渲染设备未就绪")]


def _dependency_errors() -> List[str]:
    missing = [item["package"] for item in dependency_report() if not item["ok"]]
    if missing:
        return [
            "缺少本地 LTX 推理依赖："
            + ", ".join(dict.fromkeys(missing))
            + "。请运行 install_linux.sh。"
        ]
    return []


def status() -> dict:
    dep_errors = _dependency_errors()
    device = device_report()
    device_ready = bool(device.get("ready"))
    device_errors = [] if dep_errors or device_ready else [str(device.get("detail") or "本地 LTX 渲染设备未就绪")]
    scan = local_models.scan_render_models()
    missing = scan.get("missing_required", [])
    dependencies_ready = not dep_errors
    default_models_ready = not missing
    ready = dependencies_ready and device_ready and default_models_ready
    if ready:
        detail = "local LTX-2.3 pipeline ready"
    elif dep_errors:
        detail = dep_errors[0]
    elif device_errors:
        detail = device_errors[0]
    else:
        names = ", ".join(item["name"] for item in missing[:4])
        more = f" 等 {len(missing)} 个文件" if len(missing) > 4 else ""
        detail = f"缺少本地 LTX 模型：{names}{more}"
    return {
        "state": "running" if ready else "down",
        "detail": detail,
        "url": "",
        "ready": ready,
        "dependencies_ready": dependencies_ready,
        "device_ready": device_ready,
        "device": device,
        "default_models_ready": default_models_ready,
        "missing_required": missing,
    }


def _format_missing(missing: List[dict]) -> str:
    lines = ["缺少本地 LTX 必需模型文件，不能渲染真实视频："]
    for item in missing:
        lines.append(f"- {item['name']} ({item['url']})")
    lines.append("请运行 install_linux.sh，或把这些文件放入 models/ltx 对应目录。")
    return "\n".join(lines)


def _default_missing_for_selection(mode: str, pipeline: dict) -> List[dict]:
    mode_key = "i2v_checkpoint" if mode == "i2v" else "t2v_checkpoint"
    selected_checkpoint = _mode_checkpoint_selection(mode, pipeline.get("checkpoint", ""))
    distil1 = pipeline.get("distil1") or {}
    distil2 = pipeline.get("distil2") or {}
    selected_distil = _selected_distil_model(distil1, distil2)
    selected_checkpoint_full_distilled = bool(
        selected_checkpoint and _is_full_distilled_checkpoint(selected_checkpoint)
    )
    selectable = {
        mode_key: selected_checkpoint,
        "text_encoder": pipeline.get("text_encoder", ""),
        "text_projection": pipeline.get("text_projection", ""),
        "spatial_upscaler": pipeline.get("upscaler", ""),
        "audio_vae": pipeline.get("audio_vae", ""),
        "distil_lora": selected_distil,
    }
    missing: List[dict] = []
    for key, selected in selectable.items():
        if key == "distil_lora" and selected_checkpoint_full_distilled:
            continue
        if selected:
            continue
        item = _required_by_key()[key]
        if local_models.find_required_render_file(key) is None:
            missing.append(model_manifest.public_entry(item))

    # Gemma auxiliary files are tied to the selected/default text encoder root.
    # If a custom text encoder is selected, _resolve_gemma_root will validate
    # the actual directory. For default selection, list all missing defaults.
    if not selectable["text_encoder"]:
        for key in [
            "gemma_tokenizer",
            "gemma_tokenizer_json",
            "gemma_tokenizer_config",
            "gemma_special_tokens",
            "gemma_chat_template",
            "gemma_config",
            "gemma_generation_config",
        ]:
            item = _required_by_key()[key]
            if local_models.find_required_render_file(key) is None:
                missing.append(model_manifest.public_entry(item))
    return missing


def _resolve_selected_or_required(selected: str, required_key: str) -> Path:
    if selected:
        found = local_models.find_render_model(selected)
        if found is None:
            raise LocalRenderError(f"已选择的模型文件不存在：{selected}")
        return found
    found = local_models.find_required_render_file(required_key)
    if found is None:
        item = model_manifest.public_entry(_required_by_key()[required_key])
        raise LocalRenderError(_format_missing([item]))
    return found


def _mode_checkpoint_selection(mode: str, selected: str) -> str:
    """Avoid stale UI state using the opposite mode's default checkpoint."""
    if not selected:
        return ""
    selected_name = Path(selected).name.lower()
    other_key = "t2v_checkpoint" if mode == "i2v" else "i2v_checkpoint"
    other_name = model_manifest.basename(_required_by_key()[other_key]["filename"]).lower()
    if selected_name == other_name:
        return ""
    return selected


def _is_full_distilled_checkpoint(path_or_name: str | Path) -> bool:
    return "distill" in Path(path_or_name).name.lower()


def _selected_distil_model(distil1: dict, distil2: dict) -> str:
    for stage in (distil2, distil1):
        if _enabled(stage) and stage.get("model"):
            return str(stage.get("model") or "")
    return ""


def _gemma_missing(root: Path) -> List[str]:
    required = [
        "tokenizer.model",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "config.json",
        "generation_config.json",
        "preprocessor_config.json",
    ]
    present = {p.name for p in root.rglob("*") if p.is_file() and p.stat().st_size > 0}
    missing = [name for name in required if name not in present]
    if "chat_template.json" not in present and "chat_template.jinja" not in present:
        missing.append("chat_template.json or chat_template.jinja")
    return missing


def _ensure_gemma_preprocessor_config(root: Path) -> None:
    target = root / "preprocessor_config.json"
    if target.exists() and target.stat().st_size > 0:
        return
    has_tokenizer = any(
        p.name in {"tokenizer.model", "tokenizer.json", "tokenizer_config.json"}
        for p in root.rglob("*")
        if p.is_file()
    )
    if not has_tokenizer:
        return
    try:
        target.write_text(
            json.dumps(_GEMMA3_PREPROCESSOR_CONFIG, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def _ensure_gemma_model_alias(root: Path, text_encoder: Path) -> None:
    if any(p.is_file() and p.stat().st_size > 0 for p in root.rglob("model*.safetensors")):
        return
    alias_dir = root / "ltx_gemma_model"
    alias_dir.mkdir(parents=True, exist_ok=True)
    alias = alias_dir / "model.safetensors"
    if alias.exists():
        try:
            if alias.stat().st_size > 0:
                return
            alias.unlink()
        except OSError:
            pass
    try:
        os.symlink(text_encoder, alias)
        return
    except OSError:
        pass
    try:
        os.link(text_encoder, alias)
        return
    except OSError as exc:
        raise LocalRenderError(
            "Gemma 文本编码器文件已找到，但官方 LTX 需要文件名匹配 model*.safetensors。"
            f"请创建 {alias} 指向 {text_encoder}。"
        ) from exc


def _resolve_gemma_root(text_encoder: Path) -> Path:
    candidates = []
    for parent in [text_encoder.parent, *text_encoder.parents]:
        if parent in candidates:
            continue
        candidates.append(parent)
        if parent == Path(config.ROOT):
            break

    best: Optional[Path] = None
    best_missing: List[str] = []
    for root in candidates:
        _ensure_gemma_preprocessor_config(root)
        missing = _gemma_missing(root)
        if not missing:
            _ensure_gemma_model_alias(root, text_encoder)
            return root
        if best is None or len(missing) < len(best_missing):
            best = root
            best_missing = missing

    root_hint = best or text_encoder.parent
    raise LocalRenderError(
        "Gemma text encoder 目录不完整，官方 LTX 本地管线至少需要 Gemma tokenizer/image processor 配置文件"
        "与 model*.safetensors。"
        f"当前检查目录：{root_hint}；缺少：{', '.join(best_missing or _gemma_missing(text_encoder.parent))}。"
    )


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _enabled(stage: dict) -> bool:
    return bool(stage.get("enabled", True))


def validate_and_resolve(mode: str, pipeline: dict) -> ResolvedRenderModels:
    dep_errors = _dependency_errors()
    if dep_errors:
        raise LocalRenderError(dep_errors[0])
    device_errors = _device_errors()
    if device_errors:
        raise LocalRenderError(device_errors[0])

    mode_key = "i2v_checkpoint" if mode == "i2v" else "t2v_checkpoint"
    missing = _default_missing_for_selection(mode, pipeline)
    if missing:
        raise LocalRenderError(_format_missing(missing))

    checkpoint = _resolve_selected_or_required(
        _mode_checkpoint_selection(mode, pipeline.get("checkpoint", "")),
        mode_key,
    )
    pipeline_kind = "distilled" if _is_full_distilled_checkpoint(checkpoint) else "hq"
    text_encoder = _resolve_selected_or_required(pipeline.get("text_encoder", ""), "text_encoder")
    text_projection = _resolve_selected_or_required(pipeline.get("text_projection", ""), "text_projection")
    spatial_upscaler = _resolve_selected_or_required(pipeline.get("upscaler", ""), "spatial_upscaler")
    audio_vae = _resolve_selected_or_required(pipeline.get("audio_vae", ""), "audio_vae")
    video_vae = None
    if pipeline.get("video_vae"):
        video_vae = local_models.find_render_model(str(pipeline.get("video_vae") or ""))
        if video_vae is None:
            raise LocalRenderError(f"已选择的 Video VAE 文件不存在：{pipeline.get('video_vae')}")

    distil1 = pipeline.get("distil1") or {}
    distil2 = pipeline.get("distil2") or {}
    selected_distil = _selected_distil_model(distil1, distil2)
    if pipeline_kind == "distilled" and selected_distil:
        raise LocalRenderError(
            "Distill LoRA 与完整 distilled checkpoint 互斥（二选一）：当前 checkpoint 已是 distilled 完整模型，"
            "请关闭 First/Second Stage Distil，或换用非 distilled checkpoint。"
        )
    distil_lora = None if pipeline_kind == "distilled" else _resolve_selected_or_required(selected_distil, "distil_lora")
    stage1_strength = _float(distil1.get("strength"), 0.25) if _enabled(distil1) else 0.0
    stage2_strength = _float(distil2.get("strength"), 0.5) if _enabled(distil2) else 0.0

    extra_loras: List[tuple[Path, float]] = []
    for item in pipeline.get("loras") or []:
        if not item.get("enabled", True):
            continue
        name = item.get("name") or ""
        path = local_models.find_render_model(name)
        if path is None:
            raise LocalRenderError(f"已选择的 LoRA 文件不存在：{name}")
        if distil_lora is not None and path.resolve() == distil_lora.resolve():
            continue
        extra_loras.append((path, _float(item.get("strength"), 1.0)))

    gemma_root = _resolve_gemma_root(text_encoder)
    resolved = ResolvedRenderModels(
        checkpoint=checkpoint,
        text_encoder=text_encoder,
        text_projection=text_projection,
        spatial_upscaler=spatial_upscaler,
        audio_vae=audio_vae,
        video_vae=video_vae,
        distil_lora=distil_lora,
        gemma_root=gemma_root,
        extra_loras=extra_loras,
        stage1_distil_strength=stage1_strength,
        stage2_distil_strength=stage2_strength,
        pipeline_kind=pipeline_kind,
    )
    _validate_component_bundle(resolved)
    return resolved


def _check_dimensions(width: int, height: int) -> None:
    if width % 64 != 0 or height % 64 != 0:
        raise LocalRenderError(
            f"当前分辨率 {width}x{height} 不能用于官方 LTX 两阶段本地管线；宽高必须都是 64 的倍数。"
        )


def build_job_spec(
    *,
    job_id: str,
    mode: str,
    final_prompt: str,
    negative_prompt: str,
    image_path: Optional[str],
    params: dict,
    pipeline: dict,
    seed: int,
) -> LocalRenderSpec:
    width = int(params["width"])
    height = int(params["height"])
    fps = int(params["fps"])
    duration = float(params.get("duration") or 0)
    frames = int(params.get("frames") or 0)
    if duration > 0:
        frames = config.snap_frames(duration, fps)
    elif frames < 1:
        raise LocalRenderError("渲染帧数无效：duration/fps 或 frames 必须能得到正帧数")
    else:
        frames = max(1, 8 * max(1, round((frames - 1) / 8)) + 1)
    _check_dimensions(width, height)

    if mode == "i2v" and (not image_path or not os.path.exists(image_path)):
        raise LocalRenderError("I2V 本地渲染需要有效参考图")

    resolved = validate_and_resolve(mode, pipeline)
    output_path = os.path.join(config.OUTPUT_DIR, f"{job_id}.mp4")
    module = os.environ.get("LTX_PIPELINE_MODULE", "backend.ltx_runner").strip()
    steps = os.environ.get("LTX_NUM_INFERENCE_STEPS", "15").strip() or "15"
    offload = os.environ.get("LTX_OFFLOAD", "none").strip() or "none"
    max_batch = os.environ.get("LTX_MAX_BATCH_SIZE", "1").strip() or "1"

    cmd = [
        sys.executable,
        "-m",
        module,
        "--pipeline-kind",
        resolved.pipeline_kind,
        "--checkpoint-path",
        str(resolved.checkpoint),
        "--text-projection-path",
        str(resolved.text_projection),
        "--audio-vae-path",
        str(resolved.audio_vae),
        "--spatial-upsampler-path",
        str(resolved.spatial_upscaler),
        "--gemma-root",
        str(resolved.gemma_root),
        "--prompt",
        final_prompt,
        "--negative-prompt",
        negative_prompt,
        "--output-path",
        output_path,
        "--seed",
        str(seed),
        "--height",
        str(height),
        "--width",
        str(width),
        "--num-frames",
        str(frames),
        "--frame-rate",
        str(float(fps)),
        "--num-inference-steps",
        steps,
        "--offload",
        offload,
        "--max-batch-size",
        max_batch,
    ]

    if resolved.video_vae is not None:
        cmd.extend(["--video-vae-path", str(resolved.video_vae)])

    if resolved.pipeline_kind == "hq":
        if resolved.distil_lora is None:
            raise LocalRenderError("官方 HQ two-stage 管线需要 distill LoRA；请选择 LoRA 或使用完整 distilled checkpoint。")
        cmd.extend(
            [
                "--distilled-lora",
                str(resolved.distil_lora),
                "1.0",
                "--distilled-lora-strength-stage-1",
                f"{resolved.stage1_distil_strength:.4f}",
                "--distilled-lora-strength-stage-2",
                f"{resolved.stage2_distil_strength:.4f}",
            ]
        )

    quantization = os.environ.get("LTX_QUANTIZATION", "").strip()
    if quantization:
        cmd.extend(["--quantization", quantization])
    if image_path:
        cmd.extend(["--image", image_path, "0", "1.0", os.environ.get("LTX_IMAGE_CRF", "33")])
    for path, strength in resolved.extra_loras:
        cmd.extend(["--lora", str(path), f"{strength:.4f}"])

    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    summary = {
        "pipeline": module,
        "pipeline_kind": resolved.pipeline_kind,
        "checkpoint": resolved.checkpoint.name,
        "text_encoder": resolved.text_encoder.name,
        "text_projection": resolved.text_projection.name,
        "upscaler": resolved.spatial_upscaler.name,
        "audio_vae": resolved.audio_vae.name,
        "video_vae": resolved.video_vae.name if resolved.video_vae is not None else "",
        "distil_lora": resolved.distil_lora.name if resolved.distil_lora is not None else "",
        "gemma_root": str(resolved.gemma_root),
        "quantization": quantization or "auto",
    }
    return LocalRenderSpec(command=cmd, env=env, output_path=output_path, summary=summary)


def _clean_line(raw: str) -> str:
    return _ANSI_RE.sub("", raw).strip()


def _handle_output_line(
    line: str,
    *,
    job_id: str,
    state: dict,
    emit: Callable[[dict], None],
    log: Callable[[str, str], None],
) -> None:
    text = _clean_line(line)
    if not text:
        return

    low = text.lower()
    if "building text encoder" in low:
        state["phase"] = "pass1"
        log("LTX text encoder loading Gemma ...", "info")
    elif "text encoder done" in low:
        log("LTX text encoder complete; building embedding processor", "info")
    elif "running denoising loop" in low:
        state["loop"] = int(state.get("loop", 0)) + 1
        state["phase"] = "pass1" if state["loop"] == 1 else "pass2"
        state["pct"] = 1
        log("PASS 1 — base LTX denoise started" if state["phase"] == "pass1" else "PASS 2 — spatial upscale refine started", "info")
    elif "building video decoder" in low or "encode_video" in low:
        state["phase"] = "saving"
        state["pct"] = 100

    pct_match = _PCT_RE.search(text)
    frac_match = _FRACTION_RE.search(text)
    if pct_match:
        state["pct"] = max(0, min(100, int(pct_match.group(1))))
    step = total = None
    if frac_match:
        step = int(frac_match.group(1))
        total = int(frac_match.group(2))

    if pct_match or frac_match:
        emit(
            {
                "type": "job_update",
                "job_id": job_id,
                "status": "running",
                "phase": state.get("phase", "pass1"),
                "step": step,
                "total": total,
                "pct": int(state.get("pct", 1)),
            }
        )
    elif "INFO:" in text or text.startswith("INFO"):
        log(text, "info")


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def run_job(
    *,
    job_id: str,
    spec: LocalRenderSpec,
    cancel: asyncio.Event,
    emit: Callable[[dict], None],
    log: Callable[[str, str], None],
) -> str:
    display_cmd = list(spec.command)
    if "--prompt" in display_cmd:
        idx = display_cmd.index("--prompt")
        if idx + 1 < len(display_cmd):
            display_cmd[idx + 1] = "<prompt>"
    log(
        "local LTX render starting — "
        f"{spec.summary['checkpoint']} · {spec.summary['text_encoder']} · {spec.summary['upscaler']}",
        "info",
    )
    log("local LTX command prepared: " + " ".join(display_cmd[:8]) + " ...", "info")
    emit({"type": "job_update", "job_id": job_id, "status": "running", "phase": "pass1", "pct": 1})

    proc = await asyncio.create_subprocess_exec(
        *spec.command,
        cwd=config.ROOT,
        env=spec.env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    buffer = ""
    tail: List[str] = []
    state = {"phase": "pass1", "pct": 1, "loop": 0}
    last_emit = time.time()

    assert proc.stdout is not None
    while True:
        if cancel.is_set():
            await _terminate(proc)
            raise asyncio.CancelledError()
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
        except asyncio.TimeoutError:
            if time.time() - last_emit > 5:
                emit(
                    {
                        "type": "job_update",
                        "job_id": job_id,
                        "status": "running",
                        "phase": state.get("phase", "pass1"),
                        "pct": int(state.get("pct", 1)),
                    }
                )
                last_emit = time.time()
            if proc.returncode is not None:
                break
            continue
        if not chunk:
            if proc.returncode is not None:
                break
            continue

        buffer += chunk.decode("utf-8", errors="replace")
        parts = re.split(r"[\r\n]+", buffer)
        buffer = parts.pop() if parts else ""
        for part in parts:
            cleaned = _clean_line(part)
            if cleaned:
                tail.append(cleaned)
                tail = tail[-30:]
            _handle_output_line(part, job_id=job_id, state=state, emit=emit, log=log)

    if buffer.strip():
        cleaned = _clean_line(buffer)
        tail.append(cleaned)
        _handle_output_line(buffer, job_id=job_id, state=state, emit=emit, log=log)

    rc = await proc.wait()
    if rc != 0:
        detail = "\n".join(tail[-12:]) or f"LTX process exited with code {rc}"
        raise LocalRenderError(detail)
    ok, video_error = media.validate_video_file(spec.output_path)
    if not ok:
        raise LocalRenderError(f"LTX 进程结束但没有生成可解码的有效 MP4 文件：{video_error}")
    log(f"local LTX render wrote {os.path.basename(spec.output_path)}", "info")
    return spec.output_path
