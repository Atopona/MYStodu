"""In-process llama.cpp runtime via llama-cpp-python.

This is the preferred local LLM path: the FastAPI backend loads the GGUF
directly in-process, so users do not need to start or manage a separate LLM
HTTP service. The older llama-server subprocess path remains available as a
compatibility fallback in llm_manager.py.
"""
import atexit
import importlib
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

    def _make_chat_handler(self, mmproj_path: str):
        llama_chat_format = importlib.import_module("llama_cpp.llama_chat_format")

        handler_names = (
            "Gemma3ChatHandler",
            "Llava16ChatHandler",
            "Llava15ChatHandler",
            "NanoLlavaChatHandler",
        )
        last_error = ""
        for name in handler_names:
            cls = getattr(llama_chat_format, name, None)
            if cls is None:
                continue
            for kwargs in ({"clip_model_path": mmproj_path}, {"mmproj_path": mmproj_path}):
                try:
                    handler = cls(**kwargs)
                    self._log(f"embedded vision handler: {name}")
                    return handler
                except TypeError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    last_error = f"{name}: {exc}"
                    break
        raise RuntimeError(last_error or "no compatible llama-cpp-python vision chat handler found")

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
                    kwargs["chat_handler"] = self._make_chat_handler(target_mmproj)
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

    @staticmethod
    def _messages_need_vision(messages: list) -> bool:
        for message in messages:
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
        return False

    def chat(self, settings: dict, messages: list, *, temperature: float, max_tokens: int = 3072) -> str:
        target_gguf = llm_manager.resolve_model_path(settings.get("llm_gguf", ""))
        target_mmproj = llm_manager.resolve_model_path(settings.get("llm_mmproj", ""))
        if (
            not self.ready()
            or target_gguf != self.gguf
            or ((target_mmproj if target_mmproj and os.path.exists(target_mmproj) else "") != self.mmproj)
        ):
            st = self.start(settings)
            if st["state"] != "running":
                raise RuntimeError(st.get("detail") or "embedded LLM is not ready")
        if self._messages_need_vision(messages) and not self.mmproj:
            raise RuntimeError(
                "I2V prompt generation requires a loaded local mmproj vision projector. "
                "Run install_linux.sh, select a valid mmproj, and make sure llama-cpp-python supports the Gemma3 vision handler."
            )
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
