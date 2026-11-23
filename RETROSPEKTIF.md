# 🛡️ RETROSPEKTIF & POST-MORTEM ARSITEKTUR (ANTI-REGRESSION LOG)

Dokumen ini adalah rekam jejak insiden kritis, kegagalan arsitektur, dan pelajaran empiris dalam pengembangan sistem trading institusional `LLMTradingV2`.
**ATURAN WAJIB**: Seluruh agen AI dan developer **WAJIB membaca dokumen ini** sebelum merancang atau memodifikasi logika strategi, penentuan Stop Loss/Take Profit, manajemen grid limit order, migrasi data, dan eksekusi MT5 Bridge.

---

## [INCIDENT-001] Anomali Inverted Stop Loss Judas L4 & Mitigated Area Blindness
- **Tanggal Insiden Teridentifikasi**: 23 November 2026
- **Status Resolusi**: RESOLVED
- **Komponen Terdampak**:
  - `src/bridge/server.py` (MT5 Live Bridge Server)
  - `src/workflows/backtest.py` (Backtest Engine & Kage Bunshin)
  - `src/features/poi_prioritizer.py` (POI Prioritizer)
  - `scripts/run_batch1_fibo_judas_tournament.py` (Batch Tournament Runner)
- **Tingkat Keparahan**: P0 (Kritis) — Menghasilkan anomali "False Champion" pada turnamen dan penolakan order MT5 `10016: TRADE_RETCODE_INVALID_STOPS`.

---

### 1. Deskripsi Detail Insiden

#### A. Inverted Stop Loss Anomaly pada Layer 4 Judas Catch
- **Mekanisme**:
  - Strategi DEC-043 (4-Layer Judas Grid) menempatkan order Layer 4 (L4) pada ekstensi $-27.2\%$ dari rentang swing (`sw_low - span * 0.272`).
  - Namun rumus fallback *Smart Judas Fortress SL* dihitung pada ekstensi $-13.0\%$ (`sw_low - span * 0.130 - 0.25`).
- **Anomali yang Terjadi**:
  - Pada posisi BUY, harga Stop Loss berada di **ATAS** harga Buy Limit L4 ($3697.15 > 3694.56$).
  - Di akun MT5 VPS nyata, broker menolak order ini dengan kode `10016: TRADE_RETCODE_INVALID_STOPS` karena Stop Loss buy limit wajib berada di bawah harga entri.
  - Di Python Backtest / Tournament script, formula perhitungan profit:
    $$\text{r\_gain} = \frac{\text{tp} - \text{entry}}{\max(\text{entry} - \text{sl}, 0.1)}$$
    Karena $\text{entry} < \text{sl}$ (angka negatif), fungsi `max(negatif, 0.1)` menghasilkan penyebut `0.1`.
    Akibatnya, nilai R-Multiple dan Net PnL **melompat 10x hingga 50x lipat secara artifisial**. Clone yang memiliki bug ini dinobatkan sebagai "Juara #1" di turnamen dengan PnL fiktif $90,195!

#### B. Mitigated / Spent Area Blindness ("Unused Area" Diabaikan)
- **Mekanisme**:
  - Bridge server menembakkan limit order murni berbasis kuadran persentase swing statis (25%, 12.5%, 0%, -27.2%) tanpa memeriksa histori penetrasi harga pada swing berjalan.
  - Jika harga sudah pernah turun menembus 25% dan 12.5% lalu memantul, order BUY_LIMIT tetap dipasang di level 25% dan 12.5%.
  - Pada saat yang sama, modul `src/features/smc.py` sudah memiliki pelacakan `deepest_touch_price` pada Order Block dan FVG, tetapi data ini **terputus** di `POIPrioritizer` (`SelectedPOIAnchor` tidak membawa data penetrasi masa lalu).
  - Di `src/workflows/backtest.py`, variabel `deepest_touch` berstatus *zombie variable* (dideklarasikan dan di-reset tetapi tidak pernah di-update atau dibaca di dalam loop bar).

#### C. Micro Depletion Leakage & Parsing Truncation
- Pengecekan komentar order MT5 hanya memeriksa `_L2` dan `_L3`. Jika posisi L4 tertutup, layer index default ke `0` (L1 dianggap habis, L4 tetap terbuka).
- Depletion tidak diisolasi per-timeframe, sehingga closed trade pada M1 menghapus layer aktif pada M15.
- Depletion hanya dicatat saat transaksi ditutup untung (Take Profit), mengabaikan posisi yang terkena Stop Loss atau Breakeven.

