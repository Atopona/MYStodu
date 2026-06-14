"""Cinematic Console backend — FastAPI app, WebSocket hub, REST API."""
import asyncio
import json
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import comfy_client, config, db, jobs, llm_client, llm_embedded, llm_manager, mock, prompt_engine
from .schemas import GenerateRequest, LlmStartRequest, RefineRequest, RenderRequest, SettingsPatch

# --------------------------------------------------------------- WS hub


class Hub:
    def __init__(self) -> None:
        self.clients: List[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.log_buffer: List[dict] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        if payload.get("type") == "log":
            self.log_buffer.append(payload)
            self.log_buffer = self.log_buffer[-250:]
        dead = []
        text = json.dumps(payload, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, payload: dict) -> None:
        """Thread-safe fire-and-forget broadcast."""
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self.loop)


hub = Hub()


def log(msg: str, level: str = "info") -> None:
    hub.broadcast_sync({"type": "log", "ts": time.time(), "level": level, "msg": msg})


manager = llm_manager.LlamaManager(on_log=log)
embedded_manager = llm_embedded.EmbeddedLlamaManager(on_log=log)
runner = jobs.JobRunner(broadcast=hub.broadcast_sync)

_status_cache = {
    "llm": {"state": "stopped", "detail": "", "mock": False},
    "comfy": {"state": "down", "detail": "", "mock": False},
}


# ----------------------------------------------------------- status loop


async def llm_ready(settings: dict) -> bool:
    if settings["llm_mode"] == "embedded":
        return embedded_manager.ready()
    if settings["llm_mode"] == "external":
        return await llm_client.ping(settings["external_llm_url"], settings.get("llm_api_key", ""))
    return manager.state == "running" and manager.probe()


def llm_base_url(settings: dict) -> str:
    if settings["llm_mode"] == "external":
        return settings["external_llm_url"]
    return manager.base_url


async def compute_status() -> dict:
    settings = db.get_settings()
    comfy_up = await comfy_client.ping(settings["comfy_url"])
    if settings["llm_mode"] == "embedded":
        st = embedded_manager.status()
        llm_state = {**st, "mode": "embedded"}
        llm_up = embedded_manager.ready()
    elif settings["llm_mode"] == "external":
        ext_up = await llm_client.ping(settings["external_llm_url"], settings.get("llm_api_key", ""))
        llm_state = {
            "state": "running" if ext_up else "down",
            "detail": settings["external_llm_url"] + (" (external)" if ext_up else " unreachable"),
            "mode": "external",
            "gguf": "external endpoint",
            "mmproj": "",
        }
        llm_up = ext_up
    else:
        st = manager.status()
        manager.probe()
        llm_state = {**st, "mode": "managed"}
        llm_up = manager.state == "running"

    mock_llm_setting = settings.get("mock_llm", "auto")
    mock_comfy_setting = settings.get("mock_comfy", "auto")
    llm_state["mock"] = mock_llm_setting == "on" or (mock_llm_setting == "auto" and not llm_up)
    comfy_state = {
        "state": "running" if comfy_up else "down",
        "detail": settings["comfy_url"],
        "mock": mock_comfy_setting == "on" or (mock_comfy_setting == "auto" and not comfy_up),
        "url": settings["comfy_url"],
    }
    return {"type": "status", "llm": llm_state, "comfy": comfy_state,
            "mock_llm": mock_llm_setting, "mock_comfy": mock_comfy_setting}


async def status_loop() -> None:
    global _status_cache
    while True:
        try:
            st = await compute_status()
            changed = (
                st["llm"].get("state") != _status_cache["llm"].get("state")
                or st["comfy"].get("state") != _status_cache["comfy"].get("state")
            )
            _status_cache = {"llm": st["llm"], "comfy": st["comfy"]}
            await hub.broadcast(st)
            if changed:
                pass
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(5.0)


