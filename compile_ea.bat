@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM One-Click MetaEditor EA Compiler for LLMTradingV2
REM Compiles bridge\mt5\LLMTradingBridge.mq5 via CLI
REM ============================================================
cd /d "%~dp0"

echo ============================================================
echo 🔨 COMPILING LLMTradingBridge.mq5 VIA CLI (WINDOWS)
echo Source: %CD%\bridge\mt5\LLMTradingBridge.mq5
echo ============================================================

set "SOURCE_FILE=%CD%\bridge\mt5\LLMTradingBridge.mq5"
set "LOG_FILE=%CD%\bridge\mt5\compile.log"
set "TARGET_EX5=%CD%\bridge\mt5\LLMTradingBridge.ex5"
set "EDITOR_EXE="

REM 1. Periksa argumen command line jika diberikan
if not "%~1"=="" (
    if exist "%~1" (
        set "EDITOR_EXE=%~1"
        goto :FOUND_EDITOR
    )
)

REM 2. Cari di lokasi standar Program Files
for /d %%D in (
    "C:\Program Files\MetaTrader 5"
    "C:\Program Files\PU Prime MetaTrader 5"
    "C:\Program Files\ICMarkets MetaTrader 5"
    "C:\Program Files\XM Global MT5"
    "C:\Program Files\Exness MetaTrader 5"
    "C:\Program Files\FTMO MetaTrader 5"
    "C:\Program Files\Pepperstone MetaTrader 5"
    "C:\Program Files (x86)\MetaTrader 5"
) do (
    if exist "%%~fD\metaeditor64.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor64.exe"
        goto :FOUND_EDITOR
    )
    if exist "%%~fD\metaeditor.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor.exe"
        goto :FOUND_EDITOR
    )
)

REM 3. Cari dengan wildcard di Program Files jika belum ketemu
for /d %%D in ("C:\Program Files\*MetaTrader*" "C:\Program Files (x86)\*MetaTrader*" "C:\Program Files\*MT5*") do (
    if exist "%%~fD\metaeditor64.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor64.exe"
        goto :FOUND_EDITOR
    )
    if exist "%%~fD\metaeditor.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor.exe"
        goto :FOUND_EDITOR
    )
)

:FOUND_EDITOR
if "%EDITOR_EXE%"=="" (
    echo [ERROR] metaeditor64.exe tidak ditemukan di folder Program Files standar.
    echo.
    echo Silakan jalankan script ini dengan menyebutkan path MetaEditor, contoh:
    echo compile_ea.bat "C:\Program Files\NamaBroker MT5\metaeditor64.exe"
    echo.
    pause
    exit /b 1
)

echo [OK] Menggunakan MetaEditor: "%EDITOR_EXE%"

REM Cari include directory dari terminal Roaming jika ada
set "INC_ARG="
set "TERMINAL_ROOT=%APPDATA%\MetaQuotes\Terminal"
if exist "%TERMINAL_ROOT%" (
    for /d %%D in ("%TERMINAL_ROOT%\*") do (
        if exist "%%D\MQL5\Include\Trade\Trade.mqh" (
            set "INC_ARG=/inc:\"%%D\MQL5\""
            echo [OK] Ditemukan Standard MQL5 Include: "%%D\MQL5"
            goto :START_COMPILE
        )
    )
)

:START_COMPILE
REM Bersihkan log dan binary lama sebelum compile
if exist "%LOG_FILE%" del "%LOG_FILE%" >nul 2>&1
if exist "%TARGET_EX5%" del "%TARGET_EX5%" >nul 2>&1

echo.
echo Sedang meng-compile... Mohon tunggu beberapa detik...
if not "%INC_ARG%"=="" (
    "%EDITOR_EXE%" /compile:"%SOURCE_FILE%" /log:"%LOG_FILE%" %INC_ARG%
) else (
    "%EDITOR_EXE%" /compile:"%SOURCE_FILE%" /log:"%LOG_FILE%"
)

REM Tunggu beberapa detik agar compiler selesai menulis file
timeout /t 3 /nobreak >nul 2>&1

echo.
echo ============================================================
echo 📋 HASIL COMPILE:
echo ============================================================
if exist "%LOG_FILE%" (
    type "%LOG_FILE%"
) else (
    echo [PERINGATAN] File log compile tidak ditemukan.
)

if exist "%TARGET_EX5%" (
    echo.
    echo ============================================================
    echo ✅ SUKSES! File binary ter-generate:
    echo    %TARGET_EX5%
    echo.
    echo Karena semua instance MT5 terhubung via subfolder junction,
    echo file baru ini otomatis terdistribusi ke seluruh terminal!
    echo.
    echo 💡 LANGKAH TERAKHIR DI MT5:
    echo 1. Di setiap layar MT5, ganti timeframe chart (M1 -^> M5 -^> M1)
    echo    agar terminal me-reload binary baru dari memori RAM.
    echo 2. Periksa baris '🔨 Unique Build ID' di pojok kiri atas chart.
    echo    Pastikan jam compile di semua terminal sudah sama persis!
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo ❌ GAGAL: File LLMTradingBridge.ex5 tidak berhasil dibuat.
    echo Silakan periksa pesan error di atas atau buka via MetaEditor GUI.
    echo ============================================================
)

pause
