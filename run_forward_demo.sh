#!/usr/bin/env bash
# Quick Launcher for Live Demo Forward Test Daemon & MT5 Bridge
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python3" ]; then
    PYTHON_EXEC=".venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="python3"
else
    PYTHON_EXEC="python"
fi

export PYTHONPATH="$SCRIPT_DIR"
echo "============================================================"
echo "🚀 MENJALANKAN MT5 LIVE BRIDGE CORE & RADAR STREAMER"
echo "Port Bridge: 5555 | Protocol: Institutional Live Stream"
echo "Tekan Ctrl+C untuk menghentikan daemon."
echo "============================================================"

exec "$PYTHON_EXEC" src/bridge/server.py