#### D. Penimpaan Batas POI RBR/DBD yang Diprioritaskan
- Saat `POIPrioritizer` memilih base RBR (sebagai Floor) atau DBD (sebagai Roof), nilai batas atas dan bawah base tersebut langsung tertimpa oleh kalkulasi kuadran $25\% / 75\%$ generic swing high-low.

---

### 2. Akar Masalah (Root Causes)
1. **Absence of Invariant Checkers**: Tidak adanya gerbang validasi matematis di pipeline eksekusi (`BUY` wajib `SL < Entry < Price`, `SELL` wajib `SL > Entry > Price`).
2. **Defensive Programming Trap**: Penggunaan `max(..., 0.1)` untuk mencegah division-by-zero secara membabi buta menyembunyikan kesalahan logika fatal (*silent corruption*) alih-alih melempar exception atau mendiskualifikasi clone.
3. **Data Pipeline Disconnection**: SMC feature engine menghasilkan metadata *touch lifecycle*, tetapi pipeline prioritizer membuang metadata tersebut sebelum mencapai modul eksekusi.
4. **Zombie Code in Simulation**: Backtest engine memiliki variabel yang tidak terhubung dengan eksekusi, menciptakan disparitas 99% antara backtest teoritis vs forward trading live.

---

### 3. Pagar Pembatas Permanen (Architectural Guardrails)

Seluruh implementasi di masa depan wajib mematuhi kaidah berikut:

1. **Aturan Invariant Order Broker Mutlak**:
   - Untuk semua pesanan BUY (Market / Limit):
     $$\text{SL} \le \text{Entry} - \text{MinBuffer} \quad (\text{MinBuffer} \ge 0.50 \text{ pt})$$
     $$\text{TP} \ge \text{Entry} + \text{MinBuffer}$$
   - Untuk semua pesanan SELL (Market / Limit):
     $$\text{SL} \ge \text{Entry} + \text{MinBuffer} \quad (\text{MinBuffer} \ge 0.50 \text{ pt})$$
     $$\text{TP} \le \text{Entry} - \text{MinBuffer}$$
   - Jika dilanggar, order **wajib ditolak seketika** di level Python sebelum dikirim ke socket MT5.

2. **Aturan Stop Loss Judas Grid**:
   - Jika grid memiliki Layer 4 (ekstensi $-27.2\%$), Stop Loss fallback **wajib berlabuh di ekstensi $\le -38.2\%$** (atau OB valid yang berada di bawah L4).
   - Dilarang menempatkan SL di $-13\%$ jika ada order entry di bawah $-13\%$.

3. **Aturan Unused Area / Virgin Liquidity**:
   - Sebuah level limit order hanya sah berstatus **UNUSED** jika:
     1. Belum pernah tersentuh oleh wick/ekor candle mana pun pada swing/leg saat ini (`pullback_low > limit_p - 0.20` untuk BUY).
     2. Belum pernah tertembus lebih dalam dari harga level tersebut pada base POI terkait (`selected_anchor.deepest_touch_price`).
     3. Belum ditandai *spent* oleh siklus depletion (`lay_i not in spent_layers`).
   - Jika mode `VIRGIN_DEPTH_ONLY` aktif, level bibir dangkal ($25\%$ Buy / $75\%$ Sell) wajib di-skip, sehingga hanya level kedalaman murni ($12.5\%$, $0\%$, $-27.2\%$) yang dipasang.

4. **Aturan Integritas Auditor Agent**:
   - Auditor Agent wajib mengaudit log trade setiap clone turnamen.
   - Clone yang menghasilkan trade dengan kondisi $\text{entry} \le \text{sl}$ (BUY) atau $\text{entry} \ge \text{sl}$ (SELL) otomatis **DISQUALIFIED (DQ)** dengan alasan `MATH_ANOMALY: Inverted Stop Loss`.

---

### 4. Checklist Verifikasi Anti-Regresi

Sebelum melakukan merge ke `main`, pastikan:
- [ ] Menjalankan `pytest` dan memastikan 100% test lulus.
- [ ] Menjalankan unit test khusus:
  - `test_smart_judas_fortress_sl_and_4_layer_grid`
  - `test_unused_area_filtering_skips_penetrated_levels`
  - `test_l4_depletion_detection_and_timeframe_isolation`
- [ ] Memastikan tidak ada pembagian dengan `0.1` tanpa pemeriksaan validitas arah posisi di seluruh file backtest.
- [ ] Memastikan terminal MT5 tidak menerima kode error `10016: TRADE_RETCODE_INVALID_STOPS`.
