#!/usr/bin/env bash
set -euo pipefail

echo ""
echo " ========================================================="
echo "  Video Editor"
echo " ========================================================="
echo ""

# Check Python
if ! command -v python3 >/dev/null 2>&1; then
    echo " [ERROR] python3 not found. Please install Python 3.9+."
    exit 1
fi

# Virtual environment setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ ! -d ".venv" ]; then
    echo " [INFO] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

# Install / update requirements
echo " Checking dependencies..."
pip install -r requirements.txt --quiet

# Check FFmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo ""
    echo " [WARNING] FFmpeg not found in PATH!"
    echo " Install FFmpeg via your package manager:"
    echo "   Ubuntu/Debian: sudo apt update && sudo apt install -y ffmpeg"
    echo "   macOS (Homebrew): brew install ffmpeg"
    echo "   Fedora/RHEL:   sudo dnf install -y ffmpeg"
    echo "   Arch Linux:    sudo pacman -S ffmpeg"
    echo ""
    echo " The app will open, but video encoding and slideshows will be disabled."
    sleep 3
else
    echo " [OK] FFmpeg found."
fi

PORT="${VIDEO_EDITOR_PORT:-5000}"
HOST="${VIDEO_EDITOR_HOST:-127.0.0.1}"

echo ""
echo " Starting server at: http://${HOST}:${PORT}"
echo " Press Ctrl+C to stop."
echo ""

# Try opening default browser in background
if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2 && xdg-open "http://${HOST}:${PORT}") &
elif command -v open >/dev/null 2>&1; then
    (sleep 2 && open "http://${HOST}:${PORT}") &
fi

exec python3 app.py
