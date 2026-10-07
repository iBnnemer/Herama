#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo ""
echo " ◈  herama"
echo " ──────────────────────────────"
echo ""

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo " [ERROR] Python 3 is not installed."
    echo " Install with: sudo apt install python3 python3-pip  (Linux)"
    echo "           or: brew install python  (macOS)"
    exit 1
fi

PY=$(command -v python3 || command -v python)

# ── Node check ─────────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo " [ERROR] Node.js is not installed."
    echo " Install from: https://nodejs.org/"
    exit 1
fi

# ── Python deps ────────────────────────────────────────────────────────────────
echo " Installing Python dependencies..."
$PY -m pip install -r requirements.txt -q --disable-pip-version-check

# ── Node deps ──────────────────────────────────────────────────────────────────
cd frontend
if [ ! -d node_modules ]; then
    echo " Installing Node dependencies (first run only)..."
    npm install --silent
fi

# ── Launch ─────────────────────────────────────────────────────────────────────
echo " Launching herama..."
echo ""
npm run dev
