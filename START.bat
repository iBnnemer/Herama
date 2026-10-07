@echo off
chcp 65001 >nul 2>&1
title herama
cd /d "%~dp0"
set "LOG=%~dp0herama-setup.log"
echo herama setup log > "%LOG%"

echo.
echo  herama launcher
echo  ================
echo  Log file: %LOG%
echo.

python --version >nul 2>&1
if errorlevel 1 goto :no_python
node --version >nul 2>&1
if errorlevel 1 goto :no_node

echo [1/3] Installing Python dependencies...
python -m pip install --upgrade pip --disable-pip-version-check >> "%LOG%" 2>&1
python -m pip install llama-cpp-python --prefer-binary --only-binary=llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 goto :llama_fail
:after_llama
python -m pip install fastapi "uvicorn[standard]" psutil --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 goto :fail
echo       done.

echo [2/3] Installing Node packages...
cd frontend
if not exist node_modules call npm install >> "%LOG%" 2>&1
if errorlevel 1 goto :fail_npm
if exist node_modules\electron\dist\electron.exe goto :node_ready
echo       Downloading Electron runtime, please wait...
set "ELECTRON_SKIP_BINARY_DOWNLOAD="
call node node_modules\electron\install.js
if exist node_modules\electron\dist\electron.exe goto :node_ready
echo       Retrying with a clean Electron install...
rmdir /s /q node_modules\electron
call npm install electron@32 --foreground-scripts
if not exist node_modules\electron\dist\electron.exe goto :fail_electron
:node_ready
cd ..
echo       done.

echo [3/3] Starting backend and UI...
start "herama-backend" cmd /k "cd /d %~dp0 && python -m uvicorn app.main:app --host 127.0.0.1 --port 11434 --log-level info"
timeout /t 4 /nobreak >nul
cd frontend
call npm run dev
cd ..
echo.
echo  Session ended.
pause
exit /b 0

:llama_fail
echo       No pre-built llama-cpp-python wheel found for this Python version.
echo       The app UI will still open, but model loading needs llama-cpp-python.
echo       See the log for details.
goto :after_llama

:no_python
echo [ERROR] Python not found. Install Python 3.10 to 3.12 from https://www.python.org/downloads/
echo         and tick "Add Python to PATH".
pause
exit /b 1

:no_node
echo [ERROR] Node.js not found. Install it from https://nodejs.org/
pause
exit /b 1

:fail_electron
cd ..
echo.
echo [ERROR] Could not download the Electron runtime. Read the messages above.
echo         Common causes: no internet, antivirus or firewall blocking github.com.
pause
exit /b 1

:fail_npm
cd ..
:fail
echo.
echo [ERROR] Setup failed. Last lines of the log:
echo ------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 25 '%LOG%'"
echo ------------------------------------------
echo Full log: %LOG%
pause
exit /b 1
