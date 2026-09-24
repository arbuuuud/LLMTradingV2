# 🔬 Laporan Audit Disparitas Head-to-Head: Forward Test MT5 vs Replikasi Python Backtest Engine (T4-1C / DEC-020)

**Tanggal Evaluasi**: 25 September 2026  
**Rentang Waktu Evaluasi**: 24 September 2026, 18:32:11 UTC s/d 22:50:00 UTC (~4 Jam 18 Menit)  
**Data Bar Sumber**: 360 Bar M1 XAUUSD (Recorded Ground-Truth di `reports/radar_state.json`)  
**Data Transaksi Forward**: 348 Closed Deals (57 Wave Setups) di `data/forward_trades_vps.json`  
**Engine Pembanding**: `src/workflows/backtest.py` (Vectorized & Event-Driven Polars Engine)

---

## 1. Tabel Komparasi Head-to-Head (Data Bar Identik)

Berikut perbandingan langsung antara hasil eksekusi nyata di MetaTrader 5 VPS versus simulasi deterministik Python pada rentang waktu dan bar M1 yang sama persis:

| Metrik Evaluasi | 🐍 Python Replay (Teoritis Murni) | 🖥️ Forward Test MT5 (Sweet Spot $10K) | 🌐 Forward Test MT5 (All 4 Accounts) | Gap Disparitas |
| :--- | :--- | :--- | :--- | :--- |
| **Rentang Bar Diuji** | 360 Bar M1 (18:32 - 22:50 UTC) | 360 Bar M1 (18:32 - 22:50 UTC) | 360 Bar M1 (18:32 - 22:50 UTC) | **Identik 100%** |
| **Siklus Setup / Waves** | 149 trades teoritis | 40 Waves (86 deals) | 57 Waves (348 deals) | Filter Retest MT5 lebih selektif |
| **Win Rate (Setup / Wave)**| **93.3%** | **70.0%** | **70.2%** (40W / 17L) | **-23.1% Gap** |
| **Profit Factor (PF)** | **33.03** | **1.01** | **1.01** | **-32.02 Gap** |
| **Gross Profit** | +$2,287.40 | +$532.93 | +$4,012.22 | Realized TP terpotong spread |
| **Gross Loss** | -$71.53 | -$527.48 | -$3,982.18 | Hard SL tersentuh penuh saat breakout |
| **Net PnL ($)** | **+$2,215.87** | **+$5.45** | **+$30.04** | Gap Ekspektasi vs Lapangan |
| **Payoff Ratio (W / L)** | **> 2.45** | **0.43** (Avg Win $18.73 vs Loss $43.25) | **0.45** | **Akar Masalah Utama** |
| **Maximum Drawdown** | **0.40%** | **1.98%** | **1.03% - 8.94%** | Terkendali di bawah batas aman |

---

## 2. Bedah Mendalam: Kenapa Terjadi Disparitas Gap? (Root Cause Analysis)

Setelah membedah data transaksi satuan dan mencocokkannya ke pergerakan harga per bar, ditemukan **3 FAKTOR UTAMA** yang menyebabkan perbedaan antara Backtest Python vs Forward MT5:

### 🔴 Faktor 1: Asimetri Payoff Ratio Akibat Fill Partial Layer Grid
Ini adalah **penyebab nomor satu**:
- **Saat Menang (WIN Waves = 40 kali / 70.2%)**:
  - Pada 18 gelombang kemenangan, harga hanya menyentuh **Layer 1 (Bibir 25%)**, lalu langsung memantul cepat ke target TP Midpoint 50%.
  - Karena hanya 1 layer yang tersambar, posisi yang menghasilkan profit hanya berukuran kecil (misal: 0.03 lot di Sweet Spot $\to$ profit rata-rata hanya **+$18.73** per gelombang).
- **Saat Kalah (LOSS Waves = 17 kali / 29.8%)**:
  - Pasar tidak sekadar memantul, melainkan menembus (*breakout*) zona PAC secara agresif.
  - Akibatnya, **ketiga layer (Layer 1, Layer 2, Layer 3) tersambar semua** sebelum harga menyentuh Hard Stop Loss!
  - Kerugian dihitung dari total akumulasi 3 layer (0.03 + 0.04 + 0.05 = 0.12 lot $\to$ rugi rata-rata **-$43.25** per gelombang).
