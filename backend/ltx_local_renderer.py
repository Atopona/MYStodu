"""Local LTX-2.3 renderer bridge.

The backend does not synthesize placeholder videos. A render job either invokes
the official Lightricks LTX two-stage pipeline with local model files, or fails
with a concrete missing-dependency / missing-model message.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from . import config, local_models, model_manifest


class LocalRenderError(RuntimeError):
    pass


@dataclass
class ResolvedRenderModels:
    checkpoint: Path
    text_encoder: Path
    text_projection: Path
    spatial_upscaler: Path
    audio_vae: Path
    distil_lora: Path
    gemma_root: Path
    extra_loras: List[tuple[Path, float]] = field(default_factory=list)
    stage1_distil_strength: float = 0.0
    stage2_distil_strength: float = 1.0


@dataclass
class LocalRenderSpec:
    command: List[str]
    env: Dict[str, str]
    output_path: str
    summary: Dict[str, str]


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PCT_RE = re.compile(r"(\d{1,3})%\|")
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


def _required_by_key() -> Dict[str, dict]:
    return {item["key"]: item for item in model_manifest.required_render_files()}


def _dependency_errors() -> List[str]:
    needed = {
        "ltx_pipelines": "ltx-pipelines",
        "ltx_core": "ltx-core",
        "torch": "torch",
        "av": "av",
        "OpenImageIO": "openimageio",
    }
    missing = []
    for module, package in needed.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    if missing:
        return [
            "缺少本地 LTX 推理依赖："
            + ", ".join(missing)
            + "。请运行 install_linux.sh，或安装 tools/LTX-2/packages/ltx-core 与 ltx-pipelines。"
        ]
    return []


def status() -> dict:
    dep_errors = _dependency_errors()
    scan = local_models.scan_render_models()
    missing = scan.get("missing_required", [])
    ready = not dep_errors and not missing
    if ready:
        detail = "local LTX-2.3 pipeline ready"
    elif dep_errors:
        detail = dep_errors[0]
    else:
        names = ", ".join(item["name"] for item in missing[:4])
        more = f" 等 {len(missing)} 个文件" if len(missing) > 4 else ""
        detail = f"缺少本地 LTX 模型：{names}{more}"
    return {
        "state": "running" if ready else "down",
        "detail": detail,
        "url": "",
        "ready": ready,
        "missing_required": missing,
    }


def _missing_entries(keys: Iterable[str]) -> List[dict]:
    missing = []
    for key in keys:
        item = _required_by_key()[key]
        if local_models.find_required_render_file(key) is None:
            missing.append(model_manifest.public_entry(item))
    return missing


def _format_missing(missing: List[dict]) -> str:
    lines = ["缺少本地 LTX 必需模型文件，不能渲染真实视频："]
    for item in missing:
        lines.append(f"- {item['name']} ({item['url']})")
    lines.append("请运行 install_linux.sh，或把这些文件放入 models/ltx 对应目录。")
    return "\n".join(lines)


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


def _gemma_missing(root: Path) -> List[str]:
    required = ["tokenizer.model", "tokenizer_config.json", "preprocessor_config.json"]
    present = {p.name for p in root.rglob("*") if p.is_file()}
    return [name for name in required if name not in present]


def _ensure_gemma_model_alias(root: Path, text_encoder: Path) -> None:
    if any(root.rglob("model*.safetensors")):
        return
    alias = text_encoder.parent / "model.safetensors"
    if alias.exists():
        return
    try:
        os.symlink(text_encoder.name, alias)
        return
    except OSError:
        pass
    try:
        os.link(text_encoder, alias)
        return
    except OSError as exc:
        raise LocalRenderError(
            "Gemma 文本编码器文件已找到，但官方 LTX 需要文件名匹配 model*.safetensors。"
            f"请在 {text_encoder.parent} 下创建 model.safetensors 指向 {text_encoder.name}。"
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
        missing = _gemma_missing(root)
        if not missing:
            _ensure_gemma_model_alias(root, text_encoder)
            return root
        if best is None or len(missing) < len(best_missing):
            best = root
            best_missing = missing

    root_hint = best or text_encoder.parent
    raise LocalRenderError(
        "Gemma text encoder 目录不完整，官方 LTX 本地管线至少需要 "
        "tokenizer.model、tokenizer_config.json、preprocessor_config.json 与 model*.safetensors。"
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

    mode_key = "i2v_checkpoint" if mode == "i2v" else "t2v_checkpoint"
    required_keys = [
        mode_key,
        "text_encoder",
        "text_projection",
        "spatial_upscaler",
        "audio_vae",
        "distil_lora",
        "gemma_tokenizer",
        "gemma_tokenizer_config",
        "gemma_preprocessor",
    ]
    missing = _missing_entries(required_keys)
    if missing:
        raise LocalRenderError(_format_missing(missing))

    checkpoint = _resolve_selected_or_required(pipeline.get("checkpoint", ""), mode_key)
    text_encoder = _resolve_selected_or_required(pipeline.get("text_encoder", ""), "text_encoder")
    text_projection = _resolve_selected_or_required(pipeline.get("text_projection", ""), "text_projection")
    spatial_upscaler = _resolve_selected_or_required(pipeline.get("upscaler", ""), "spatial_upscaler")
    audio_vae = _resolve_selected_or_required(pipeline.get("audio_vae", ""), "audio_vae")

    distil1 = pipeline.get("distil1") or {}
    distil2 = pipeline.get("distil2") or {}
    selected_distil = distil2.get("model") or distil1.get("model") or ""
    distil_lora = _resolve_selected_or_required(selected_distil, "distil_lora")
    stage1_strength = _float(distil1.get("strength"), 1.0) if _enabled(distil1) else 0.0
    stage2_strength = _float(distil2.get("strength"), 1.0) if _enabled(distil2) else 0.0

    extra_loras: List[tuple[Path, float]] = []
    for item in pipeline.get("loras") or []:
        if not item.get("enabled", True):
            continue
        name = item.get("name") or ""
        path = local_models.find_render_model(name)
        if path is None:
            raise LocalRenderError(f"已选择的 LoRA 文件不存在：{name}")
        if path.resolve() == distil_lora.resolve():
            continue
        extra_loras.append((path, _float(item.get("strength"), 1.0)))

    gemma_root = _resolve_gemma_root(text_encoder)
    return ResolvedRenderModels(
        checkpoint=checkpoint,
        text_encoder=text_encoder,
        text_projection=text_projection,
        spatial_upscaler=spatial_upscaler,
        audio_vae=audio_vae,
        distil_lora=distil_lora,
        gemma_root=gemma_root,
        extra_loras=extra_loras,
        stage1_distil_strength=stage1_strength,
        stage2_distil_strength=stage2_strength,
    )


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
        "--checkpoint-path",
        str(resolved.checkpoint),
        "--text-projection-path",
        str(resolved.text_projection),
        "--audio-vae-path",
        str(resolved.audio_vae),
        "--distilled-lora",
        str(resolved.distil_lora),
        "1.0",
        "--distilled-lora-strength-stage-1",
        f"{resolved.stage1_distil_strength:.4f}",
        "--distilled-lora-strength-stage-2",
        f"{resolved.stage2_distil_strength:.4f}",
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
        str(int(params["frames"])),
        "--frame-rate",
        str(float(params["fps"])),
        "--num-inference-steps",
        steps,
        "--offload",
        offload,
        "--max-batch-size",
        max_batch,
    ]

    quantization = os.environ.get("LTX_QUANTIZATION", "").strip()
    if quantization:
        cmd.extend(["--quantization", quantization])
    if image_path:
        cmd.extend(["--image", image_path, "0", "1.0", os.environ.get("LTX_IMAGE_CRF", "33")])
    for path, strength in resolved.extra_loras:
        cmd.extend(["--lora", str(path), f"{strength:.4f}"])

    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    summary = {
        "pipeline": module,
        "checkpoint": resolved.checkpoint.name,
        "text_encoder": resolved.text_encoder.name,
        "text_projection": resolved.text_projection.name,
        "upscaler": resolved.spatial_upscaler.name,
        "audio_vae": resolved.audio_vae.name,
        "distil_lora": resolved.distil_lora.name,
        "gemma_root": str(resolved.gemma_root),
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
    if not os.path.exists(spec.output_path) or os.path.getsize(spec.output_path) == 0:
        raise LocalRenderError("LTX 进程结束但没有生成有效 MP4 文件")
    log(f"local LTX render wrote {os.path.basename(spec.output_path)}", "info")
    return spec.output_path
