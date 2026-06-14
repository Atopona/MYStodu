"""SQLite persistence: settings + job history. Small traffic, sync sqlite3 + lock."""
import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

from . import config

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at REAL,
                mode TEXT,
                status TEXT,
                phase TEXT,
                prompt TEXT,
                params TEXT,
                video_path TEXT,
                thumb_path TEXT,
                error TEXT,
                meta TEXT
            )"""
        )
        _conn.commit()
    return _conn


# ---------------------------------------------------------------- settings

def get_settings() -> dict:
    with _lock:
        rows = _get().execute("SELECT key, value FROM settings").fetchall()
    stored = {r["key"]: json.loads(r["value"]) for r in rows}
    merged = dict(config.DEFAULT_SETTINGS)
    for k, v in stored.items():
        if k in merged or k in ("ui_state",):
            merged[k] = v
    return merged


def update_settings(patch: dict) -> dict:
    with _lock:
        c = _get()
        for k, v in patch.items():
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
        c.commit()
    return get_settings()


def get_setting(key: str, default: Any = None) -> Any:
    with _lock:
        row = _get().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return config.DEFAULT_SETTINGS.get(key, default)
    return json.loads(row["value"])


def set_setting(key: str, value: Any) -> None:
    update_settings({key: value})


# ---------------------------------------------------------------- jobs

def create_job(mode: str, prompt: str, params: dict, meta: dict) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        c = _get()
        c.execute(
            "INSERT INTO jobs (id, created_at, mode, status, phase, prompt, params, "
            "video_path, thumb_path, error, meta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                time.time(),
                mode,
                "queued",
                "queued",
                prompt,
                json.dumps(params, ensure_ascii=False),
                "",
                "",
                "",
                json.dumps(meta, ensure_ascii=False),
            ),
        )
        c.commit()
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols, vals = [], []
    for k, v in fields.items():
        if k in ("params", "meta") and isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        cols.append(f"{k}=?")
        vals.append(v)
    vals.append(job_id)
    with _lock:
        c = _get()
        c.execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id=?", vals)
        c.commit()


def _row_to_job(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "mode": r["mode"],
        "status": r["status"],
        "phase": r["phase"],
        "prompt": r["prompt"],
        "params": json.loads(r["params"] or "{}"),
        "video_path": r["video_path"],
        "thumb_path": r["thumb_path"],
        "error": r["error"],
        "meta": json.loads(r["meta"] or "{}"),
    }


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        r = _get().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _row_to_job(r) if r else None


def list_jobs(limit: int = 60) -> list:
    with _lock:
        rows = _get().execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def delete_job(job_id: str) -> None:
    with _lock:
        c = _get()
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        c.commit()
