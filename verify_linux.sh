#!/usr/bin/env bash
set -euo pipefail

# End-to-end Linux verifier for the real local LTX path.
# It never uses fake rendering. A passing run means the local runtime,
# required model files, FastAPI service, T2V render, and I2V render all worked.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [ -f "$ROOT/data/local_paths.env" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/data/local_paths.env"
fi

VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
HOST="${CC_HOST:-127.0.0.1}"
PORT="${CC_PORT:-7860}"
BASE_URL="${BASE_URL:-http://$HOST:$PORT}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-7200}"
VERIFY_DURATION="${VERIFY_DURATION:-2}"
VERIFY_FPS="${VERIFY_FPS:-8}"
VERIFY_WIDTH="${VERIFY_WIDTH:-896}"
VERIFY_HEIGHT="${VERIFY_HEIGHT:-512}"
SERVER_LOG="$ROOT/.tmp/verify-linux-server.log"
STARTED_PID=""
RUN_T2V=1
RUN_I2V=1
NO_START=0

usage() {
  cat <<'EOF'
Cinematic Console Linux verifier

Usage:
  bash verify_linux.sh [options]

Options:
  --skip-t2v       Do not run the short text-to-video render
  --skip-i2v       Do not run the short image-to-video render
  --skip-render    Only run diagnostics and service readiness checks
  --no-start       Require an already running service at BASE_URL
  --help           Show this help

Environment:
  BASE_URL=http://127.0.0.1:7860
  VERIFY_TIMEOUT=7200
  VERIFY_DURATION=2
  VERIFY_FPS=8
  VERIFY_WIDTH=896
  VERIFY_HEIGHT=512
EOF
}

log() {
  printf '\033[1;32m[verify_linux]\033[0m %s\n' "$*"
}

die() {
  printf '\033[1;31m[verify_linux]\033[0m %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [ -n "${STARTED_PID:-}" ] && kill -0 "$STARTED_PID" >/dev/null 2>&1; then
    log "stopping verifier-started server $STARTED_PID"
    kill "$STARTED_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-t2v)
      RUN_T2V=0
      shift
      ;;
    --skip-i2v)
      RUN_I2V=0
      shift
      ;;
    --skip-render)
      RUN_T2V=0
      RUN_I2V=0
      shift
      ;;
    --no-start)
      NO_START=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[ -x "$PY" ] || die "missing venv python: $PY; run install_linux.sh first"

log "running local diagnostics"
"$PY" -m backend.ltx_diagnose --fail

service_ok() {
  "$PY" - "$BASE_URL" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
with urllib.request.urlopen(base + "/api/status", timeout=3) as r:
    raise SystemExit(0 if r.status == 200 else 1)
PY
}

if service_ok; then
  log "using existing service at $BASE_URL"
elif [ "$NO_START" = "1" ]; then
  die "service is not reachable at $BASE_URL"
else
  mkdir -p "$ROOT/.tmp"
  : > "$SERVER_LOG"
  log "starting service at $BASE_URL"
  CC_HOST="$HOST" CC_PORT="$PORT" CC_NO_BROWSER=1 "$PY" "$ROOT/run.py" >"$SERVER_LOG" 2>&1 &
  STARTED_PID="$!"
  for _ in $(seq 1 90); do
    if service_ok; then
      break
    fi
    if ! kill -0 "$STARTED_PID" >/dev/null 2>&1; then
      sed -n '1,160p' "$SERVER_LOG" >&2 || true
      die "service exited during startup"
    fi
    sleep 1
  done
  service_ok || die "service did not become ready; log: $SERVER_LOG"
fi

log "verifying service and optional real renders"
"$PY" - "$BASE_URL" "$ROOT" "$RUN_T2V" "$RUN_I2V" "$VERIFY_TIMEOUT" "$VERIFY_DURATION" "$VERIFY_FPS" "$VERIFY_WIDTH" "$VERIFY_HEIGHT" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from backend import media

base = sys.argv[1].rstrip("/")
root = Path(sys.argv[2])
run_t2v = sys.argv[3] == "1"
run_i2v = sys.argv[4] == "1"
timeout = float(sys.argv[5])
duration = int(sys.argv[6])
fps = int(sys.argv[7])
width = int(sys.argv[8])
height = int(sys.argv[9])

