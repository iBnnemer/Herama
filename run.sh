#!/usr/bin/env bash
# Herama single-click launcher — macOS / Linux
# Run:  bash run.sh   OR   chmod +x run.sh && ./run.sh

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# locate Python 3
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.11+ not found. Install it first."
    exit 1
fi

# delegate to the cross-platform Python launcher
exec "$PYTHON" launcher.py "$@"
