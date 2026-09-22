#!/usr/bin/env bash
# LLMTradingV2 Dashboard Launcher
PORT="${1:-8080}"
echo "Starting LLMTradingV2 Project Management Dashboard on http://127.0.0.1:$PORT..."
exec python3 -m src.dashboard.server
