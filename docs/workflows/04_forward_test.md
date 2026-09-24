# Workflow 4: Forward Test Workflow (Incubation Staging)

## 1. Tujuan
Menjadi pintu gerbang validasi (*staging / sandbox*) sebelum suatu strategi hasil optimasi W2 (Backtest) diizinkan dieksekusi menggunakan modal riil di W3 (Live Trading). Mengeliminasi bias *overfitting* data historis dan membongkar disparitas eksekusi dunia nyata vs teori backtest.

---

## 2. Kriteria Inkubasi (Graduation Gate)

Setiap strategi yang dipromosikan dari Backtest wajib melewati pengujian di akun Demo / Paper Trading dengan kriteria:
1. **Durasi / Sampel Minimum**:
   - Berjalan aktif minimal **20 hari bursa** ATAU telah mengeksekusi minimal **50 closed trades**.
2. **Toleransi Degradasi Performa (Max 15%)**:
   - Realized Winrate $\ge 0.85 \times \text{Backtest Winrate}$.
   - Realized Profit Factor $\ge 0.85 \times \text{Backtest Profit Factor}$.
   - Max Drawdown Demo $\le 1.20 \times \text{Backtest Max Drawdown}$.
3. **Slippage & Spread Audit**:
   - Memastikan strategi tidak bergantung pada fill rate teoritis yang tidak realistis di kondisi spread riil.

---

## 3. Siklus Hidup Strategi (Strategy State Machine)

```text
[DRAFT / BRAINSTORM] (W5)
         │
         ▼
    [BACKTESTING] (W2)
         │ (Lolos Kage Bunshin Leaderboard)
         ▼
   [FORWARD_STAGING] (W4 - Demo/Paper)
         │
         ▼
   [DISPARITY_AUDIT] (T4-1C: Forward MT5 vs Python Backtest Replication)
         │
    ┌────┴────────────────────────┐
    ▼ (Lolos KPI & Disparity < 15%)▼ (Gagal KPI / Severe Drift)
[LIVE_APPROVED] (W3)          [REJECTED / ARCHIVED]
```

---

## 4. Protokol Wajib: Investigasi Disparitas Forward vs Backtest (DEC-020)

### Latar Belakang Masalah
Banyak sistem kuantitatif tampak luar biasa di backtest (Profit Factor tinggi, kurva ekuitas mulus), namun saat dipasang di forward test akun demo, hasilnya sering kali **berbeda jauh (disparity)** — seperti kasus VPS forward test di mana PF anjlok menjadi 0.79 karena friksi eksekusi, pelebaran spread, antrian limit order, dan proteksi BEP yang terlalu ketat.

### Metodologi Replikasi Deterministik Python
Untuk menghentikan ketidakpastian dan praduga, sistem menetapkan aturan baku:
Setiap kali batch trade forward selesai dipanen (`forward_trades_vps.json` atau `forward_trades_local.json`):
1. **Ekstraksi Data Bar Identik**:
   Sistem mengambil rentang waktu (timestamp awal s/d akhir) dari seluruh trade forward tersebut, lalu memotong bar OHLCV M1 yang sama persis dari Data Lake (`data/parquet/xauusd_m1.parquet`).
2. **Re-Run di Python Backtest Engine**:
   Data bar tersebut dijalankan ulang di `src/workflows/backtest.py` dengan parameter strategi yang persis sama.
3. **Head-to-Head Disparity Matrix**:
   - **Trade Matching**: Berapa trade yang dieksekusi di MT5 namun terlewat di Python (atau sebaliknya)?
   - **Spread & Fill Friction**: Berapa selisih harga entry rata-rata akibat spread ask/bid riil broker vs spread teoritis?
   - **Exit Cause Breakdown**: Apakah trade di MT5 keluar karena BEP prematur, trailing stop, hit TP, atau SL?
4. **Disparity Verdict**:
   Jika perbedaan Profit Factor $> 15\%$, strategi **DILARANG NAIK KE REAL** dan wajib dikembalikan ke meja kalibrasi Kage Bunshin.
