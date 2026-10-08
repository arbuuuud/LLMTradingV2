@echo off
REM Quick Launcher for Project Management Dashboard on Windows
cd /d "%~dp0"

REM Nonaktifkan Windows QuickEdit Mode otomatis agar CMD tidak beku saat diklik kursor
reg add HKCU\Console /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1
powershell -NoProfile -Command "$h = [System.IntPtr](Get-Process -Id $PID).MainWindowHandle; $mode = 0; Add-Type -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern IntPtr GetStdHandle(int nStdHandle); [DllImport(\"kernel32.dll\")] public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode); [DllImport(\"kernel32.dll\")] public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);' -Name Native -Namespace Win32; $std = [Win32.Native]::GetStdHandle(-10); [Win32.Native]::GetConsoleMode($std, [ref]$mode); [Win32.Native]::SetConsoleMode($std, $mode -band -bnot 0x0040)" >nul 2>&1

echo ============================================================
echo 🌐 MENJALANKAN DASHBOARD WEB LLMTRADINGV2 (WINDOWS)
echo Buka di browser lokal: http://localhost:8080
echo Buka dari luar/publik : http://103.59.160.228:8080
echo [Anti-Freeze Active] QuickEdit Mode dinonaktifkan otomatis.
echo ============================================================

set PORT=8080
set PYTHONPATH=%CD%
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe src\dashboard\server.py
) else (
    python src\dashboard\server.py
)

pause
