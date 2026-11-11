@echo off
setlocal enabledelayedexpansion
title Video Editor
color 0A
cls

echo.
echo  =========================================================
echo   Video Editor
echo  =========================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Create and activate virtual environment if not present
if not exist ".venv" (
    echo  [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
)

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Install/verify dependencies
echo  Checking dependencies...
pip install -r requirements.txt --quiet

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [WARNING] FFmpeg not found in PATH!
    echo  Download from: https://ffmpeg.org/download.html
    echo  Windows install: winget install Gyan.FFmpeg
    echo  Add ffmpeg to your system PATH, then restart this script.
    echo.
    echo  The app will still open, but processing will be disabled.
    echo.
    timeout /t 4 >nul
) else (
    echo  [OK] FFmpeg found.
)

:: Port configuration
if "%VIDEO_EDITOR_PORT%"=="" (
    set PORT=5000
) else (
    set PORT=%VIDEO_EDITOR_PORT%
)

echo.
echo  Starting server at: http://127.0.0.1:%PORT%
echo  Press Ctrl+C to stop.
echo.

:: Open browser after 2 seconds
start "" /b cmd /c "timeout /t 2 >nul && start http://127.0.0.1:%PORT%"

:: Run Flask app
python app.py

echo.
echo  Server stopped.
pause
