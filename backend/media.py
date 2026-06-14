"""Media helpers for real render outputs."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional, Tuple


def find_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def make_thumbnail(video_path: str, thumb_path: str, at: float = 1.0) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg or not os.path.exists(video_path):
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, at):.2f}",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        "scale=360:-2",
        thumb_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.returncode == 0 and os.path.exists(thumb_path)
    except Exception:
        return False


def validate_video_file(video_path: str) -> Tuple[bool, str]:
    """Return true only when ffmpeg can decode at least one video frame."""
    if not os.path.exists(video_path):
        return False, f"file does not exist: {video_path}"
    try:
        if os.path.getsize(video_path) <= 0:
            return False, f"file is empty: {video_path}"
    except OSError as exc:
        return False, str(exc)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False, "ffmpeg/imageio-ffmpeg is unavailable for output validation"

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        video_path,
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return False, str(exc)
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        return False, detail or f"ffmpeg exited with code {res.returncode}"
    return True, ""
