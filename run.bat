@echo off
REM Herama single-click launcher — Windows
REM Starts the FastAPI backend in the background, then opens the GUI.

setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM --- locate Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)

REM --- install / upgrade core dependencies silently ---
echo [Herama] Checking dependencies...
python -m pip install --upgrade --quiet customtkinter fastapi uvicorn requests psutil huggingface_hub >nul 2>&1

REM --- start FastAPI backend in a minimised background window ---
echo [Herama] Starting backend server...
start "Herama Backend" /min python -m app.main

REM --- wait a moment for the backend to initialise ---
timeout /t 3 /nobreak >nul

REM --- launch GUI (stays in foreground) ---
echo [Herama] Launching GUI...
python -m app.gui_ui

endlocal
