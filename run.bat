@echo off
REM Herama single-click launcher — Windows
REM Double-click this file to start the full platform (backend + GUI).

setlocal
cd /d "%~dp0"

REM --- locate Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 not found in PATH.
    echo Install Python 3.11+ from https://python.org and add it to PATH.
    pause
    exit /b 1
)

REM --- delegate everything to the cross-platform Python launcher ---
REM   launcher.py handles: OS detection, dep upgrade, backend spawn, GUI open
python launcher.py

endlocal
