#!/usr/bin/env bash
#
# Local development startup for parent-sec-chat.
#
# Starts, in one terminal:
#   * backend  - backend/local_server.py in --memory mode (no AWS needed)
#   * web      - Vite dev server for the parent web app (proxies /api to backend)
#   * desktop  - (optional, --desktop) the child GTK client, auto-registered
#                against the local backend via desktop/dev.sh
#
# Usage:
#   ./dev.sh                 backend + web
#   ./dev.sh --desktop       backend + web + desktop client
#   ./dev.sh --desktop --clean   also wipe the desktop client's dev config
#   ./dev.sh --no-web        backend only (plus desktop if requested)
#   ./dev.sh --aws           backend uses real DynamoDB/S3 instead of memory
#
# Environment overrides:
#   BACKEND_PORT (default 8080)   WEB_PORT (default 3000)
#
# Ctrl+C stops everything. Per-service logs are written to .dev-logs/.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
WEB_DIR="$ROOT_DIR/web"
DESKTOP_DIR="$ROOT_DIR/desktop"
LOG_DIR="$ROOT_DIR/.dev-logs"

BACKEND_PORT="${BACKEND_PORT:-8080}"
WEB_PORT="${WEB_PORT:-3000}"
BACKEND_URL="http://localhost:$BACKEND_PORT"

START_WEB=1
START_DESKTOP=0
CLEAN_DESKTOP=0
MEMORY_FLAG="--memory"

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "$arg" in
        --desktop)  START_DESKTOP=1 ;;
        --clean)    CLEAN_DESKTOP=1 ;;
        --no-web)   START_WEB=0 ;;
        --aws)      MEMORY_FLAG="" ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
if [[ -t 1 ]]; then
    C_BACKEND=$'\033[36m'; C_WEB=$'\033[35m'; C_DESKTOP=$'\033[33m'
    C_INFO=$'\033[32m'; C_ERR=$'\033[31m'; C_RESET=$'\033[0m'
else
    C_BACKEND=""; C_WEB=""; C_DESKTOP=""; C_INFO=""; C_ERR=""; C_RESET=""
fi

info() { echo "${C_INFO}[dev]${C_RESET} $*"; }
err()  { echo "${C_ERR}[dev]${C_RESET} $*" >&2; }

# Prefix each line of a service's output with a coloured label and tee to a log.
tag() {
    local label="$1" color="$2" logfile="$3"
    while IFS= read -r line; do
        printf '%s[%s]%s %s\n' "$color" "$label" "$C_RESET" "$line"
        printf '%s\n' "$line" >> "$logfile"
    done
}

# --------------------------------------------------------------------------
# Prerequisites
# --------------------------------------------------------------------------
need() {
    command -v "$1" >/dev/null 2>&1 || { err "Missing required command: $1"; exit 1; }
}

need python3
need pgrep
if [[ $START_WEB -eq 1 ]]; then
    need node
    need npm
fi
if [[ $START_DESKTOP -eq 1 ]]; then
    if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' >/dev/null 2>&1; then
        err "Desktop client needs PyGObject/GTK 3. Install with:"
        err "  sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-notify-0.7"
        exit 1
    fi
    if ! python3 -c 'import requests, PIL' >/dev/null 2>&1; then
        err "Desktop client needs the packages in desktop/requirements.txt:"
        err "  pip install -r desktop/requirements.txt"
        exit 1
    fi
fi
if [[ -z "$MEMORY_FLAG" ]]; then
    if ! python3 -c 'import boto3' >/dev/null 2>&1; then
        err "--aws mode needs a working boto3 (pip install -r backend/requirements.txt)."
        exit 1
    fi
fi

