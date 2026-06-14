#!/usr/bin/env bash
set -euo pipefail

# Cinematic Console Linux start script.
#
# Default:
#   bash start_linux.sh
#
# With a free Cloudflare Quick Tunnel:
#   bash start_linux.sh --tunnel
#   CC_TUNNEL=cloudflare bash start_linux.sh
#
# Quick Tunnel does not need a Cloudflare account. It creates a temporary
# https://*.trycloudflare.com URL for the local WebUI.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$ROOT/.venv}"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

HOST="${CC_HOST:-127.0.0.1}"
PORT="${CC_PORT:-7860}"
NO_BROWSER="${CC_NO_BROWSER:-0}"
TUNNEL_MODE="${CC_TUNNEL:-0}"
TUNNEL_TARGET="${CC_TUNNEL_TARGET:-http://127.0.0.1:$PORT}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-}"
CLOUDFLARED_DIR="$ROOT/tools/cloudflared"
CLOUDFLARED_LOG="$ROOT/.tmp/cloudflared.log"
SERVER_LOG="$ROOT/.tmp/server-linux.log"
TUNNEL_PID=""

usage() {
  cat <<'EOF'
Cinematic Console Linux starter

Usage:
  bash start_linux.sh [options]

Options:
  --host HOST        Bind host, default 127.0.0.1
  --port PORT        Bind port, default 7860
  --tunnel           Start a free Cloudflare Quick Tunnel
  --no-tunnel        Disable tunnel even if CC_TUNNEL is set
  --no-browser       Do not open a local browser
  --help             Show this help

Environment:
  CC_HOST=127.0.0.1
  CC_PORT=7860
  CC_NO_BROWSER=1
  CC_TUNNEL=cloudflare
  CC_TUNNEL_TARGET=http://127.0.0.1:7860
  CLOUDFLARED_BIN=/path/to/cloudflared

Examples:
  bash start_linux.sh
  bash start_linux.sh --tunnel
  CC_PORT=9000 bash start_linux.sh --tunnel
EOF
}

log() {
  printf '\033[1;32m[start_linux]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[start_linux]\033[0m %s\n' "$*"
}

die() {
  printf '\033[1;31m[start_linux]\033[0m %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [ -n "${TUNNEL_PID:-}" ] && kill -0 "$TUNNEL_PID" >/dev/null 2>&1; then
    log "stopping Cloudflare tunnel"
    kill "$TUNNEL_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      [ $# -ge 2 ] || die "--host needs a value"
      HOST="$2"
      shift 2
      ;;
    --port)
      [ $# -ge 2 ] || die "--port needs a value"
      PORT="$2"
      TUNNEL_TARGET="${CC_TUNNEL_TARGET:-http://127.0.0.1:$PORT}"
      shift 2
      ;;
    --tunnel)
      TUNNEL_MODE="cloudflare"
      shift
      ;;
    --no-tunnel)
      TUNNEL_MODE="0"
      shift
      ;;
    --no-browser)
      NO_BROWSER="1"
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

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

ensure_python_env() {
  need_cmd python3
  if [ ! -x "$PY" ]; then
    log "creating Python venv at $VENV"
    python3 -m venv "$VENV"
  fi

  if ! "$PY" -c "import fastapi, uvicorn, httpx, PIL, websockets" >/dev/null 2>&1; then
    log "installing backend dependencies"
    "$PIP" install --upgrade pip wheel setuptools
    "$PIP" install -r "$ROOT/requirements.txt"
  fi
}

ensure_frontend() {
  if [ -f "$ROOT/frontend/dist/index.html" ]; then
    return
  fi
  if ! command -v npm >/dev/null 2>&1; then
    warn "frontend/dist missing and npm not found; UI will be unavailable until built"
    return
  fi
  log "building frontend"
  (
    cd "$ROOT/frontend"
    if [ ! -d node_modules ]; then
      npm install --no-fund --no-audit
    fi
    npm run build
  )
}

cloudflared_arch() {
  case "$(uname -m)" in
    x86_64|amd64)
      printf 'amd64'
      ;;
    aarch64|arm64)
      printf 'arm64'
      ;;
    armv7l|armv6l)
      printf 'arm'
      ;;
    *)
      die "unsupported CPU architecture for cloudflared: $(uname -m)"
      ;;
  esac
}

ensure_cloudflared() {
  if [ -n "$CLOUDFLARED_BIN" ]; then
    [ -x "$CLOUDFLARED_BIN" ] || die "CLOUDFLARED_BIN is not executable: $CLOUDFLARED_BIN"
    printf '%s\n' "$CLOUDFLARED_BIN"
    return
  fi

  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return
  fi

  need_cmd curl
  mkdir -p "$CLOUDFLARED_DIR"
  local arch
  arch="$(cloudflared_arch)"
  local bin="$CLOUDFLARED_DIR/cloudflared"
  local url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$arch"

  if [ ! -x "$bin" ]; then
    log "downloading cloudflared ($arch)" >&2
    curl -L --fail --retry 3 --connect-timeout 15 -o "$bin" "$url"
    chmod +x "$bin"
  fi
  printf '%s\n' "$bin"
}

start_cloudflare_tunnel() {
  mkdir -p "$ROOT/.tmp"
  : > "$CLOUDFLARED_LOG"
  local cf
  cf="$(ensure_cloudflared)"

  log "starting Cloudflare Quick Tunnel -> $TUNNEL_TARGET"
  "$cf" tunnel --no-autoupdate --url "$TUNNEL_TARGET" >"$CLOUDFLARED_LOG" 2>&1 &
  TUNNEL_PID="$!"

  local public_url=""
  for _ in $(seq 1 60); do
    if ! kill -0 "$TUNNEL_PID" >/dev/null 2>&1; then
      warn "cloudflared exited early; log follows"
      sed -n '1,120p' "$CLOUDFLARED_LOG" >&2 || true
      die "Cloudflare tunnel failed"
    fi
    public_url="$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$CLOUDFLARED_LOG" | tail -n 1 || true)"
    if [ -n "$public_url" ]; then
      printf '\n'
      log "Cloudflare tunnel ready:"
      printf '  %s\n\n' "$public_url"
      return
    fi
    sleep 1
  done

  warn "tunnel started, but public URL was not detected yet"
  warn "cloudflared log: $CLOUDFLARED_LOG"
}

ensure_python_env
ensure_frontend

export CC_HOST="$HOST"
export CC_PORT="$PORT"
export CC_NO_BROWSER="$NO_BROWSER"

mkdir -p "$ROOT/.tmp"
log "local WebUI: http://$HOST:$PORT"

if [ "$TUNNEL_MODE" = "cloudflare" ] || [ "$TUNNEL_MODE" = "1" ] || [ "$TUNNEL_MODE" = "true" ]; then
  export CC_NO_BROWSER="1"
  start_cloudflare_tunnel
fi

log "starting FastAPI backend"
log "server log: $SERVER_LOG"
"$PY" "$ROOT/run.py" 2>&1 | tee "$SERVER_LOG"
