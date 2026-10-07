#!/usr/bin/env bash
# Herama single-click launcher — macOS / Linux
# Starts the FastAPI backend in the background, then opens the GUI.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- locate Python 3 ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info.major)")
        if [ "$ver" = "3" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3 not found. Install Python 3.11+ first."
    exit 1
fi

# --- install / upgrade core dependencies silently ---
echo "[Herama] Checking dependencies..."
"$PYTHON" -m pip install --upgrade --quiet customtkinter fastapi uvicorn requests psutil huggingface_hub 2>/dev/null || true

# --- start FastAPI backend in background ---
echo "[Herama] Starting backend server..."
"$PYTHON" -m app.main &
BACKEND_PID=$!

# trap: kill backend when GUI exits
cleanup() {
    echo "[Herama] Shutting down backend (PID $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# wait for backend to be ready (up to 10 s)
echo "[Herama] Waiting for backend..."
for i in $(seq 1 10); do
    if curl -sf http://127.0.0.1:11434/health &>/dev/null; then
        echo "[Herama] Backend ready."
        break
    fi
    sleep 1
done

# --- launch GUI (foreground) ---
echo "[Herama] Launching GUI..."
"$PYTHON" -m app.gui_ui
