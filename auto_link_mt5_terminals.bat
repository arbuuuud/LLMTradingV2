@echo off
setlocal EnableDelayedExpansion
REM Auto-Link Single Shared Expert Advisor to All MT5 Terminal Instances on Windows
cd /d "%~dp0"

echo ============================================================
echo 🔗 MENYAMBUNGKAN 1 FOLDER EXPERTS KE SEMUA INSTANCE MT5
echo Target Source: %CD%\bridge\mt5
echo ============================================================

set "SOURCE_DIR=%CD%\bridge\mt5"
set /a COUNT=0

REM 1. Pindai folder Roaming AppData (Standar MT5 Multi-Instance)
set "TERMINAL_ROOT=%APPDATA%\MetaQuotes\Terminal"

if exist "%TERMINAL_ROOT%" (
    for /d %%D in ("%TERMINAL_ROOT%\*") do (
        if exist "%%D\MQL5\Experts" (
            set "TARGET_LINK=%%D\MQL5\Experts\LLMTradingV2"
            if not exist "!TARGET_LINK!" (
                mklink /J "!TARGET_LINK!" "%SOURCE_DIR%" >nul 2>&1
                if exist "!TARGET_LINK!" (
                    echo [LINK BERHASIL] %%~nxD -^> LLMTradingV2 Terhubung!
                    set /a COUNT+=1
                )
            ) else (
                echo [SUDAH TERHUBUNG] %%~nxD
                set /a COUNT+=1
            )
        )
    )
)

REM 2. Pindai folder Program Files (Portable Mode jika ada)
for /d %%P in ("C:\Program Files\MetaTrader 5*" "C:\Program Files (x86)\MetaTrader 5*" "C:\Program Files\PU Prime*" "C:\Program Files\ICMarkets*") do (
    if exist "%%P\MQL5\Experts" (
        set "TARGET_P=%%P\MQL5\Experts\LLMTradingV2"
        if not exist "!TARGET_P!" (
            mklink /J "!TARGET_P!" "%SOURCE_DIR%" >nul 2>&1
            if exist "!TARGET_P!" (
                echo [PORTABLE LINK] %%~nxP -^> LLMTradingV2 Terhubung!
                set /a COUNT+=1
            )
        ) else (
            echo [PORTABLE AKTIF] %%~nxP
            set /a COUNT+=1
        )
    )
)

echo ============================================================
echo ✅ SELESAI! Sebanyak %COUNT% instance MT5 kini memakai 1 folder yang sama.
echo Cukup compile 1 kali di MetaEditor, semua MT5 otomatis terupdate!
echo Di setiap MT5: Klik kanan 'Experts' -^> 'Refresh' di Navigator.
echo ============================================================
pause
