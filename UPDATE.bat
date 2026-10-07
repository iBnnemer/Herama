@echo off
chcp 65001 >nul 2>&1
title herama - update
cd /d "%~dp0"

echo.
echo  herama - checking for updates
echo  ===============================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git not found. Install from: https://git-scm.com/
    pause
    exit /b 1
)

echo  Fetching latest version from GitHub...
git pull origin main
if errorlevel 1 (
    echo.
    echo [ERROR] git pull failed.
    echo         Make sure you have internet access and the repo is accessible.
    pause
    exit /b 1
)

echo.
echo  Update complete.
echo  Launching herama...
echo.

call START.bat