# ------------------------------------------------------------- lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.loop = asyncio.get_event_loop()
    runner.start()
    status_task = asyncio.create_task(status_loop())
    log("Console ready. Load a workflow, generate a prompt, hit Render.")
    try:
        node_map = comfy_client.load_node_map()
        for mode_key in ("i2v", "t2v"):
            m = node_map.get(mode_key)
            if m:
                wf = comfy_client.load_template(m["template"])
                log(f"Workflow loaded — {m['template']} · {len(wf)} nodes · map OK ({mode_key.upper()})")
    except Exception as exc:  # noqa: BLE001
        log(f"workflow templates: {exc}", "warn")
    settings = db.get_settings()
    if settings.get("auto_start_llm") and settings["llm_mode"] in ("embedded", "managed"):
        if settings["llm_mode"] == "embedded":
            await asyncio.to_thread(embedded_manager.start, settings)
        else:
            await asyncio.to_thread(manager.start, settings)
    yield
    status_task.cancel()
    embedded_manager.stop()
    manager.stop()


app = FastAPI(title="Cinematic Console", lifespan=lifespan)


# ------------------------------------------------------------------- WS


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        st = await compute_status()
        await ws.send_text(json.dumps(st, ensure_ascii=False))
        for entry in hub.log_buffer[-100:]:
            await ws.send_text(json.dumps(entry, ensure_ascii=False))
        while True:
            await ws.receive_text()  # keepalive pings from client
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        hub.disconnect(ws)


# ---------------------------------------------------------------- meta


@app.get("/api/meta")
async def api_meta():
    return {
        "shot_types": config.SHOT_TYPES,
        "resolutions": config.RESOLUTIONS,
        "version": "1.0.0",
    }


@app.get("/api/status")
async def api_status():
    return await compute_status()


# ------------------------------------------------------------- settings


@app.get("/api/settings")
async def get_settings():
    s = db.get_settings()
    s.pop("ui_state", None)
    return s


@app.put("/api/settings")
async def put_settings(patch: SettingsPatch):
    data = {k: v for k, v in patch.model_dump().items() if v is not None}
    s = db.update_settings(data)
    log("settings saved")
    await hub.broadcast(await compute_status())
    s.pop("ui_state", None)
    return s


@app.get("/api/ui-state")
async def get_ui_state():
    return {"state": db.get_setting("ui_state", None)}


@app.put("/api/ui-state")
async def put_ui_state(payload: dict):
    db.set_setting("ui_state", payload.get("state"))
    return {"ok": True}


# ------------------------------------------------------------------ LLM


@app.get("/api/llm/models")
async def api_llm_models():
    scanned = llm_manager.scan_llm_models()
    suggested = not scanned["ggufs"]
    if suggested:
        return {
            **mock.MOCK_LLM_SUGGESTIONS,
            "suggested": True,
            "source": "suggested",
            "mock_reason": "models/llm 里没有 GGUF；这里显示的是推荐文件名，不代表已下载。",
        }
    return {**scanned, "suggested": False, "source": "local"}


@app.post("/api/llm/start")
async def api_llm_start(req: LlmStartRequest):
    settings = db.get_settings()
    if settings["llm_mode"] == "embedded":
        patch = {}
        if req.gguf:
            patch["llm_gguf"] = req.gguf
        if req.mmproj:
            patch["llm_mmproj"] = req.mmproj
        if patch:
            settings = db.update_settings(patch)
        st = await asyncio.to_thread(embedded_manager.start, settings, req.gguf or "", req.mmproj or "")
        await hub.broadcast(await compute_status())
        if st["state"] == "error":
            raise HTTPException(502, st["detail"])
        return st
    if settings["llm_mode"] == "external":
        ok = await llm_client.ping(settings["external_llm_url"], settings.get("llm_api_key", ""))
        if not ok:
            raise HTTPException(502, f"外部 LLM 端点不可达：{settings['external_llm_url']}")
        return {"state": "running", "detail": "external endpoint ok"}
    patch = {}
    if req.gguf:
        patch["llm_gguf"] = req.gguf
    if req.mmproj:
        patch["llm_mmproj"] = req.mmproj
    if patch:
        settings = db.update_settings(patch)
    st = await asyncio.to_thread(manager.start, settings, req.gguf or "", req.mmproj or "")
    await hub.broadcast(await compute_status())
    if st["state"] == "error":
        raise HTTPException(502, st["detail"])
    return st


