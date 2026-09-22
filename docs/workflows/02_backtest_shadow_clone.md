# Workflow 2: Backtest & Shadow Clone Testing (Kage Bunshin)

## 1. Tujuan
Melakukan pengujian brutal (*brutal backtesting*) terhadap strategi dan model checklist trading menggunakan data historis tick & bar. Metode ini mengadopsi konsep **Shadow Cloning (Kage Bunshin)**: satu strategi dasar (*base strategy*) di-kloning secara otomatis menjadi puluhan atau ratusan variasi parameter untuk diadu secara simultan.

Tujuan penting lainnya adalah menguji dan memvalidasi performa **ForceClose Agent** secara kuantitatif.

---

## 2. Mekanisme Shadow Clone (Kage Bunshin Matrix)

### A. Dimensi Mutasi (Ablation Matrix)
Setiap kloningan menguji variasi kombinasi checklist, seperti:
1. **Entry Trigger Requirements**:
   - Clone 01: Wajib Sweep Liquidity + OB + FVG + OTE.
   - Clone 02: Cukup FVG + BOS (tanpa perlu OB).
   - Clone 03: Wajib iFVG (Inversion) rejection.
2. **OTE Depth**:
   - Clone A: Entry tepat di level 0.618.
   - Clone B: Entry di deep discount level 0.786.
3. **Exit & ForceClose Rules**:
   - Baseline: Fixed SL & TP (misal 1:2 R:R).
   - Dynamic Clone 1: ForceClose jika candle M1 close menembus iFVG berlawanan arah.
   - Dynamic Clone 2: ForceClose jika momentum stall > 5 candle di area spread tinggi.
   - Dynamic Clone 3: Breakeven lock begitu harga bergerak +1R.

### B. Arsitektur Komputasi
- Dibangun di atas **Polars Vectorized Backtesting** dan **Event-Driven Bar Simulator**.
- Menggunakan multiprocessing / parallel CPU workers agar puluhan varian dapat selesai diuji dalam hitungan detik.

---

## 3. Metrik Evaluasi & Uji Performa ForceClose Agent

Setiap clone dinilai berdasarkan metrik institusional:
- **Sharpe Ratio** & **Sortino Ratio**.
- **Max Drawdown (%)** & **Calmar Ratio**.
- **Expectancy per Trade (R-multiple)**.
- **ForceClose Efficacy (Saved R)**:
  $$\text{Saved R} = \sum (\text{Loss jika kena Fixed SL} - \text{Actual Loss saat di-ForceClose})$$
  Jika *Saved R* positif signifikan tanpa memotong trade yang seharusnya berujung profit (*false early exit*), maka aturan ForceClose tersebut dinyatakan superior dan diintegrasikan ke Trading Engine.

---

## 4. Output Workflow

1. **Leaderboard Report**: Tabel peringkat klon terbaik.
2. **Checklist Recommendation**: Spesifikasi bobot kriteria optimal untuk dipasang pada Tactician Agent.
3. **Graduation Artifact**: File konfigurasi strategi `registry/strategies/STRAT-XXX.yaml` siap diuji ke **Forward Test (W4)**.
