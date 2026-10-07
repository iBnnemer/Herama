@echo off
chcp 65001 >nul 2>&1
title herama
cd /d "%~dp0"

echo.
echo  herama - starting...
echo.

:: Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

:: Node check
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)

:: Python deps
echo Installing Python dependencies...
python -m pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] pip install failed. Check requirements.txt
    pause
    exit /b 1
)

:: Node deps
cd frontend
if not exist node_modules (
    echo Installing Node.js dependencies (first run only)...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

:: Launch
echo.
echo Launching herama...
echo.
npm run dev
if errorlevel 1 (
    echo.
    echo [ERROR] App exited with an error. See above for details.
    pause
)

cd ..
