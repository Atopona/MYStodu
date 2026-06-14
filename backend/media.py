"""Media helpers for real render outputs."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


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
