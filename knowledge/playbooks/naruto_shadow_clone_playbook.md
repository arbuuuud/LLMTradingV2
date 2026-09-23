# Playbook Eksplorasi Kuantitatif "Naruto Shadow Clone" (Kage Bunshin Engine)
**LLMTradingV2 Institutional Architecture**

---

## 1. Misi Utama (The Hokage Goal)

Misi mutlak Naruto Agent adalah mengeksplorasi, menguji secara paralel, dan melahirkan strategi kuantitatif handal (*Production-Ready Engine*) yang memenuhi kriteria:
1. **Target Profitabilitas**: Mencapai return konsisten **$\ge 1\%$ per hari** atau **$\ge 20\%$ per bulan**.
2. **Pencegahan Kelumpuhan (Anti-Analysis Paralysis)**:
   - Untuk gaya **Scalping (M1–M10)**: Wajib menghasilkan frekuensi minimal **$2 - 5\text{ peluang trade per hari}$** (atau $\ge 40\text{ trade per bulan}$).
   - Klon yang menghasilkan trade $< 30$ per bulan otomatis **didiskualifikasi** oleh Auditor.
3. **Penyajian 4 Profil Risiko Standar**:
   - 🛡️ **Prop Firm**: Base Risk 0.50% ($1.0\text{x}$), Max Drawdown $\le 7.8\%$.
   - 💎 **Sweet Spot**: Base Risk 0.75% ($1.5\text{x}$), Max Drawdown $\le 10.7\%$ (Rekomendasi Utama Akun Real).
   - 🚀 **Aggressive**: Base Risk 1.00% ($2.0\text{x}$), Max Drawdown $\le 13.1\%$.
   - ⚡ **YOLO**: Base Risk 2.00% ($4.0\text{x}$), Max Drawdown $\le 22.0\%$.

---

## 2. Default Thinking Matrix (Pohon Hipotesis Multi-Dimensi)

Setiap kali pengguna memasukkan metodologi riset baru (contoh: *PAC - Pivot and Control*), Naruto secara otonom membelah diri menjadi puluhan klon (*Shadow Clones*) dengan memvariasikan 4 dimensi inti:

### Dimensi 1: Market Structure & Fibonacci State
- **Kondisi Gelombang**:
  - *Klon Impulsif*: Trading searah gelombang ekspansi tren.
  - *Klon Korektif*: Trading pada gelombang retrace/pullback.
  - *Klon Range-Bound*: Trading bolak-balik di pasar sideway (Mean Reversion murni).
- **Trigger Event**:
  - *Pasca-BOS*: Entry sesaat setelah terjadi Break of Structure.
  - *Pasca-CHoCH*: Entry pada perubahan karakter tren awal.
- **Konfluensi Fibonacci**:
  - *High Conviction*: Rentang Roof-Floor berada pada zona Golden OTE (0.618–0.786).
  - *Standard Range*: Rentang Roof-Floor normal (0.382–0.500 Shallow).

### Dimensi 2: Karakteristik & Kasta POI (Roof & Floor Selection)
- **Bahan Dasar Zona**:
  - *Reversal OB*: Murni menggunakan DBR (+OB Demand) dan RBD (-OB Supply).
  - *Continuation S&D*: Menggunakan RBR (+Demand) dan DBD (-Supply) dengan base 1–3 candle.
  - *Smart Confluence Cluster*: Mengutamakan zona leburan bertumpuk (`★ [CONFLUENCE CLUSTER]`).
  - *FVG / iFVG*: Menggunakan batas celah ketidakseimbangan harga.
- **Freshness & Liquidity**:
  - *Virgin Only*: Sentuhan = 0.
  - *Tested Tolerance*: Mengizinkan zona yang sudah disentuh 1–2 kali selama belum tembus body close.
  - *Liquidity Swept*: Bobot keyakinan bertambah jika base sudah menyapu High/Low sebelumnya.

### Dimensi 3: Peran Candlestick Pattern (Execution Trigger vs Guardian Force Close)
- **Mode Eksekusi Entry**:
  - *Pre-set Grid Limit*: Memasang limit order langsung di area diskon 0–25% (tanpa menunggu candle, frekuensi tinggi).
  - *Confirmed Reaction [Reac]*: Order baru aktif jika sudah terbentuk candle pantulan `[Reac] Bull Engulfing / Pin Bar Hammer` di lantai.
- **Mode Guardian Early Force Close**:
  - *Counter Momentum Kill [Mom]*: Menutup posisi sebelum TP jika muncul candle lawan `[Mom] Marubozu` berdaya dorong besar.
  - *Counter POI Touch*: Menutup posisi atau mengunci BEP saat harga menyentuh POI baru di depan harga.

### Dimensi 4: Sesi Waktu & Killzones (Timezone Filters)
- *Asian Session*: Sesi tenang, volatilitas rendah, ideal untuk scalping range-bound PAC.
- *London Open (14.00–18.00 WIB)*: Injeksi likuiditas awal eropa.
- *New York Overlap (19.00–23.00 WIB)*: Puncak volatilitas harian dan tren ekspansi kencang.
- *All-Day Flexible*: Berjalan 24 jam dengan batas filter spread.

---

## 3. Protokol Anti-Overfitting (The Auditor Veto Gate)

Sebelum klon dinyatakan lulus menjadi strategi produksi:
1. **Aturan Syarat Aditif (Additive Scoring)**:
   - Hindari *Checklist Over-Filtering*. Syarat mutlak (*Mandatory*) hanya 2: (1) Berada di kuadran zona entry, (2) Batas batas struktural belum jebol.
   - Faktor konfluensi lain (Fibo OTE, Swept Liq, Reac Candle) bertindak sebagai **pengali ukuran lot / bobot tambahan**, bukan syarat gugur.
2. **Uji Validasi Brutal 3 Tahap**:
   - **Tahap A: Walk-Forward Analysis (WFA)**: Data dibagi rolling train/test. WFE (*Walk-Forward Efficiency*) wajib $\ge 60\%$.
   - **Tahap B: Monte Carlo Permutation (1,000 runs)**: Urutan trade diacak untuk menguji ketahanan drawdown ekstrim.
   - **Tahap C: 500 Random Monkeys**: Klon diuji melawan 500 bot acak. Nilai signifikansi statistik wajib $p\text{-value} < 0.01$.
