# Playbook Kalibrasi Engine PAC: Pembelajaran Forward Test VPS & Blueprint Kage Bunshin

**Dokumen Kontrak Strategi**: `knowledge/playbooks/pac_engine_calibration_playbook.md`  
**Ref Keputusan**: DEC-018 (Fase 5 Subtask T5-3)  
**Tujuan**: Mentransformasikan temuan riil 52 Forward Trades VPS (Win Rate 73.1%, Net -$9.82, Payoff Ratio 0.29) menjadi performa profitabel konsisten (Profit Factor > 2.0, R:R >= 1:2) melalui Kage Bunshin Tournament.

---

## 🔬 1. Hasil Audit Riil 52 Forward Trades VPS

Dari data murni MT5 demo di VPS:
- **Total Trades**: 52 trades
- **Win Count**: 38 trades (73.1% Win Rate)
- **Loss Count**: 14 trades (26.9%)
- **Net PnL**: -$9.82 (Total Win: +$36.85, Total Loss: -$46.67)
- **Akar Masalah (Root Cause)**:
  - 23 dari 38 win (60.5%) terkunci di BEP flat (+$0.20) karena ambang BEP (+1.0 poin) terlalu sempit untuk instrumen XAUUSD.
  - Rata-rata Win (+$0.97) jauh lebih kecil daripada rata-rata Loss (-$3.33), menghasilkan Payoff Ratio 0.29.

---

## 🎯 2. Empat Pilar Kalibrasi Engine PAC (Kage Bunshin Matrix)

### Pilar 1: Naruto-2 Reversal Cognition Guardian (Subtask 5-3A)
- **Peran**: Agent spesialis pembaca sinyal pembalikan arah saat posisi sedang berjalan (running profit).
- **Logika Kognitif**:
  - Jika posisi BUY sedang running naik, lalu mendadak muncul pola pembalikan di M1 (Evening Star, Shooting Star Rejection Wick, atau Bearish Engulfing):
    1. *Evaluasi Konteks*: Apakah pola ini muncul di dekat zona Supply (Roof) atau di area OTE?
    2. *Tindakan Taktis*: Daripada membiarkan harga turun menghantam BEP atau SL, agent mengeksekusi **Force TP / Early Partial Exit** untuk mengamankan profit maksimal di puncak.
    3. *Refleksi Struktur*: Menandai titik pembalikan tersebut sebagai kandidat *Local Roof* baru untuk potensi setup reversal berikutnya.

### Pilar 2: Greed-Version Trailing Profit & Daily Circuit Breaker (Subtask 5-3B)
- **Sistem Penguncian Bertingkat (Greed Trailing)**:
  - Floating Profit mencapai **+1.0% Equity** $\to$ Kunci Stop Loss di **+0.5% Equity** (Trading berhenti jika turun ke +0.5%).
  - Floating Profit naik ke **+1.5% Equity** $\to$ Kunci Stop Loss di **+1.0% Equity**.
  - Floating Profit naik ke **+2.0% Equity** $\to$ Kunci Stop Loss di **+1.5% Equity**.
  - Begitu seterusnya hingga posisi ter-lock sendiri oleh pasar saat terjadi pullback.
- **Daily Risk Boundary**:
  - Kerugian maksimal harian dibatasi ketat: **-1.0% Equity / hari** (Hard Trading Lockout hingga 00:00 UTC).
  - Target profit harian minimal: **+2.0% Equity / hari** (Rasio Risk-Reward Harian 1:2).
  - Preset profil diselaraskan untuk: *Prop Firm*, *Sweet Spot*, *Aggressive*, dan *YOLO*.

### Pilar 3: Virgin Liquidity Depth Engine (Subtask 5-3C)
- **Aturan Kesegaran Likuiditas (Untouched Depth > 50%)**:
  - Jika zona demand/supply M1 sudah tertembus atau termitigasi $> 50\%$ kedalamannya, zona tersebut kehilangan daya tahan.
  - Bot **dilarang keras** memasang limit order baru di level yang sudah tersentuh ($< 50\%$).
  - Order limit baru **hanya boleh dialokasikan** pada kedalaman yang masih murni (*virgin/untouched* $> 50\%$).
  - Jika zona sudah tertembus seluruhnya, zona berstatus **EXHAUSTED**.

### Pilar 4: Kage Bunshin Tournament on Limit Order Style (Subtask 5-3D)
Mengadu probabilitas eksekusi di ribuan candle M1 XAUUSD:
- **Kubu A (Single Precision Limit)**:
  - Hanya menempatkan **1 Limit Order** tunggal di Golden Level (misal kedalaman 50% atau Equilibrium OTE).
- **Kubu B (Layered Depth Grid)**:
  - Begitu zona terbentuk, **langsung memasang 3 hingga 5 limit order sekaligus** secara serentak (misal layer 20%, 40%, 60%, 80%).
- **Tujuan Turnamen**: Menemukan model mana yang menghasilkan Sharpe Ratio, Profit Factor, dan stabilitas Drawdown terbaik.
