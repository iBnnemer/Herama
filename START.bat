@echo off
chcp 65001 >nul 2>&1
title herama
cd /d "%~dp0"

echo.
echo  herama launcher
echo  ================
echo.

:: ---- check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install from: https://www.python.org/downloads/
    echo         Check "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Python: %%v

:: ---- check Node ----
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo         Install from: https://nodejs.org/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo  Node:   %%v
echo.

:: ---- Python deps ----
echo [1/3] Installing Python dependencies...
echo       (llama-cpp-python uses pre-built wheel - no compiler needed)
echo.

python -m pip install --upgrade pip -q --disable-pip-version-check

:: Install llama-cpp-python from pre-built CPU wheel (no compiler required)
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --disable-pip-version-check
if errorlevel 1 (
    echo [WARNING] Pre-built llama-cpp-python wheel failed, trying default (may take longer)...
    python -m pip install llama-cpp-python --disable-pip-version-check
)

:: Install remaining dependencies
python -m pip install fastapi "uvicorn[standard]" psutil --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies.
    echo.
    pause
    exit /b 1
)
echo  Done.

:: ---- Node deps ----
echo [2/3] Checking Node.js dependencies...
cd frontend
if not exist node_modules (
    echo       First run - installing packages (this may take a minute)...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        echo.
        cd ..
        pause
        exit /b 1
    )
)
echo  Done.

:: ---- Start backend ----
echo [3/3] Starting backend server...
cd ..
start "herama-backend" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 11434 --log-level info"

:: Wait for backend to respond
echo  Waiting for backend...
:wait
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:11434/health >nul 2>&1
if errorlevel 1 goto :wait
echo  Backend ready.
echo.

:: ---- Launch UI ----
echo  Opening herama...
echo.
cd frontend
npm run dev
cd ..

echo.
echo  Session ended.
pause