@app.post("/api/llm/stop")
async def api_llm_stop():
    embedded_manager.stop()
    st = manager.stop()
    await hub.broadcast(await compute_status())
    return st


# ---------------------------------------------------------------- comfy


@app.get("/api/models")
async def api_models():
    """Model lists for the PIPELINE panel — real ComfyUI scan or mock zoo."""
    settings = db.get_settings()
    mock_mode = settings.get("mock_comfy", "auto")
    if mock_mode != "on":
        try:
            timeout = 20.0 if mock_mode == "off" else 2.0
            if mock_mode == "auto" and not await comfy_client.ping(settings["comfy_url"], timeout=0.75):
                raise comfy_client.ComfyError("ComfyUI ping failed")
            info = await comfy_client.object_info(settings["comfy_url"], timeout=timeout)
            lists = comfy_client.extract_model_lists(info)
            if any(lists.values()):
                return {**lists, "source": "comfyui"}
        except Exception:  # noqa: BLE001
            if mock_mode == "off":
                raise HTTPException(502, f"ComfyUI 不可达：{settings['comfy_url']} — 无法扫描模型列表")
    return {
        **mock.MOCK_COMFY_MODELS,
        "source": "mock",
        "mock_reason": "ComfyUI 未连接；这是离线演示用的示例模型名，不代表本机已下载这些模型。",
    }


# --------------------------------------------------------------- upload


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(400, "图片太大（>30MB）")
    from PIL import Image
    import io

    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        w, h = im.size
        fmt = (im.format or "PNG").lower()
    except Exception:
        raise HTTPException(400, "不是有效的图片文件（支持 png/jpg/webp）")
    ext = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(fmt, ".png")
    image_id = uuid.uuid4().hex[:12] + ext
    path = os.path.join(config.UPLOAD_DIR, image_id)
    with open(path, "wb") as fh:
        fh.write(raw)
    log(f"reference image uploaded — {w}x{h} ({image_id})")
    return {"id": image_id, "url": f"/files/uploads/{image_id}", "width": w, "height": h}


# ------------------------------------------------------------- generate


def _resolve_style(settings: dict, image_used: bool) -> str:
    style = settings.get("prompt_style", "auto")
    if style in ("sulphur", "director"):
        return style
    name = (settings.get("llm_gguf", "") or "").lower()
    if "sulphur" in name or "enhancer" in name or "prompt" in name:
        return "sulphur"
    return "director"


def _camera_suggestion(beats: List[dict]) -> str:
    seen: List[str] = []
    for b in beats:
        m = b["motion"].lower()
        if m not in seen and m not in ("shot",):
            seen.append(m)
    return ", ".join(seen[:5]) if seen else "static"


