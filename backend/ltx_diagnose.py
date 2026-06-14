"""Local LTX installation diagnostics.

Run after install:
    python -m backend.ltx_diagnose

This does not render a video. It verifies imports, model presence, the runner
entrypoint, and, when possible, builds the exact local render command.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config, local_models, ltx_local_renderer, model_manifest


def _fmt_bytes(value: int) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def _required_file_status(entries: list[dict], finder) -> list[dict]:
    out = []
    for item in entries:
        path = finder(item["key"])
        public = model_manifest.public_entry(item)
        out.append(
            {
                **public,
                "present": path is not None,
                "path": str(path) if path else "",
                "bytes": path.stat().st_size if path and path.exists() else 0,
            }
        )
    return out


def _llm_file_status() -> list[dict]:
    return _required_file_status(model_manifest.required_llm_files(), local_models.find_required_llm_file)


def _runner_help() -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "backend.ltx_runner", "--help"],
            cwd=config.ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "returncode": None, "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-1000:],
    }


def _dry_run_command(deps_ok: bool, render_ready: bool, device_ready: bool) -> dict:
    if not deps_ok:
        return {"ok": False, "skipped": True, "reason": "LTX runtime imports are not ready"}
    if not device_ready:
        return {"ok": False, "skipped": True, "reason": "CUDA/GPU device is not ready for local LTX rendering"}
    if not render_ready:
        return {"ok": False, "skipped": True, "reason": "required render model files are missing"}
    try:
        spec = ltx_local_renderer.build_job_spec(
            job_id="diagnose",
            mode="t2v",
            final_prompt="A concise diagnostic prompt for local LTX command construction.",
            negative_prompt="",
            image_path=None,
            params={"duration": 2, "fps": 8, "frames": 17, "width": 896, "height": 512},
            pipeline={},
            seed=123456,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "skipped": False, "error": str(exc)}

    cmd = list(spec.command)
    if "--prompt" in cmd:
        idx = cmd.index("--prompt")
        if idx + 1 < len(cmd):
            cmd[idx + 1] = "<prompt>"
    if "--negative-prompt" in cmd:
        idx = cmd.index("--negative-prompt")
        if idx + 1 < len(cmd):
            cmd[idx + 1] = "<negative-prompt>"
    return {"ok": True, "skipped": False, "command": cmd, "summary": spec.summary}


def _safetensors_integrity(deps_ok: bool, render_ready: bool) -> dict:
    if not deps_ok:
        return {"ok": False, "skipped": True, "reason": "LTX runtime imports are not ready", "items": []}
    if not render_ready:
        return {"ok": False, "skipped": True, "reason": "required render model files are missing", "items": []}
    try:
        import safetensors  # noqa: F401
        from safetensors import safe_open
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "skipped": True, "reason": f"safetensors is unavailable: {exc}", "items": []}

    config_required = {"i2v_checkpoint", "t2v_checkpoint", "spatial_upscaler"}
    checked_keys = [
        "i2v_checkpoint",
        "t2v_checkpoint",
        "text_encoder",
        "text_projection",
        "spatial_upscaler",
        "audio_vae",
        "distil_lora",
    ]
    items = []
    for key in checked_keys:
        path = local_models.find_required_render_file(key)
        public = model_manifest.public_entry(next(item for item in model_manifest.required_render_files() if item["key"] == key))
        if path is None:
            items.append({**public, "ok": False, "path": "", "error": "file not found"})
            continue
        try:
            with safe_open(str(path), framework="pt", device="cpu") as fh:
                tensor_count = len(fh.keys())
                metadata = fh.metadata() or {}
            config_text = metadata.get("config", "")
            config_ok = True
            config_error = ""
            if key in config_required:
                if not config_text:
                    config_ok = False
                    config_error = "missing safetensors metadata['config']"
                else:
                    try:
                        parsed = json.loads(config_text)
                        if not isinstance(parsed, dict) or not parsed:
                            config_ok = False
                            config_error = "metadata['config'] is empty"
                    except Exception as exc:  # noqa: BLE001
                        config_ok = False
                        config_error = f"metadata['config'] is not valid JSON: {exc}"
            ok = tensor_count > 0 and config_ok
            error = "" if ok else (config_error or "safetensors contains no tensors")
            items.append(
                {
                    **public,
                    "ok": ok,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "tensor_count": tensor_count,
                    "config_required": key in config_required,
                    "config_present": bool(config_text),
                    "error": error,
                }
            )
        except Exception as exc:  # noqa: BLE001
            items.append({**public, "ok": False, "path": str(path), "bytes": path.stat().st_size, "error": str(exc)})

    return {"ok": all(item["ok"] for item in items), "skipped": False, "items": items}


def _component_bundle_check(deps_ok: bool, render_ready: bool) -> dict:
    if not deps_ok:
        return {"ok": False, "skipped": True, "reason": "LTX runtime imports are not ready"}
    if not render_ready:
        return {"ok": False, "skipped": True, "reason": "required render model files are missing"}

    required = {
        key: local_models.find_required_render_file(key)
        for key in [
            "t2v_checkpoint",
            "text_encoder",
            "text_projection",
            "spatial_upscaler",
            "audio_vae",
            "distil_lora",
        ]
    }
    missing = [key for key, path in required.items() if path is None]
    if missing:
        return {"ok": False, "skipped": True, "reason": "missing required files: " + ", ".join(missing)}

    text_encoder = required["text_encoder"]
    resolved = ltx_local_renderer.ResolvedRenderModels(
        checkpoint=required["t2v_checkpoint"],
        text_encoder=text_encoder,
        text_projection=required["text_projection"],
        spatial_upscaler=required["spatial_upscaler"],
        audio_vae=required["audio_vae"],
        video_vae=None,
        distil_lora=required["distil_lora"],
        gemma_root=text_encoder.parent,
        pipeline_kind="hq",
    )
    report = ltx_local_renderer.inspect_component_bundle(resolved)
    return {**report, "skipped": False}


def collect() -> dict[str, Any]:
    deps = ltx_local_renderer.dependency_report()
    deps_ok = all(item["ok"] for item in deps)
    device = ltx_local_renderer.device_report()
    device_ready = bool(device.get("ready"))
    render_models = local_models.scan_render_models()
    llm_models = local_models.scan_llm_models()
    render_required = _required_file_status(model_manifest.required_render_files(), local_models.find_required_render_file)
    llm_required = _llm_file_status()
    runner = _runner_help()
    dry_run = _dry_run_command(deps_ok, bool(render_models.get("ready")), device_ready)
    integrity = _safetensors_integrity(deps_ok, bool(render_models.get("ready")))
    component_bundle = _component_bundle_check(deps_ok, bool(render_models.get("ready")))
    renderer_status = ltx_local_renderer.status()
    integrity_ready = bool(integrity.get("ok")) if deps_ok and render_models.get("ready") else True
    component_ready = bool(component_bundle.get("ok")) if deps_ok and render_models.get("ready") else True

    return {
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
        },
        "paths": {
            "root": config.ROOT,
            "llm_model_dir": config.LLM_MODEL_DIR,
            "ltx_model_dir": config.LTX_MODEL_DIR,
            "frontend_dist": config.FRONTEND_DIST,
        },
        "dependencies": {
            "ready": deps_ok,
            "items": deps,
        },
        "device": device,
        "llm_models": {
            "ready": llm_models.get("ready", False),
            "required": llm_required,
            "scan": llm_models,
        },
        "render_models": {
            "ready": render_models.get("ready", False),
            "required": render_required,
            "scan": render_models,
        },
        "model_integrity": integrity,
        "component_bundle": component_bundle,
        "runner_entrypoint": runner,
        "dry_run": dry_run,
        "renderer_status": renderer_status,
        "overall_ready": bool(
            deps_ok
            and device_ready
            and llm_models.get("ready")
            and render_models.get("ready")
            and runner.get("ok")
            and dry_run.get("ok")
            and integrity_ready
            and component_ready
        ),
    }


def _print_human(data: dict[str, Any]) -> None:
    print("Cinematic Console local LTX diagnostics")
    print(f"Python: {data['python']['executable']}")
    print(f"Project: {data['paths']['root']}")
    print(f"LTX models: {data['paths']['ltx_model_dir']}")
    print(f"LLM models: {data['paths']['llm_model_dir']}")
    print()

    print(f"Dependencies: {'OK' if data['dependencies']['ready'] else 'MISSING'}")
    for item in data["dependencies"]["items"]:
        if not item["ok"]:
            print(f"  - {item['package']} ({item['module']}): {item['error']}")

    device = data.get("device", {})
    print(f"CUDA device: {'OK' if device.get('ready') else 'MISSING'}")
    if device.get("detail"):
        print(f"  {device['detail']}")
    for item in device.get("devices", []):
        total_gb = item.get("total_memory", 0) / 1024 / 1024 / 1024
        free = item.get("free_memory")
        if free is not None:
            free_gb = free / 1024 / 1024 / 1024
            print(f"  - GPU {item['index']}: {item['name']} ({free_gb:.1f}/{total_gb:.1f} GB free)")
        else:
            print(f"  - GPU {item['index']}: {item['name']} ({total_gb:.1f} GB)")

    print(f"Render models: {'OK' if data['render_models']['ready'] else 'MISSING'}")
    for item in data["render_models"]["required"]:
        if not item["present"]:
            print(f"  - {item['label']}: {item['name']}")
        else:
            print(f"  + {item['label']}: {item['path']} ({_fmt_bytes(item['bytes'])})")

    print(f"Prompt LLM models: {'OK' if data['llm_models']['ready'] else 'MISSING'}")
    for item in data["llm_models"]["required"]:
        if not item["present"]:
            print(f"  - {item['label']}: {item['name']}")
        else:
            print(f"  + {item['label']}: {item['path']} ({_fmt_bytes(item['bytes'])})")

    print(f"Runner entrypoint: {'OK' if data['runner_entrypoint']['ok'] else 'FAILED'}")
    print(f"Safetensors integrity: {'OK' if data['model_integrity']['ok'] else 'SKIPPED/FAILED'}")
    if data["model_integrity"].get("reason"):
        print(f"  reason: {data['model_integrity']['reason']}")
    for item in data["model_integrity"].get("items", []):
        if not item["ok"]:
            print(f"  - {item['label']}: {item.get('error', 'invalid')}")
    component_bundle = data.get("component_bundle", {})
    print(f"Component bundle: {'OK' if component_bundle.get('ok') else 'SKIPPED/FAILED'}")
    if component_bundle.get("reason"):
        print(f"  reason: {component_bundle['reason']}")
    for err in component_bundle.get("errors", []):
        print(f"  - {err}")
    print(f"Dry-run command: {'OK' if data['dry_run']['ok'] else 'SKIPPED/FAILED'}")
    if data["dry_run"].get("reason"):
        print(f"  reason: {data['dry_run']['reason']}")
    if data["dry_run"].get("error"):
        print(f"  error: {data['dry_run']['error']}")
    print()
    print(f"Overall ready: {'YES' if data['overall_ready'] else 'NO'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose local LTX installation for Cinematic Console")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--fail", action="store_true", help="exit non-zero when not fully ready")
    args = parser.parse_args()

    data = collect()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_human(data)
    if args.fail and not data["overall_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
