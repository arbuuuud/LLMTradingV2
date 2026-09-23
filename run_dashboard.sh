#!/usr/bin/env bash
# LLMTradingV2 Dashboard Launcher
PORT="${1:-8080}"
echo "Starting LLMTradingV2 Project Management Dashboard on http://127.0.0.1:$PORT..."

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
exec "$PYTHON_EXEC" -m src.dashboard.server

