"""llama-server (llama.cpp) subprocess lifecycle manager.

Managed mode: we spawn `llama-server -m model.gguf --mmproj mmproj.gguf -ngl 99 -c 8192`
and watch its /health endpoint. External mode: we only health-check a user URL.
"""
import atexit
import os
import shlex
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Optional

import httpx

from . import config


def resolve_model_path(name: str) -> str:
    """Accept absolute paths or filenames relative to models/llm."""
    if not name:
        return ""
    if os.path.isabs(name) and os.path.exists(name):
        return name
    cand = os.path.join(config.LLM_MODEL_DIR, name)
    if os.path.exists(cand):
        return cand
    cand2 = os.path.join(config.ROOT, name)
    if os.path.exists(cand2):
        return cand2
    return name  # let llama-server report the error


def scan_llm_models() -> dict:
    """List *.gguf under models/llm, split mmproj projector files from main models."""
    ggufs, mmprojs = [], []
    try:
        for fn in sorted(os.listdir(config.LLM_MODEL_DIR)):
            if not fn.lower().endswith(".gguf"):
                continue
            if "mmproj" in fn.lower():
                mmprojs.append(fn)
            else:
                ggufs.append(fn)
    except OSError:
        pass
    return {"ggufs": ggufs, "mmprojs": mmprojs}


class LlamaManager:
    def __init__(self, on_log: Optional[Callable[[str, str], None]] = None):
        self.proc: Optional[subprocess.Popen] = None
        self.state = "stopped"  # stopped | starting | running | error
        self.detail = ""
        self.gguf = ""
        self.mmproj = ""
        self.port = 8731
        self.host = "127.0.0.1"
        self._on_log = on_log
        self._tail: deque = deque(maxlen=80)
        self._lock = threading.Lock()
        self._gen = 0  # generation counter; invalidates stale watcher threads
        atexit.register(self.stop)

    # ------------------------------------------------------------- helpers
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _log(self, msg: str, level: str = "info") -> None:
        if self._on_log:
            try:
                self._on_log(msg, level)
            except Exception:
                pass

    def status(self) -> dict:
        return {
            "state": self.state,
            "detail": self.detail,
            "gguf": os.path.basename(self.gguf) if self.gguf else "",
            "mmproj": os.path.basename(self.mmproj) if self.mmproj else "",
            "url": self.base_url if self.state in ("starting", "running") else "",
            "tail": list(self._tail)[-12:],
        }

    # -------------------------------------------------------------- start
    def start(self, settings: dict, gguf: str = "", mmproj: str = "") -> dict:
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._stop_locked()

            exe = settings.get("llama_server_path", "")
            if exe and not os.path.isabs(exe):
                exe = os.path.join(config.ROOT, exe)
            if not exe or not os.path.exists(exe):
                self.state = "error"
                self.detail = f"llama-server not found: {exe or '(unset)'} — run setup_llm.bat or set the path in Settings"
                self._log(self.detail, "error")
                return self.status()

            gguf_path = resolve_model_path(gguf or settings.get("llm_gguf", ""))
            if not gguf_path or not os.path.exists(gguf_path):
                self.state = "error"
                self.detail = f"GGUF model not found: {gguf_path or '(unset)'} — run setup_llm.bat or pick a model"
                self._log(self.detail, "error")
                return self.status()
            mmproj_path = resolve_model_path(mmproj or settings.get("llm_mmproj", ""))

            self.host = settings.get("llm_host", "127.0.0.1")
            self.port = int(settings.get("llm_port", 8731))
            self.gguf = gguf_path
            self.mmproj = mmproj_path if mmproj_path and os.path.exists(mmproj_path) else ""

            cmd = [
                exe,
                "-m", gguf_path,
                "--host", self.host,
                "--port", str(self.port),
                "-ngl", str(int(settings.get("llm_ngl", 99))),
                "-c", str(int(settings.get("llm_ctx", 8192))),
            ]
            if self.mmproj:
                cmd += ["--mmproj", self.mmproj]
            extra = settings.get("llm_extra_args", "").strip()
            if extra:
                try:
                    cmd += shlex.split(extra)
                except ValueError:
                    cmd += extra.split()

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(exe) or None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )
            except Exception as exc:  # noqa: BLE001
                self.state = "error"
                self.detail = f"failed to spawn llama-server: {exc}"
                self._log(self.detail, "error")
                return self.status()

            self.state = "starting"
            self.detail = f"loading {os.path.basename(gguf_path)} ..."
            self._log(f"llama-server starting on :{self.port} — {os.path.basename(gguf_path)}"
                      + (f" + {os.path.basename(self.mmproj)}" if self.mmproj else ""))
            threading.Thread(target=self._pump_output, args=(self.proc, gen), daemon=True).start()
            threading.Thread(target=self._wait_healthy, args=(gen,), daemon=True).start()
            return self.status()

    def _pump_output(self, proc: subprocess.Popen, gen: int) -> None:
        try:
            for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
                line = line.rstrip()
                if line:
                    self._tail.append(line)
        except Exception:
            pass

    def _wait_healthy(self, gen: int, timeout: float = 600.0) -> None:
        deadline = time.time() + timeout
        url = f"{self.base_url}/health"
        while time.time() < deadline:
            if gen != self._gen:
                return  # superseded by a newer start/stop
            proc = self.proc
            if proc is None or proc.poll() is not None:
                if gen == self._gen:
                    self.state = "error"
                    tail = " | ".join(list(self._tail)[-3:])
                    self.detail = f"llama-server exited (code {proc.returncode if proc else '?'}) {tail[:300]}"
                    self._log(self.detail, "error")
                return
            try:
                r = httpx.get(url, timeout=2.0, trust_env=False)
                if r.status_code == 200:
                    if gen == self._gen:
                        self.state = "running"
                        self.detail = f"ready on {self.base_url}"
                        self._log(f"llama-server ready — {self.base_url}")
                    return
            except Exception:
                pass
            time.sleep(1.0)
        if gen == self._gen:
            self.state = "error"
            self.detail = "llama-server health check timed out"
            self._log(self.detail, "error")

    # --------------------------------------------------------------- stop
    def _stop_locked(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
        if self.state != "error":
            self.state = "stopped"
            self.detail = ""

    def stop(self) -> dict:
        with self._lock:
            self._gen += 1
            self._stop_locked()
            self.state = "stopped"
            self.detail = ""
        return self.status()

    # ------------------------------------------------------------- health
    def probe(self) -> bool:
        """Re-check a 'running' server is still alive (called by status loop)."""
        if self.state != "running":
            return self.state == "running"
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.state = "error"
            self.detail = "llama-server process died"
            self._log(self.detail, "error")
            return False
        return True
