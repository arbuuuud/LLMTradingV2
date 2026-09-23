@echo off
REM Quick Launcher for Live Demo Forward Test Daemon on Windows
cd /d "%~dp0"

echo ============================================================
echo 🚀 MENJALANKAN FORWARD TEST LIVE DEMO DAEMON (WINDOWS)
echo Port Bridge: 5555 ^| Target: 50 Closed Trades
echo Tekan Ctrl+C untuk menghentikan daemon.
echo ============================================================

set PYTHONPATH=%CD%
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe src\bridge\server.py
) else (
    python src\bridge\server.py
)

pause