client = httpx.Client(timeout=60.0)

def fail(msg: str) -> None:
    raise SystemExit(msg)

def get(path: str) -> dict:
    r = client.get(base + path)
    r.raise_for_status()
    return r.json()

def post(path: str, payload: dict) -> dict:
    r = client.post(base + path, json=payload)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        fail(f"{path} failed HTTP {r.status_code}: {detail}")
    return r.json()

status = get("/api/status")
if not status.get("render", {}).get("ready"):
    fail("render is not ready: " + status.get("render", {}).get("detail", "unknown"))

def poll(job_id: str) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        item = get(f"/api/history/{job_id}")
        last = item
        if item.get("status") == "done":
            meta = item.get("meta") or {}
            if meta.get("renderer") != "local-ltx":
                fail(f"job {job_id} did not use local-ltx renderer: {meta}")
            if meta.get("mock"):
                fail(f"job {job_id} is marked as mock output")
            video_url = item.get("video_url") or ""
            if not video_url:
                fail(f"job {job_id} finished without video_url")
            rel = video_url.replace("/files/outputs/", "")
            path = root / "outputs" / rel
            if not path.exists() or path.stat().st_size <= 0:
                fail(f"job {job_id} video file missing or empty: {path}")
            ok, video_error = media.validate_video_file(str(path))
            if not ok:
                fail(f"job {job_id} video is not decodable: {video_error}")
            print(f"[verify_linux] job {job_id} done -> {path} ({path.stat().st_size} bytes)")
            return item
        if item.get("status") == "error":
            fail(f"job {job_id} failed: {item.get('error')}")
        time.sleep(5)
    fail(f"job {job_id} timed out after {timeout}s; last={json.dumps(last, ensure_ascii=False)[:1000]}")

common_params = {
    "duration": duration,
    "fps": fps,
    "frames": 0,
    "width": width,
    "height": height,
}

if run_t2v:
    print("[verify_linux] submitting real T2V smoke render")
    res = post("/api/render", {
        "mode": "t2v",
        "prompt": (
            "A concise cinematic verification clip: a small brushed-metal cube on a black glass table, "
            "soft studio light moving from left to right, subtle camera push in, realistic reflections. "
            "Sounds: quiet room tone and a low soft synth pulse."
        ),
        "params": common_params,
        "pipeline": {},
    })
    poll(res["job_id"])

if run_i2v:
    tmp = root / ".tmp" / "verify-i2v-reference.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (768, 448), (9, 10, 14))
    draw = ImageDraw.Draw(im)
    draw.rectangle((64, 56, 704, 392), outline=(245, 197, 66), width=6)
    draw.line((92, 348, 676, 92), fill=(98, 208, 255), width=8)
    draw.rectangle((116, 112, 244, 240), fill=(255, 93, 93), outline=(245, 245, 245), width=3)
    draw.ellipse((492, 152, 636, 296), fill=(199, 123, 255), outline=(245, 245, 245), width=3)
    draw.text((108, 84), "LTX VERIFY I2V", fill=(245, 245, 245))
    draw.text((108, 268), "REFERENCE CARD", fill=(245, 197, 66))
    im.save(tmp)
    print("[verify_linux] uploading I2V reference image")
    with tmp.open("rb") as fh:
        up = client.post(base + "/api/upload", files={"file": ("verify-i2v-reference.png", fh, "image/png")})
    up.raise_for_status()
    image = up.json()
    print("[verify_linux] submitting real I2V smoke render")
    res = post("/api/render", {
        "mode": "i2v",
        "image_id": image["id"],
        "prompt": (
            "The attached verification card is the exact first frame: black slate background, yellow frame, "
            "cyan diagonal line, red square, purple circle, and the words LTX VERIFY I2V. Keep those visible "
            "while making a subtle camera push-in and a moving studio light sweep across the card. "
            "Sounds: faint electrical hum and soft mechanical movement."
        ),
        "params": common_params,
        "pipeline": {},
    })
    poll(res["job_id"])

print("[verify_linux] verification complete")
PY

log "all requested verification checks passed"
