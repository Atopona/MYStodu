"""ComfyUI API client: optional object_info, workflow injection, /prompt
submit, WebSocket progress + preview relay, output download.

Workflow templates live in backend/workflows/*.json (ComfyUI **API format**).
backend/workflows/node_map.json declares which node inputs receive which
logical values, so users can swap in their own exported workflows without
touching code.
"""
import asyncio
import json
import os
import socket
import struct
import uuid
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx
import websockets

from . import config


class ComfyError(Exception):
    pass


def _norm(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith("http"):
        url = "http://" + url
    return url or "http://127.0.0.1:8188"


def _local_tcp_open(base_url: str, timeout: float = 0.25) -> bool:
    """Fast localhost preflight so missing ComfyUI falls back to Mock immediately."""
    parsed = urlparse(_norm(base_url))
    host = parsed.hostname or "127.0.0.1"
    if host not in ("127.0.0.1", "localhost", "::1"):
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ----------------------------------------------------------------- REST


async def ping(base_url: str, timeout: float = 3.0) -> bool:
    if not _local_tcp_open(base_url, timeout=min(0.25, timeout)):
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.get(_norm(base_url) + "/system_stats")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def object_info(base_url: str, timeout: float = 20.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        r = await client.get(_norm(base_url) + "/object_info")
        r.raise_for_status()
        return r.json()


def _choices(info: dict, class_type: str, input_name: str) -> List[str]:
    try:
        v = info[class_type]["input"]["required"][input_name][0]
        if isinstance(v, list):
            return [str(x) for x in v]
    except (KeyError, TypeError, IndexError):
        pass
    try:
        v = info[class_type]["input"]["optional"][input_name][0]
        if isinstance(v, list):
            return [str(x) for x in v]
    except (KeyError, TypeError, IndexError):
        pass
    return []


def extract_model_lists(info: dict) -> dict:
    """Pull model file lists relevant to the LTX pipeline out of /object_info."""
    checkpoints = _choices(info, "CheckpointLoaderSimple", "ckpt_name")
    loras = _choices(info, "LoraLoader", "lora_name") or _choices(
        info, "LoraLoaderModelOnly", "lora_name"
    )
    vaes = _choices(info, "VAELoader", "vae_name")
    clips = _choices(info, "CLIPLoader", "clip_name")
    upscalers = _choices(info, "UpscaleModelLoader", "model_name")
    # LTX-specific loaders from custom node packs, when present:
    text_proj = (
        _choices(info, "LTXVTextProjectionLoader", "proj_name")
        or _choices(info, "LTXAuxModelLoader", "model_name")
        or [c for c in clips if "projection" in c.lower()]
        or vaes  # last-ditch: same models folder dropdowns still let the user pick
    )
    audio_vaes = [v for v in vaes if "audio" in v.lower()] or vaes
    preview_vaes = [v for v in vaes if v.lower().startswith("tae") or "preview" in v.lower()] or vaes
    return {
        "checkpoints": checkpoints,
        "loras": loras,
        "text_encoders": clips,
        "text_projections": text_proj,
        "upscalers": upscalers,
        "audio_vaes": audio_vaes,
        "preview_vaes": preview_vaes,
    }


async def upload_image(base_url: str, path: str, timeout: float = 60.0) -> str:
    """POST /upload/image; returns the server-side filename to use in LoadImage."""
    name = f"cc_{uuid.uuid4().hex[:8]}_{os.path.basename(path)}"
    with open(path, "rb") as fh:
        files = {"image": (name, fh, "application/octet-stream")}
        data = {"overwrite": "true", "type": "input"}
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.post(_norm(base_url) + "/upload/image", files=files, data=data)
    if r.status_code != 200:
        raise ComfyError(f"image upload failed: HTTP {r.status_code} {r.text[:200]}")
    j = r.json()
    sub = j.get("subfolder") or ""
    fn = j.get("name") or name
    return f"{sub}/{fn}" if sub else fn


async def submit(base_url: str, workflow: dict, client_id: str, timeout: float = 30.0) -> str:
    payload = {"prompt": workflow, "client_id": client_id}
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        r = await client.post(_norm(base_url) + "/prompt", json=payload)
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            msg = err.get("message") or str(err)
            node_errors = r.json().get("node_errors") or {}
            if node_errors:
                first = next(iter(node_errors.items()))
                msg += f" | node {first[0]}: {json.dumps(first[1])[:300]}"
        except Exception:  # noqa: BLE001
            msg = r.text[:400]
        raise ComfyError(f"ComfyUI rejected workflow: {msg}")
    return r.json()["prompt_id"]


async def interrupt(base_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            await client.post(_norm(base_url) + "/interrupt")
    except httpx.HTTPError:
        pass


async def get_history(base_url: str, prompt_id: str, timeout: float = 20.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        r = await client.get(_norm(base_url) + f"/history/{prompt_id}")
        r.raise_for_status()
        return r.json().get(prompt_id, {})


async def download_view(
    base_url: str, filename: str, subfolder: str, folder_type: str, dest: str
) -> bool:
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    async with httpx.AsyncClient(timeout=600.0, trust_env=False) as client:
        r = await client.get(_norm(base_url) + "/view", params=params)
        if r.status_code != 200:
            return False
        with open(dest, "wb") as fh:
            fh.write(r.content)
    return True


def pick_video_output(history: dict) -> Optional[dict]:
    """Find the most video-looking output entry in a history record."""
    outputs = history.get("outputs", {}) or {}
    best: Optional[dict] = None
    for _node, out in outputs.items():
        for key in ("videos", "gifs", "video", "files"):
            for ent in out.get(key, []) or []:
                fn = ent.get("filename", "")
                if fn.lower().endswith((".mp4", ".webm", ".mov", ".mkv", ".gif")):
                    return ent
                best = best or ent
        for ent in out.get("images", []) or []:
            fn = ent.get("filename", "")
            if fn.lower().endswith((".mp4", ".webm")):
                return ent
            best = best or ent
    return best


# ---------------------------------------------------------- workflow build


def load_node_map() -> dict:
    path = os.path.join(config.WORKFLOW_DIR, "node_map.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_template(name: str) -> dict:
    path = os.path.join(config.WORKFLOW_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _set_input(wf: dict, node_id: str, input_name: str, value: Any, warnings: List[str]) -> None:
    node = wf.get(str(node_id))
    if node is None:
        warnings.append(f"node {node_id} not in template (skipped {input_name})")
        return
    node.setdefault("inputs", {})[input_name] = value


def inject(
    wf: dict,
    mapping: dict,
    values: Dict[str, Any],
    warnings: List[str],
) -> None:
    """Apply node_map 'inputs' bindings. Binding = {node,input} or list of them."""
    bindings = mapping.get("inputs", {})
    for key, value in values.items():
        if value is None:
            continue
        bind = bindings.get(key)
        if not bind:
            continue
        if isinstance(bind, dict):
            bind = [bind]
        for b in bind:
            _set_input(wf, b["node"], b["input"], value, warnings)


def insert_lora_chain(
    wf: dict,
    mapping: dict,
    loras: List[dict],
    warnings: List[str],
) -> int:
    """Generic LoRA insertion: splice LoraLoaderModelOnly nodes into MODEL edges.

    node_map 'lora_chain' is one chain or a list of chains:
    {"from": ["<node>", <output_index>], "consumers": [{"node": "...", "input": "model"}]}
    (one chain per sampling pass keeps user LoRAs active in both passes).
    """
    chains = mapping.get("lora_chain")
    active = [l for l in loras if l.get("enabled") and l.get("name")]
    if not chains or not active:
        return 0
    if isinstance(chains, dict):
        chains = [chains]
    for ci, chain in enumerate(chains):
        src = list(chain.get("from", []))
        if len(src) != 2:
            warnings.append(f"lora_chain[{ci}].from malformed — skipped")
            continue
        prev = [str(src[0]), int(src[1])]
        for i, lora in enumerate(active):
            nid = f"cc_lora_{ci+1}_{i+1}"
            wf[nid] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": prev,
                    "lora_name": lora["name"],
                    "strength_model": float(lora.get("strength", 1.0)),
                },
                "_meta": {"title": f"CC LoRA p{ci+1}.{i+1}"},
            }
            prev = [nid, 0]
        for cons in chain.get("consumers", []):
            _set_input(wf, cons["node"], cons["input"], prev, warnings)
    return len(active)


def apply_decode_tile(wf: dict, mapping: dict, decode_tile: int, warnings: List[str]) -> None:
    """decode_tile > 0 swaps the mapped decode node to VAEDecodeTiled (OOM rescue)."""
    node_id = str(mapping.get("decode_node", "") or "")
    if not node_id:
        return
    node = wf.get(node_id)
    if node is None:
        warnings.append(f"decode_node {node_id} not in template")
        return
    if decode_tile and int(decode_tile) > 0:
        node["class_type"] = "VAEDecodeTiled"
        node.setdefault("inputs", {})["tile_size"] = max(64, int(decode_tile))
        node["inputs"].setdefault("overlap", 64)
        node["inputs"].setdefault("temporal_size", 64)
        node["inputs"].setdefault("temporal_overlap", 8)


def build_workflow(
    mode: str,
    values: Dict[str, Any],
    loras: List[dict],
) -> tuple:
    """Returns (workflow_dict, mapping, warnings)."""
    node_map = load_node_map()
    mapping = node_map.get(mode)
    if not mapping:
        raise ComfyError(f"node_map.json has no '{mode}' section")
    wf = load_template(mapping["template"])
    warnings: List[str] = []
    inject(wf, mapping, values, warnings)
    insert_lora_chain(wf, mapping, loras, warnings)
    apply_decode_tile(wf, mapping, int(values.get("decode_tile") or 0), warnings)
    return wf, mapping, warnings


# ------------------------------------------------------------- WS listen


async def listen(
    base_url: str,
    client_id: str,
    prompt_id: str,
    *,
    on_progress: Callable[[str, int, int], None],
    on_preview: Callable[[bytes], None],
    on_node: Callable[[Optional[str]], None],
    pass_nodes: Dict[str, List[str]],
    cancel: asyncio.Event,
    timeout: float = 3600.0,
) -> None:
    """Listen to ComfyUI's WS until this prompt finishes executing."""
    ws_url = _norm(base_url).replace("http", "ws", 1) + f"/ws?clientId={client_id}"
    pass1 = set(map(str, pass_nodes.get("pass1", [])))
    pass2 = set(map(str, pass_nodes.get("pass2", [])))
    current_node: Optional[str] = None

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=10) as ws:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if cancel.is_set():
                await interrupt(base_url)
                raise ComfyError("cancelled")
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise ComfyError("render timed out")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                continue

            if isinstance(msg, (bytes, bytearray)):
                if len(msg) > 8:
                    etype, _fmt = struct.unpack(">II", msg[:8])
                    if etype == 1:  # PREVIEW_IMAGE
                        on_preview(bytes(msg[8:]))
                continue

            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            mtype, d = data.get("type"), data.get("data", {})
            if d.get("prompt_id") not in (None, prompt_id):
                continue
            if mtype == "executing":
                node = d.get("node")
                current_node = str(node) if node is not None else None
                on_node(current_node)
                if node is None and d.get("prompt_id") == prompt_id:
                    return  # finished
            elif mtype == "progress":
                v, m = int(d.get("value", 0)), int(d.get("max", 1))
                node = str(d.get("node") or current_node or "")
                phase = "pass2" if node in pass2 else ("pass1" if node in pass1 else "pass1")
                if not pass1 and not pass2:
                    phase = "pass1"
                on_progress(phase, v, m)
            elif mtype == "execution_error":
                raise ComfyError(
                    f"node {d.get('node_id')} ({d.get('node_type')}): {d.get('exception_message', 'execution error')}"
                )
            elif mtype == "execution_interrupted":
                raise ComfyError("interrupted on ComfyUI side")
