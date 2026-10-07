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
    goto :error
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Python: %%v

:: ---- check Node ----
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo         Install from: https://nodejs.org/
    goto :error
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo  Node:   %%v
echo.

:: ---- Python deps ----
echo [1/3] Installing Python dependencies...
python -m pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed. Run this manually to see the error:
    echo         python -m pip install -r requirements.txt
    goto :error
)
echo  Done.

:: ---- Node deps ----
echo [2/3] Checking Node dependencies...
cd frontend
if not exist node_modules (
    echo       Installing (first run - may take a minute)...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        goto :error
    )
)
echo  Done.

:: ---- Start backend in a separate visible window ----
echo [3/3] Starting backend...
cd ..
start "herama-backend" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 11434 --log-level info"
echo  Backend window opened. Wait for it to show "Application startup complete."
echo.

:: ---- Wait for backend ----
echo  Waiting for backend to be ready...
:wait_loop
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:11434/health >nul 2>&1
if errorlevel 1 goto :wait_loop
echo  Backend is ready!
echo.

:: ---- Launch Electron ----
echo  Launching herama UI...
cd frontend
npm run dev
cd ..
goto :end

:error
echo.
echo  Press any key to exit...
pause >nul
exit /b 1

:end
echo.
echo  Session ended. Press any key to close.
pause >nul
