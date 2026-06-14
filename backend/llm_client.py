"""OpenAI-compatible chat client (llama-server / LM Studio / Ollama-openai)."""
import base64
import os
import socket
from typing import List, Optional
from urllib.parse import urlparse

import httpx


class LlmError(Exception):
    pass


def _local_tcp_open(base_url: str, timeout: float = 0.25) -> bool:
    """Fast localhost preflight for external llama-server/LM Studio probes."""
    parsed = urlparse(base_url if base_url.startswith("http") else "http://" + base_url)
    host = parsed.hostname or "127.0.0.1"
    if host not in ("127.0.0.1", "localhost", "::1"):
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def image_to_data_url(path: str, max_side: int = 1344) -> str:
    """Load an image file, downscale if huge, return data: URL (jpeg)."""
    from PIL import Image
    import io

    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = max(w, h) / max_side
        if scale > 1:
            im = im.resize((int(w / scale), int(h / scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_messages(
    *,
    system_prompt: Optional[str],
    user_text: str,
    image_path: Optional[str] = None,
) -> List[dict]:
    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if image_path and os.path.exists(image_path):
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
        ]
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_text})
    return messages


async def chat(
    base_url: str,
    messages: List[dict],
    *,
    temperature: float = 0.8,
    max_tokens: int = 3072,
    api_key: str = "",
    timeout: float = 420.0,
) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": "default",
        "messages": messages,
        "temperature": round(max(0.0, min(2.0, temperature)), 2),
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LlmError(f"LLM unreachable at {url}: {exc.__class__.__name__}") from exc
    if r.status_code != 200:
        raise LlmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
        text = data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        raise LlmError(f"LLM returned malformed response: {r.text[:300]}") from exc
    if not (text or "").strip():
        raise LlmError("LLM returned an empty completion")
    return text.strip()


async def ping(base_url: str, api_key: str = "", timeout: float = 3.0) -> bool:
    """Health probe: /health (llama-server) falling back to /v1/models."""
    if not _local_tcp_open(base_url, timeout=min(0.25, timeout)):
        return False
    base = base_url.rstrip("/")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        for path in ("/health", "/v1/models"):
            try:
                r = await client.get(base + path, headers=headers)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                continue
    return False
