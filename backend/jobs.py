"""Render job runner: one job at a time, queue, WS events, mock + real paths."""
import asyncio
import base64
import os
import random
import time
import uuid
from typing import Callable, Dict, List, Optional

from . import comfy_client, config, db, mock, prompt_engine


class JobRunner:
    def __init__(self, broadcast: Callable[[dict], None]):
        # broadcast must be a sync callable that schedules a WS fan-out
        self.broadcast = broadcast
        self.queue: "asyncio.Queue[dict]" = asyncio.Queue()
        self.current_id: Optional[str] = None
        self.cancel_events: Dict[str, asyncio.Event] = {}
        self._worker: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------- api
    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.get_running_loop().create_task(self._run_loop())

    def log(self, msg: str, level: str = "info") -> None:
        self.broadcast({"type": "log", "ts": time.time(), "level": level, "msg": msg})

    def emit(self, payload: dict) -> None:
        self.broadcast(payload)

    async def enqueue(self, job_id: str, spec: dict) -> None:
        self.cancel_events[job_id] = asyncio.Event()
        await self.queue.put({"job_id": job_id, **spec})
        self.emit({"type": "job_update", "job_id": job_id, "status": "queued", "phase": "queued", "pct": 0})

    def cancel(self, job_id: str) -> bool:
        ev = self.cancel_events.get(job_id)
        if ev:
            ev.set()
            return True
        return False

    # --------------------------------------------------------------- loop
    async def _run_loop(self) -> None:
        while True:
            spec = await self.queue.get()
            job_id = spec["job_id"]
            self.current_id = job_id
            cancel = self.cancel_events.get(job_id) or asyncio.Event()
            try:
                if cancel.is_set():
                    raise asyncio.CancelledError()
                db.update_job(job_id, status="running", phase="pass1")
                if spec["use_mock"]:
                    await self._run_mock(job_id, spec, cancel)
                else:
                    await self._run_comfy(job_id, spec, cancel)
            except asyncio.CancelledError:
                db.update_job(job_id, status="cancelled", phase="cancelled")
                self.emit({"type": "job_update", "job_id": job_id, "status": "cancelled", "phase": "cancelled", "pct": 0})
                self.log(f"job {job_id} cancelled", "warn")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                db.update_job(job_id, status="error", error=msg)
                hint = ""
                low = msg.lower()
                if "out of memory" in low or "oom" in low or "cuda" in low and "memory" in low:
                    hint = " — VRAM不足：把 decode tile 设为 512 后重试"
                self.emit({"type": "job_update", "job_id": job_id, "status": "error", "phase": "error", "pct": 0, "error": msg + hint})
                self.log(f"render failed: {msg}{hint}", "error")
            finally:
                self.current_id = None
                self.cancel_events.pop(job_id, None)

    # --------------------------------------------------------------- mock
    async def _run_mock(self, job_id: str, spec: dict, cancel: asyncio.Event) -> None:
        p = spec["params"]
        seed = spec["seed"]
        self.log(f"[mock] queue accepted — job {job_id} · seed {seed}")
        self.log(f"[mock] workflow assembled: {spec['mode'].upper()} two-pass · {p['width']}x{p['height']} · {p['frames']}f @ {p['fps']}fps")

        async def run_pass(phase: str, steps: int, label: str) -> None:
            db.update_job(job_id, phase=phase)
            for s in range(1, steps + 1):
                if cancel.is_set():
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.16 if phase == "pass1" else 0.22)
                self.emit({
                    "type": "job_update", "job_id": job_id, "status": "running",
                    "phase": phase, "step": s, "total": steps,
                    "pct": round(100 * s / steps),
                })
                if s % 2 == 0 or s == steps:
                    b64 = await asyncio.to_thread(
                        mock.make_preview_frame, s, steps, label, seed + (0 if phase == "pass1" else 7)
                    )
                    self.emit({"type": "preview", "job_id": job_id, "phase": phase, "image": b64})

        self.log("[mock] PASS 1 — base render (denoise)")
        await run_pass("pass1", 18, "PASS 1")
        self.log("[mock] PASS 1 complete — latents handed to spatial upscaler")
        self.log("[mock] PASS 2 — x2 spatial upscale refine")
        await run_pass("pass2", 12, "PASS 2")

        db.update_job(job_id, phase="saving")
        self.emit({"type": "job_update", "job_id": job_id, "status": "running", "phase": "saving", "pct": 100})
        self.log("[mock] encoding placeholder video (ffmpeg)")
        video_path = os.path.join(config.OUTPUT_DIR, f"{job_id}.mp4")
        ok = await asyncio.to_thread(
            mock.make_mock_video,
            video_path,
            width=p["width"], height=p["height"], fps=p["fps"],
            duration=p["duration"], seed=seed,
            log=lambda m: self.log(m, "warn"),
        )
        if not ok:
            raise RuntimeError("mock video synthesis failed (ffmpeg unavailable?)")
        thumb_path = os.path.join(config.THUMB_DIR, f"{job_id}.jpg")
        await asyncio.to_thread(mock.make_thumbnail, video_path, thumb_path, min(1.0, p["duration"] / 2))
        self._finish(job_id, video_path, thumb_path, mock_used=True)

    # -------------------------------------------------------------- comfy
    async def _run_comfy(self, job_id: str, spec: dict, cancel: asyncio.Event) -> None:
        settings = db.get_settings()
        base_url = settings["comfy_url"]
        p = spec["params"]
        mode = spec["mode"]

        values: Dict[str, object] = {
            "positive_prompt": spec["final_prompt"],
            "negative_prompt": settings.get("negative_prompt", ""),
            "seed": spec["seed"],
            "width": p["width"], "height": p["height"],
            "frames": p["frames"], "fps": p["fps"],
            "frame_overlap": p["frame_overlap"],
            "transition_fade": p["transition_fade"],
            "midscene_guide": p["midscene_guide"],
            "carry_i2v_guides": p["carry_i2v_guides"],
            "midscene_anchor": p["midscene_anchor"],
            "decode_tile": p["decode_tile"],
        }
        pl = spec["pipeline"]
        values.update({
            "checkpoint": pl.get("checkpoint") or None,
            "text_encoder": pl.get("text_encoder") or None,
            "text_projection": pl.get("text_projection") or None,
            "upscaler": pl.get("upscaler") or None,
            "audio_vae": pl.get("audio_vae") or None,
            "preview_vae": pl.get("preview_vae") or None,
        })
        for idx in (1, 2):
            d = pl.get(f"distil{idx}") or {}
            if d.get("enabled") and d.get("model"):
                values[f"distil{idx}_model"] = d["model"]
                values[f"distil{idx}_str"] = float(d.get("strength", 1.0))
                values[f"distil{idx}_visual"] = float(d.get("visual", 1.0))
                values[f"distil{idx}_audio"] = float(d.get("audio", 1.0))

        if mode == "i2v":
            image_path = spec.get("image_path")
            if not image_path or not os.path.exists(image_path):
                raise comfy_client.ComfyError("I2V render needs a reference image")
            self.log("uploading reference image to ComfyUI ...")
            values["image"] = await comfy_client.upload_image(base_url, image_path)

        wf, mapping, warnings = comfy_client.build_workflow(mode, values, pl.get("loras") or [])
        for w in warnings:
            self.log(f"node_map: {w}", "warn")

        client_id = uuid.uuid4().hex
        prompt_id = await comfy_client.submit(base_url, wf, client_id)
        self.log(f"workflow submitted — prompt_id {prompt_id[:8]}… ({len(wf)} nodes)")
        db.update_job(job_id, meta={**spec["meta"], "prompt_id": prompt_id})

        last_phase = {"v": "pass1"}

        def on_progress(phase: str, v: int, m: int) -> None:
            if phase != last_phase["v"]:
                last_phase["v"] = phase
                db.update_job(job_id, phase=phase)
                self.log(f"{'PASS 2 — spatial upscale' if phase == 'pass2' else 'PASS 1 — base render'} started")
            self.emit({
                "type": "job_update", "job_id": job_id, "status": "running",
                "phase": phase, "step": v, "total": m,
                "pct": round(100 * v / max(1, m)),
            })

        def on_preview(blob: bytes) -> None:
            self.emit({
                "type": "preview", "job_id": job_id, "phase": last_phase["v"],
                "image": base64.b64encode(blob).decode("ascii"),
            })

        def on_node(node: Optional[str]) -> None:
            if node:
                self.emit({"type": "node", "job_id": job_id, "node": node})

        await comfy_client.listen(
            base_url, client_id, prompt_id,
            on_progress=on_progress, on_preview=on_preview, on_node=on_node,
            pass_nodes=mapping.get("progress_nodes", {}),
            cancel=cancel,
        )

        db.update_job(job_id, phase="saving")
        self.emit({"type": "job_update", "job_id": job_id, "status": "running", "phase": "saving", "pct": 100})
        history = await comfy_client.get_history(base_url, prompt_id)
        ent = comfy_client.pick_video_output(history)
        if not ent:
            raise comfy_client.ComfyError("no video output found in ComfyUI history — check SaveVideo node / node_map outputs")
        ext = os.path.splitext(ent.get("filename", "out.mp4"))[1] or ".mp4"
        video_path = os.path.join(config.OUTPUT_DIR, f"{job_id}{ext}")
        ok = await comfy_client.download_view(
            base_url, ent["filename"], ent.get("subfolder", ""), ent.get("type", "output"), video_path
        )
        if not ok:
            raise comfy_client.ComfyError(f"failed to download output {ent.get('filename')}")
        thumb_path = os.path.join(config.THUMB_DIR, f"{job_id}.jpg")
        await asyncio.to_thread(mock.make_thumbnail, video_path, thumb_path, 1.0)
        self._finish(job_id, video_path, thumb_path, mock_used=False)

    # ------------------------------------------------------------- finish
    def _finish(self, job_id: str, video_path: str, thumb_path: str, mock_used: bool) -> None:
        rel_video = f"/files/outputs/{os.path.basename(video_path)}"
        rel_thumb = (
            f"/files/outputs/thumbs/{os.path.basename(thumb_path)}"
            if os.path.exists(thumb_path)
            else ""
        )
        db.update_job(job_id, status="done", phase="done", video_path=rel_video, thumb_path=rel_thumb)
        self.emit({
            "type": "job_update", "job_id": job_id, "status": "done", "phase": "done",
            "pct": 100, "video_url": rel_video, "thumb_url": rel_thumb,
        })
        self.log(f"render complete — {os.path.basename(video_path)}" + (" (mock)" if mock_used else ""))
