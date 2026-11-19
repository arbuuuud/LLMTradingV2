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

REM 2. Cari dari proses MT5 (terminal64.exe) yang SEDANG BERJALAN di RAM!
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-Process -Name '*terminal*' -ErrorAction SilentlyContinue | ForEach-Object { $_.Path } | Select-Object -Unique"`) do (
    if exist "%%~dpPmetaeditor64.exe" (
        set "EDITOR_EXE=%%~dpPmetaeditor64.exe"
        echo [OK] Ditemukan dari proses MT5 yang aktif: "!EDITOR_EXE!"
        goto :FOUND_EDITOR
    )
    if exist "%%~dpPMetaEditor64.exe" (
        set "EDITOR_EXE=%%~dpPMetaEditor64.exe"
        echo [OK] Ditemukan dari proses MT5 yang aktif: "!EDITOR_EXE!"
        goto :FOUND_EDITOR
    )
    if exist "%%~dpPmetaeditor.exe" (
        set "EDITOR_EXE=%%~dpPmetaeditor.exe"
        echo [OK] Ditemukan dari proses MT5 yang aktif: "!EDITOR_EXE!"
        goto :FOUND_EDITOR
    )
)

REM 3. Cari otomatis via origin.txt pada semua instance MetaQuotes Terminal
set "TERMINAL_ROOT=%APPDATA%\MetaQuotes\Terminal"
if exist "%TERMINAL_ROOT%" (
    for /d %%D in ("%TERMINAL_ROOT%\*") do (
        if exist "%%D\origin.txt" (
            set /p ORIGIN_DIR=<"%%D\origin.txt"
            if defined ORIGIN_DIR (
                if "!ORIGIN_DIR:~-1!"=="\" set "ORIGIN_DIR=!ORIGIN_DIR:~0,-1!"
                if exist "!ORIGIN_DIR!\metaeditor64.exe" (
                    set "EDITOR_EXE=!ORIGIN_DIR!\metaeditor64.exe"
                    goto :FOUND_EDITOR
                )
                if exist "!ORIGIN_DIR!\metaeditor.exe" (
                    set "EDITOR_EXE=!ORIGIN_DIR!\metaeditor.exe"
                    goto :FOUND_EDITOR
                )
            )
        )
    )
)

REM 3. Cari dari Windows Registry Uninstall keys
for /f "tokens=2*" %%A in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "MetaTrader 5" 2^>nul ^| findstr /i "InstallLocation"') do (
    if exist "%%B\metaeditor64.exe" (
        set "EDITOR_EXE=%%B\metaeditor64.exe"
        goto :FOUND_EDITOR
    )
    if exist "%%B\metaeditor.exe" (
        set "EDITOR_EXE=%%B\metaeditor.exe"
        goto :FOUND_EDITOR
    )
)
for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "MetaTrader 5" 2^>nul ^| findstr /i "InstallLocation"') do (
    if exist "%%B\metaeditor64.exe" (
        set "EDITOR_EXE=%%B\metaeditor64.exe"
        goto :FOUND_EDITOR
    )
    if exist "%%B\metaeditor.exe" (
        set "EDITOR_EXE=%%B\metaeditor.exe"
        goto :FOUND_EDITOR
    )
)

REM 4. Cari di berbagai folder program & drive lokal
for %%D in (
    "C:\Program Files\MetaTrader 5"
    "C:\Program Files\PU Prime MetaTrader 5"
    "C:\Program Files\ICMarkets MetaTrader 5"
    "C:\Program Files\XM Global MT5"
    "C:\Program Files\Exness MetaTrader 5"
    "C:\Program Files\FTMO MetaTrader 5"
    "C:\Program Files\Pepperstone MetaTrader 5"
    "C:\Program Files (x86)\MetaTrader 5"
    "C:\MT5"
    "C:\MetaTrader 5"
    "C:\MetaTrader"
    "D:\MT5"
    "D:\MetaTrader 5"
    "%LOCALAPPDATA%\Programs\MetaTrader 5"
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

REM 5. Wildcard search di root Program Files & C:
for /d %%D in ("C:\Program Files\*MetaTrader*" "C:\Program Files (x86)\*MetaTrader*" "C:\Program Files\*MT5*" "C:\*MT5*" "C:\*MetaTrader*") do (
    if exist "%%~fD\metaeditor64.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor64.exe"
        goto :FOUND_EDITOR
    )
    if exist "%%~fD\metaeditor.exe" (
        set "EDITOR_EXE=%%~fD\metaeditor.exe"
        goto :FOUND_EDITOR
    )
)

REM 6. Cek system PATH
for /f "delims=" %%I in ('where metaeditor64.exe 2^>nul') do (
    if exist "%%~fI" (
        set "EDITOR_EXE=%%~fI"
        goto :FOUND_EDITOR
    )
)
for /f "delims=" %%I in ('where metaeditor.exe 2^>nul') do (
    if exist "%%~fI" (
        set "EDITOR_EXE=%%~fI"
        goto :FOUND_EDITOR
    )
)

REM 7. Quick search via PowerShell di folder Program Files & Users
for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "Get-ChildItem -Path 'C:\Program Files*', 'C:\Users', 'C:\' -Filter 'metaeditor*.exe' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName -First 1"`) do (
    if exist "%%F" (
        set "EDITOR_EXE=%%F"
        goto :FOUND_EDITOR
    )
)

:FOUND_EDITOR
if "%EDITOR_EXE%"=="" (
    echo [ERROR] metaeditor64.exe tidak ditemukan otomatis di VPS.
    echo.
    echo TIPS: Cari lokasi shortcut MT5 di Desktop Anda:
    echo Klik kanan shortcut MT5 -^> Properties -^> 'Open File Location'.
    echo Di folder tersebut terdapat file 'metaeditor64.exe'.
    echo.
    echo Jalankan script ini dengan path tersebut, contoh:
    echo compile_ea.bat "C:\Lokasi\MT5\metaeditor64.exe"
    echo.
    pause
    exit /b 1
)

echo [OK] Ditemukan MetaEditor: "%EDITOR_EXE%"

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
