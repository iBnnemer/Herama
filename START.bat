@echo off
title herama launcher
cd /d "%~dp0"

echo.
echo  ◈  herama
echo  ──────────────────────────────
echo.

:: ── Python check ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Download from: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: ── Node.js check ─────────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js is not installed or not in PATH.
    echo  Download from: https://nodejs.org/
    pause
    exit /b 1
)

:: ── Install Python dependencies (skip if already installed) ───────────────────
echo  Installing Python dependencies...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)

:: ── Install Node dependencies ─────────────────────────────────────────────────
cd frontend
if not exist node_modules (
    echo  Installing Node dependencies (first run only, may take a minute)...
    npm install --silent
    if errorlevel 1 (
        echo  [ERROR] Failed to install Node dependencies.
        pause
        exit /b 1
    )
)

:: ── Launch app ────────────────────────────────────────────────────────────────
echo  Launching herama...
echo.
npm run dev

cd ..
