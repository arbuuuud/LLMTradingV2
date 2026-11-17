@echo off
REM Tool to archive old forward trades and reset forward_trades_vps.json cleanly
cd /d "%~dp0"

echo ============================================================
echo 📦 MENGARSIPKAN DATA LAMA & RESET TELEMETRY VPS (BATCH BARU)
echo ============================================================

if not exist "data\archives" mkdir "data\archives"

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set TIMESTAMP=%datetime:~0,8%_%datetime:~8,6%

if exist "data\forward_trades_vps.json" (
    copy "data\forward_trades_vps.json" "data\archives\vps_backup_%TIMESTAMP%.json" >nul
    echo [BACKUP SUKSES] data\archives\vps_backup_%TIMESTAMP%.json
) else (
    echo [INFO] File data\forward_trades_vps.json belum ada.
)

REM Reset isi file menjadi array kosong []
echo []> "data\forward_trades_vps.json"

echo [RESET BERSIH] data\forward_trades_vps.json -> []
echo ============================================================
echo ✅ SELESAI! Data lama tersimpan aman di folder data\archives.
echo Telemetry forward test siap mencatat transaksi dari nol!
echo ============================================================
pause
