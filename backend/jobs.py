"""Render job runner: one job at a time, backed by the local LTX pipeline."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Callable, Dict, Optional

from . import config, db, ltx_local_renderer, media


class JobRunner:
    def __init__(self, broadcast: Callable[[dict], None]):
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
                await self._run_local_ltx(job_id, spec, cancel)
            except asyncio.CancelledError:
                db.update_job(job_id, status="cancelled", phase="cancelled")
                self.emit(
                    {
                        "type": "job_update",
                        "job_id": job_id,
                        "status": "cancelled",
                        "phase": "cancelled",
                        "pct": 0,
                    }
                )
                self.log(f"job {job_id} cancelled", "warn")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                db.update_job(job_id, status="error", error=msg)
                hint = ""
                low = msg.lower()
                if "out of memory" in low or "oom" in low or ("cuda" in low and "memory" in low):
                    hint = " — VRAM 不足：降低分辨率，或设置环境变量 LTX_OFFLOAD=cpu 后重试"
                self.emit(
                    {
                        "type": "job_update",
                        "job_id": job_id,
                        "status": "error",
                        "phase": "error",
                        "pct": 0,
                        "error": msg + hint,
                    }
                )
                self.log(f"render failed: {msg}{hint}", "error")
            finally:
                self.current_id = None
                self.cancel_events.pop(job_id, None)

    # ----------------------------------------------------------- local LTX
    async def _run_local_ltx(self, job_id: str, spec: dict, cancel: asyncio.Event) -> None:
        render_spec: ltx_local_renderer.LocalRenderSpec = spec["ltx_spec"]
        db.update_job(job_id, phase="pass1", meta={**spec["meta"], "renderer": "local-ltx", **render_spec.summary})
        video_path = await ltx_local_renderer.run_job(
            job_id=job_id,
            spec=render_spec,
            cancel=cancel,
            emit=self.emit,
            log=self.log,
        )

        db.update_job(job_id, phase="saving")
        self.emit({"type": "job_update", "job_id": job_id, "status": "running", "phase": "saving", "pct": 100})
        thumb_path = os.path.join(config.THUMB_DIR, f"{job_id}.jpg")
        await asyncio.to_thread(media.make_thumbnail, video_path, thumb_path, 1.0)
        self._finish(job_id, video_path, thumb_path)

    # ------------------------------------------------------------- finish
    def _finish(self, job_id: str, video_path: str, thumb_path: str) -> None:
        rel_video = f"/files/outputs/{os.path.basename(video_path)}"
        rel_thumb = (
            f"/files/outputs/thumbs/{os.path.basename(thumb_path)}"
            if os.path.exists(thumb_path)
            else ""
        )
        db.update_job(job_id, status="done", phase="done", video_path=rel_video, thumb_path=rel_thumb)
        self.emit(
            {
                "type": "job_update",
                "job_id": job_id,
                "status": "done",
                "phase": "done",
                "pct": 100,
                "video_url": rel_video,
                "thumb_url": rel_thumb,
            }
        )
        self.log(f"render complete — {os.path.basename(video_path)}")