async def _llm_generate(req: GenerateRequest, refine: Optional[RefineRequest] = None) -> dict:
    settings = db.get_settings()
    mock_setting = settings.get("mock_llm", "auto")
    image_path = None
    if req.mode == "i2v" and req.image_id:
        p = os.path.join(config.UPLOAD_DIR, os.path.basename(req.image_id))
        image_path = p if os.path.exists(p) else None

    use_real = mock_setting == "off" or (mock_setting == "auto" and await llm_ready(settings))
    used_mock = False
    text = ""
    model_label = ""

    if use_real:
        style = _resolve_style(settings, image_path is not None)
        system_prompt = prompt_engine.DIRECTOR_SYSTEM_PROMPT if style == "director" else None
        if refine is not None:
            user_text = prompt_engine.build_refine_user_text(refine.prompt, refine.instruction)
        else:
            user_text = prompt_engine.build_generation_user_text(
                intent=req.intent, duration=req.duration, fps=req.fps,
                shot_type=req.shot_type, dialogue=req.dialogue, fov=req.fov,
                choreo=req.choreo, lora_triggers=req.lora_triggers,
                mode=req.mode, has_image=image_path is not None,
            )
        messages = llm_client.build_messages(
            system_prompt=system_prompt, user_text=user_text, image_path=image_path
        )
        temperature = 0.2 + max(0.0, min(1.0, req.creativity)) * 1.2
        try:
            log(f"LLM {'refine' if refine else 'generate'} — mode={settings['llm_mode']}, style={style}, temp={temperature:.2f}")
            if settings["llm_mode"] == "embedded":
                text = await asyncio.to_thread(
                    embedded_manager.chat,
                    settings,
                    messages,
                    temperature=temperature,
                )
            else:
                text = await llm_client.chat(
                    llm_base_url(settings), messages,
                    temperature=temperature, api_key=settings.get("llm_api_key", ""),
                )
            model_label = settings.get("llm_gguf") or settings.get("llm_mode", "embedded")
        except (llm_client.LlmError, RuntimeError) as exc:
            if mock_setting == "off":
                raise HTTPException(502, f"LLM 调用失败：{exc}")
            log(f"LLM unavailable ({exc}) — falling back to mock prompt", "warn")
            use_real = False

    if not use_real:
        used_mock = True
        model_label = "mock"
        if refine is not None:
            text = mock.mock_refine(refine.prompt, refine.instruction)
        else:
            text = mock.mock_generate(
                intent=req.intent, duration=req.duration, shot_type=req.shot_type,
                dialogue=req.dialogue, fov=req.fov, choreo=req.choreo,
                lora_triggers=req.lora_triggers, creativity=req.creativity, mode=req.mode,
            )
        await asyncio.sleep(0.7)  # tiny beat so the UI's working state is visible

    text = prompt_engine.ensure_beats(text, req.duration)
    beats = prompt_engine.parse_beats(text)
    words = prompt_engine.word_count(text)
    log(f"prompt {'refined' if refine else 'generated'} — {len(beats)} beats · {words} words" + (" · MOCK" if used_mock else ""))
    log(f"\U0001F4F7 Camera LoRA suggestion: {_camera_suggestion(beats)}")
    return {
        "prompt": text,
        "beats": beats,
        "words": words,
        "used_mock": used_mock,
        "model": model_label,
    }


@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    if req.mode == "i2v" and not req.image_id:
        raise HTTPException(400, "I2V 模式需要先上传参考图（或切换到 T2V）")
    return await _llm_generate(req)


@app.post("/api/refine")
async def api_refine(req: RefineRequest):
    if not req.prompt.strip():
        raise HTTPException(400, "当前没有可润色的提示词，先 GENERATE 一次")
    if not req.instruction.strip():
        raise HTTPException(400, "请输入修改指令（如 make beat 2 slower）")
    return await _llm_generate(req, refine=req)


# --------------------------------------------------------------- render


def _validate_distil_mutex(req: RenderRequest) -> None:
    ckpt = (req.pipeline.checkpoint or "").lower()
    distil_on = (req.pipeline.distil1.enabled and req.pipeline.distil1.model) or (
        req.pipeline.distil2.enabled and req.pipeline.distil2.model
    )
    if "distil" in ckpt and distil_on:
        raise HTTPException(
            400,
            "Distill LoRA 与完整 distilled checkpoint 互斥（二选一）：当前 checkpoint 已是 distilled 完整模型，"
            "请在 PIPELINE 面板关闭 First/Second Stage Distil，或换用非 distilled checkpoint。",
        )


