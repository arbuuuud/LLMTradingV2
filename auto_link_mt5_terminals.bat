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
echo ✅ SELESAI! Sebanyak %COUNT% instance MT5 kini memakai 1 subfolder LLMTradingV2 yang sama.
echo.
echo 💡 PANDUAN REFRESH PASCA-COMPILE DI METAEDITOR:
echo 1. Anda cukup tekan F7 (Compile) 1 kali di MetaEditor.
echo 2. File binary LLMTradingBridge.ex5 otomatis ter-update untuk semua terminal.
echo 3. Karena MT5 me-load EA ke memori RAM saat berjalan:
echo    - Di terminal MT5 yang tidak otomatis reload:
echo      Cukup ganti timeframe chart (misal: M1 -> M5 -> M1),
echo      ATAU klik kanan chart -> Expert Advisors -> Properties -> OK,
echo      ATAU klik kanan Navigator 'Experts' -> Refresh.
echo 4. PERIKSA POJOK KIRI ATAS CHART:
echo    Lihat baris '🔨 Unique Build ID' (tanggal dan jam compile).
echo    Jika jam compile di semua terminal sudah sama, artinya seluruh
echo    terminal sudah 100%% menjalankan versi terbaru yang identik!
echo ============================================================
pause
