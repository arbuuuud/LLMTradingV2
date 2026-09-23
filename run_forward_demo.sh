#!/usr/bin/env bash
# Quick Launcher for Live Demo Forward Test Daemon
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "❌ Virtualenv .venv tidak ditemukan!"
    exit 1
fi

echo "============================================================"
echo "🚀 MENJALANKAN FORWARD TEST LIVE DEMO DAEMON (WORKFLOW 4)"
echo "Port Bridge: 5555 | Target: 50 Closed Trades"
echo "Tekan Ctrl+C untuk menghentikan daemon."
echo "============================================================"

PYTHONPATH=. .venv/bin/python3 src/workflows/forward_daemon.py