@app.post("/api/render")
async def api_render(req: RenderRequest):
    if not req.prompt.strip():
        raise HTTPException(400, "提示词为空 — 先 GENERATE 或手动输入")
    if req.mode == "i2v" and not req.image_id:
        raise HTTPException(400, "I2V 渲染需要参考图")
    _validate_distil_mutex(req)

    settings = db.get_settings()
    keep_ts = settings.get("keep_timestamps", False) if req.keep_timestamps is None else req.keep_timestamps
    final_prompt = req.prompt.strip() if keep_ts else prompt_engine.strip_timestamps(req.prompt)
    seed = req.seed if req.seed > 0 else random.randint(10**11, 10**12 - 1)

    p = req.params
    p.frames = config.snap_frames(p.duration, p.fps)

    mock_setting = settings.get("mock_comfy", "auto")
    comfy_up = await comfy_client.ping(settings["comfy_url"])
    if mock_setting == "off" and not comfy_up:
        raise HTTPException(502, f"ComfyUI 不可达：{settings['comfy_url']} — 请检查地址或启动 ComfyUI（设置里可改为 Mock）")
    use_mock = mock_setting == "on" or (mock_setting == "auto" and not comfy_up)

    image_path = None
    if req.image_id:
        cand = os.path.join(config.UPLOAD_DIR, os.path.basename(req.image_id))
        image_path = cand if os.path.exists(cand) else None
        if req.mode == "i2v" and image_path is None:
            raise HTTPException(400, "参考图已失效，请重新上传")

    meta = {
        "seed": seed, "frames": p.frames, "width": p.width, "height": p.height,
        "fps": p.fps, "duration": p.duration, "mock": use_mock,
        "words": prompt_engine.word_count(req.prompt),
        "keep_timestamps": keep_ts,
        "image_id": req.image_id or "",
    }
    params_snapshot = req.ui_snapshot or {}
    job_id = db.create_job(req.mode, req.prompt, params_snapshot, meta)

    await runner.enqueue(job_id, {
        "mode": req.mode,
        "use_mock": use_mock,
        "seed": seed,
        "final_prompt": final_prompt,
        "image_path": image_path,
        "params": p.model_dump(),
        "pipeline": req.pipeline.model_dump(),
        "meta": meta,
    })
    log(f"job {job_id} queued — {req.mode.upper()} · {p.width}x{p.height} · {p.frames}f @ {p.fps}fps · seed {seed}"
        + (" · MOCK" if use_mock else ""))
    return {"job_id": job_id, "seed": seed, "frames": p.frames, "mock": use_mock}


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel(job_id: str):
    ok = runner.cancel(job_id)
    if not ok:
        raise HTTPException(404, "任务不存在或已结束")
    return {"ok": True}


# -------------------------------------------------------------- history


@app.get("/api/history")
async def api_history(limit: int = 60):
    items = db.list_jobs(limit)
    for it in items:
        it["video_url"] = it.pop("video_path", "")
        it["thumb_url"] = it.pop("thumb_path", "")
        it["prompt_excerpt"] = (it["prompt"] or "")[:220]
    return {"items": items}


@app.get("/api/history/{job_id}")
async def api_history_item(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "记录不存在")
    job["video_url"] = job.pop("video_path", "")
    job["thumb_url"] = job.pop("thumb_path", "")
    return job


@app.delete("/api/history/{job_id}")
async def api_history_delete(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "记录不存在")
    for rel in (job.get("video_path"), job.get("thumb_path")):
        if rel:
            path = os.path.join(config.ROOT, rel.lstrip("/").replace("files/", "", 1).replace("/", os.sep))
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
    db.delete_job(job_id)
    log(f"history {job_id} deleted")
    return {"ok": True}


# --------------------------------------------------------------- static


app.mount("/files/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
app.mount("/files/outputs", StaticFiles(directory=config.OUTPUT_DIR), name="outputs")

if os.path.isdir(os.path.join(config.FRONTEND_DIST, "assets")):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(config.FRONTEND_DIST, "assets")),
        name="assets",
    )


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    path = os.path.join(config.FRONTEND_DIST, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404)


@app.get("/", include_in_schema=False)
async def index():
    path = os.path.join(config.FRONTEND_DIST, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse(
        {"error": "frontend not built — run `npm run build` in frontend/ (start.bat does this automatically)"},
        status_code=503,
    )
