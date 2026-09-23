@echo off
REM Quick Launcher for Project Management Dashboard on Windows
cd /d "%~dp0"

echo ============================================================
echo 🌐 MENJALANKAN DASHBOARD WEB LLMTRADINGV2 (WINDOWS)
echo Buka di browser lokal: http://localhost:8080
echo Buka dari luar/publik : http://103.59.160.228:8080
echo ============================================================

set PORT=8080
set PYTHONPATH=%CD%
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe src\dashboard\server.py
) else (
    python src\dashboard\server.py
)

pause
