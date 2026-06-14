"""In-process llama.cpp runtime via llama-cpp-python.

This is the preferred local LLM path: the FastAPI backend loads the GGUF
directly in-process, so users do not need to start or manage a separate LLM
HTTP service. The older llama-server subprocess path remains available as a
compatibility fallback in llm_manager.py.
"""
import atexit
import os
import threading
from collections import deque
from typing import Callable, Optional

from . import llm_manager


class EmbeddedLlamaManager:
    def __init__(self, on_log: Optional[Callable[[str, str], None]] = None):
        self.llm = None
        self.state = "stopped"  # stopped | loading | running | error
        self.detail = ""
        self.gguf = ""
        self.mmproj = ""
        self._on_log = on_log
        self._tail: deque = deque(maxlen=80)
        self._lock = threading.Lock()
        atexit.register(self.stop)

    def _log(self, msg: str, level: str = "info") -> None:
        self._tail.append(msg)
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
            "url": "",
            "tail": list(self._tail)[-12:],
        }

    def ready(self) -> bool:
        return self.state == "running" and self.llm is not None

    def start(self, settings: dict, gguf: str = "", mmproj: str = "") -> dict:
        with self._lock:
            target_gguf = llm_manager.resolve_model_path(gguf or settings.get("llm_gguf", ""))
            target_mmproj = llm_manager.resolve_model_path(mmproj or settings.get("llm_mmproj", ""))

            if self.ready() and target_gguf == self.gguf and target_mmproj == self.mmproj:
                return self.status()

            self.stop()
            if not target_gguf or not os.path.exists(target_gguf):
                self.state = "error"
                self.detail = (
                    f"GGUF model not found: {target_gguf or '(unset)'} — "
                    "run install_linux.sh or set models/llm paths"
                )
                self._log(self.detail, "error")
                return self.status()

            try:
                from llama_cpp import Llama
            except Exception as exc:  # noqa: BLE001
                self.state = "error"
                self.detail = (
                    "llama-cpp-python is not installed. Run install_linux.sh "
                    "or `pip install llama-cpp-python` in the project venv."
                )
                self._log(f"{self.detail} ({exc})", "error")
                return self.status()

            self.state = "loading"
            self.detail = f"loading {os.path.basename(target_gguf)} in backend process ..."
            self._log(f"embedded llama.cpp loading — {os.path.basename(target_gguf)}")

            kwargs = {
                "model_path": target_gguf,
                "n_ctx": int(settings.get("llm_ctx", 8192)),
                "n_gpu_layers": int(settings.get("llm_ngl", 99)),
                "verbose": False,
            }
            if target_mmproj and os.path.exists(target_mmproj):
                try:
                    from llama_cpp.llama_chat_format import Llava15ChatHandler

                    kwargs["chat_handler"] = Llava15ChatHandler(clip_model_path=target_mmproj)
                    self.mmproj = target_mmproj
                except Exception as exc:  # noqa: BLE001
                    self._log(
                        f"mmproj present but embedded vision handler was unavailable: {exc}",
                        "warn",
                    )
                    self.mmproj = ""
            else:
                self.mmproj = ""

            try:
                self.llm = Llama(**kwargs)
            except Exception as exc:  # noqa: BLE001
                self.llm = None
                self.state = "error"
                self.detail = f"failed to load embedded GGUF: {exc}"
                self._log(self.detail, "error")
                return self.status()

            self.gguf = target_gguf
            self.state = "running"
            self.detail = "ready in backend process"
            self._log("embedded llama.cpp ready — no external LLM service")
            return self.status()

    def stop(self) -> dict:
        self.llm = None
        if self.state != "error":
            self.state = "stopped"
            self.detail = ""
        return self.status()

    def chat(self, settings: dict, messages: list, *, temperature: float, max_tokens: int = 3072) -> str:
        if not self.ready():
            st = self.start(settings)
            if st["state"] != "running":
                raise RuntimeError(st.get("detail") or "embedded LLM is not ready")
        try:
            out = self.llm.create_chat_completion(  # type: ignore[union-attr]
                messages=messages,
                temperature=round(max(0.0, min(2.0, temperature)), 2),
                max_tokens=max_tokens,
                stream=False,
            )
            text = out["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"embedded LLM failed: {exc}") from exc
        if not (text or "").strip():
            raise RuntimeError("embedded LLM returned an empty completion")
        return text.strip()
