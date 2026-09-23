@echo off
REM Quick Launcher for Project Management Dashboard on Windows
cd /d "%~dp0"

echo ============================================================
echo 🌐 MENJALANKAN DASHBOARD WEB LLMTRADINGV2 (WINDOWS)
echo Buka di browser: http://localhost:8000
echo ============================================================

set PYTHONPATH=%CD%
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe src\dashboard\server.py
) else (
    python src\dashboard\server.py
)

pause
