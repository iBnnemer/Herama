"""
Herama cross-platform launcher.

Detects the operating system, starts the FastAPI/llama.cpp backend in a
silent background process, waits until it is ready, then launches the GUI.

Usage:
  python launcher.py            # auto-detect OS
  python launcher.py --no-gui   # backend only (headless / server mode)

OS-specific behaviour
---------------------
Windows  — uses CREATE_NO_WINDOW flag so no console window appears.
macOS    — uses os.setpgrp() to detach backend from the terminal session.
Linux    — same as macOS; also works inside a desktop session or via SSH.
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).resolve().parent
API_BASE    = "http://127.0.0.1:11434"
HEALTH_URL  = f"{API_BASE}/health"
MAX_WAIT_S  = 30    # seconds to wait for the backend to become healthy
POLL_INTERVAL = 0.5

OS = platform.system()   # "Windows" | "Darwin" | "Linux"


# ---------------------------------------------------------------------------
# Dependency bootstrap (runs before anything else)
# ---------------------------------------------------------------------------
def _bootstrap():
    """Ensure core deps are present before importing them."""
    reqs = REPO_ROOT / "requirements.txt"
    if reqs.exists():
        print("[Herama] Checking / upgrading dependencies…")
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--upgrade", "--quiet", "-r", str(reqs)],
            check=False,
        )
    else:
        # minimal set needed to start at all
        for pkg in ["fastapi", "uvicorn", "customtkinter", "requests"]:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg],
                check=False,
            )


# ---------------------------------------------------------------------------
# Backend process spawn
# ---------------------------------------------------------------------------
def _start_backend() -> subprocess.Popen:
    """Start `python -m app.main` as a detached background process."""
    cmd = [sys.executable, "-m", "app.main"]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}

    if OS == "Windows":
        # CREATE_NO_WINDOW (0x08000000) hides the console window entirely
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif OS in ("Darwin", "Linux"):
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # detach from terminal on POSIX
        )
    else:
        # Unknown OS — try generic spawn
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    print(f"[Herama] Backend started (PID {proc.pid}) on {OS}")
    return proc


# ---------------------------------------------------------------------------
# Health poll
# ---------------------------------------------------------------------------
def _wait_for_backend(proc: subprocess.Popen) -> bool:
    """Poll /health until it responds 200 or timeout / process dies."""
    deadline = time.monotonic() + MAX_WAIT_S
    print(f"[Herama] Waiting for backend (up to {MAX_WAIT_S}s)…", end="", flush=True)
    while time.monotonic() < deadline:
        # check if process died unexpectedly
        if proc.poll() is not None:
            print("\n[Herama] Backend process exited early.")
            return False
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as r:
                if r.status == 200:
                    print(" ready.")
                    return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(POLL_INTERVAL)
    print("\n[Herama] Timeout waiting for backend — continuing anyway.")
    return False


# ---------------------------------------------------------------------------
# GUI launch
# ---------------------------------------------------------------------------
def _start_gui():
    print("[Herama] Launching GUI…")
    # Import here so the module is only loaded after deps are bootstrapped
    from app.gui_ui import main as gui_main
    gui_main()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Herama launcher")
    parser.add_argument("--no-gui", action="store_true",
                        help="Start backend only, skip the GUI")
    parser.add_argument("--no-backend", action="store_true",
                        help="Start GUI only (backend already running)")
    args = parser.parse_args()

    if not args.no_backend:
        _bootstrap()
        proc = _start_backend()
        _wait_for_backend(proc)
    else:
        proc = None

    if not args.no_gui:
        _start_gui()

    # Keep the launcher alive so the backend process is not orphaned on
    # platforms that tie child lifetime to parent (rare but possible).
    if proc and proc.poll() is None:
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("\n[Herama] Shutting down backend…")
            proc.terminate()


if __name__ == "__main__":
    main()