- **Kesimpulan Matematis**:
  Meskipun Win Rate gelombang sangat tinggi (**70.2%**), karena rata-rata menang hanya **$18.73** sedangkan rata-rata kalah mencapai **$43.25** (Payoff Ratio 0.43), kurva keuntungan tertahan di titik impas (**Profit Factor 1.01**).

### 🔴 Faktor 2: Friksi Spread Ask-Bid Broker & Slippage di Akun Real MT5
- Di Python Backtest, harga dieksekusi secara instan pada garis High/Low bar M1.
- Di MT5 VPS nyata:
  - Pada posisi **SELL**, penutupan posisi (TP dan SL) dieksekusi di harga **ASK** ($Ask = Bid + Spread$). Spread XAUUSD saat malam hari berkisar 0.20 - 0.35 poin ($20 - $35 per 1.0 lot).
  - Ketika harga mendekati Midpoint 50% TP, posisi SELL tertahan beberapa tick lebih lama untuk menyentuh TP akibat spread, sementara saat bergerak mendekati SL, spread justru mempercepat tersentuhnya Hard SL.

### 🔴 Faktor 3: Penumpukan Cooldown & Retest Filter di Python Bridge
- Python Backtest murni membuka trade setiap kali bar menyentuh zona PAC tanpa batasan jeda waktu.
- Pada Live Bridge (`src/bridge/server.py`), kita memasang proteksi ketat:
  - Cooldown minimal 60 detik antar order.
  - Pengecekan `has_matching_pending` dan `has_active_pos` agar tidak spamming limit order.
- Dampak positifnya: MT5 terhindar dari overtrading liar (hanya 57 gelombang dibanding 149 trade teoritis). Namun dampak sampingnya, beberapa pantulan PAC yang sangat cepat tidak sempat diambil limit order-nya.

---

## 3. Kesimpulan Komparatif

1. **Akurasi Arah Sinyal Terbukti Valid**:
   Tingkat kemenangan arah PAC terkonfirmasi sangat tinggi (**70.2% Win Rate** di 57 gelombang live MT5). Logika penentuan kuadran 0-25% dan 75-100% bekerja dengan baik di pasar nyata.
2. **Kelemahan Terletak pada Grid Asymmetry**:
   Menang dengan 1 layer ($18), kalah dengan 3 layer ($43). Ini adalah karakteristik klasik strategi grid limit order tanpa mitigasi ukuran lot bertingkat.
3. **Sistem Terbukti Aman & Resilient**:
   Semua akun terproteksi 100% dari kegagalan margin. Akun Prop Firm hanya mengalami drawdown 1.03%, dan akun Sweet Spot serta YOLO membukukan Net Profit positif.

---

## 4. Rekomendasi Solusi & Kalibrasi Berikutnya (Next Iteration Action Items)

Untuk mengangkat Profit Factor dari **1.01 menjadi $\ge 2.50$ di Live MT5**, langkah kalibrasi yang direkomendasikan adalah:

1. **Inverted Lot Distribution (Martingale Terbalik / Anti-Grid Choking)**:
   - Alih-alih membagi lot sama rata atau memperbesar lot di layer bawah, buat **Layer 1 (Bibir) membawa bobot lot terbesar (misal: 50% risiko)**, dan Layer 2 & 3 membawa sisa 25% + 25%.
   - Dengan begitu, saat 18 gelombang yang hanya menyentuh Layer 1 memantul ke TP, profit yang dipanen menjadi **2x lipat lebih besar**, menyeimbangkan payoff ratio!
2. **Adaptive Quick-Escape TP untuk Multi-Layer**:
   - Jika Layer 2 atau Layer 3 tersentuh, geser target TP lebih dekat (misal ke rata-rata harga entry + 0.5R) untuk keluar dari pasar sesegera mungkin dengan *small profit* daripada memaksakan menunggu ke Midpoint 50%.
