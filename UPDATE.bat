@echo off
chcp 65001 >nul 2>&1
title herama - update
cd /d "%~dp0"

echo.
echo  herama - checking for updates
echo  ===============================
echo.

git --version >nul 2>&1
if errorlevel 1 goto :no_git

echo  Fetching latest version from GitHub...
git fetch origin main
if errorlevel 1 goto :fail
git reset --hard origin/main
if errorlevel 1 goto :fail

echo.
echo  Update complete. Launching herama...
start "" cmd /c "%~dp0START.bat"
exit /b 0

:no_git
echo [ERROR] git not found. Install from https://git-scm.com/
pause
exit /b 1

:fail
echo.
echo [ERROR] Update failed. Check your internet connection.
pause
exit /b 1