port_in_use() {
    python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
    sys.exit(0)   # something is listening
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

if port_in_use "$BACKEND_PORT"; then
    err "Port $BACKEND_PORT is already in use. Stop the other process or set BACKEND_PORT."
    exit 1
fi
if [[ $START_WEB -eq 1 ]] && port_in_use "$WEB_PORT"; then
    err "Port $WEB_PORT is already in use. Stop the other process or set WEB_PORT."
    exit 1
fi

# --------------------------------------------------------------------------
# Process management
# --------------------------------------------------------------------------
# Each service runs as "cmd | tag" in the background, so $! would only be the
# log tagger. Instead we kill the whole process tree under this script.
kill_tree() {
    local sig="$1" pid="$2" kid
    for kid in $(pgrep -P "$pid" 2>/dev/null || true); do
        kill_tree "$sig" "$kid"
    done
    kill "-$sig" "$pid" 2>/dev/null || true
}

cleanup() {
    trap - INT TERM EXIT
    echo
    info "Shutting down..."
    local kid
    for kid in $(pgrep -P $$ 2>/dev/null || true); do
        kill_tree TERM "$kid"
    done
    sleep 0.5
    for kid in $(pgrep -P $$ 2>/dev/null || true); do
        kill_tree KILL "$kid"
    done
    wait 2>/dev/null || true
    info "Stopped. Logs are in $LOG_DIR"
    exit 0
}
trap cleanup INT TERM EXIT

mkdir -p "$LOG_DIR"

wait_for_backend() {
    local tries=0
    until port_in_use "$BACKEND_PORT"; do
        tries=$((tries + 1))
        if [[ $tries -ge 40 ]]; then
            err "Backend did not start listening on port $BACKEND_PORT. See $LOG_DIR/backend.log"
            exit 1
        fi
        sleep 0.25
    done
}

# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------
info "Starting backend on $BACKEND_URL (${MEMORY_FLAG:-AWS DynamoDB/S3} mode)"
: > "$LOG_DIR/backend.log"
(
    cd "$BACKEND_DIR"
    # shellcheck disable=SC2086
    exec python3 -u local_server.py --port "$BACKEND_PORT" $MEMORY_FLAG
) 2>&1 | tag backend "$C_BACKEND" "$LOG_DIR/backend.log" &

wait_for_backend
info "Backend is up"

# --------------------------------------------------------------------------
# Web (Vite)
# --------------------------------------------------------------------------
if [[ $START_WEB -eq 1 ]]; then
    if [[ ! -d "$WEB_DIR/node_modules" ]]; then
        info "web/node_modules missing, running npm install..."
        : > "$LOG_DIR/web.log"
        (cd "$WEB_DIR" && npm install) 2>&1 | tag web "$C_WEB" "$LOG_DIR/web.log"
    fi
    if [[ ! -f "$WEB_DIR/.env.local" ]]; then
        info "Creating web/.env.local with local-dev defaults"
        printf 'VITE_LOCAL_DEV=true\nVITE_API_URL=\n' > "$WEB_DIR/.env.local"
    fi
    if [[ "$BACKEND_PORT" != "8080" ]]; then
        err "Note: web/vite.config.ts proxies /api to http://localhost:8080."
        err "      With BACKEND_PORT=$BACKEND_PORT the web app will not reach the backend unless you update that proxy target."
    fi

    info "Starting web dev server on http://localhost:$WEB_PORT"
    : > "$LOG_DIR/web.log"
    (
        cd "$WEB_DIR"
        exec npm run dev -- --port "$WEB_PORT" --strictPort
    ) 2>&1 | tag web "$C_WEB" "$LOG_DIR/web.log" &
fi

# --------------------------------------------------------------------------
# Desktop client
# --------------------------------------------------------------------------
if [[ $START_DESKTOP -eq 1 ]]; then
    DESKTOP_ARGS=("$BACKEND_URL")
    [[ $CLEAN_DESKTOP -eq 1 ]] && DESKTOP_ARGS+=(--clean)
    info "Starting desktop client (config in /tmp/parentchat-dev)"
    : > "$LOG_DIR/desktop.log"
    (
        cd "$DESKTOP_DIR"
        exec ./dev.sh "${DESKTOP_ARGS[@]}"
    ) 2>&1 | tag desktop "$C_DESKTOP" "$LOG_DIR/desktop.log" &
fi

# --------------------------------------------------------------------------
# Banner
# --------------------------------------------------------------------------
echo
info "Everything is running."
info "  Backend API : $BACKEND_URL   (parent auth bypassed, parent id: dev-parent-001)"
if [[ $START_WEB -eq 1 ]]; then
    info "  Parent web  : http://localhost:$WEB_PORT   (any email/password logs in)"
else
    info "  Parent web  : not started (--no-web). Backend also serves web/dist at $BACKEND_URL if built."
fi
if [[ $START_DESKTOP -eq 1 ]]; then
    info "  Child client: running, registered to dev-parent-001 (see the 'desktop' lines above)"
else
    info "  Child client: not started. Re-run with --desktop to launch it."
fi
info "  Logs        : $LOG_DIR/"
info "Press Ctrl+C to stop."
echo

# Wait for any child to exit; then tear down the rest.
wait -n 2>/dev/null || true
err "A service exited. Shutting down the rest."
