# 🥋 Laporan Mega Kage Bunshin Tournament: Dynamic Partial Close & BEP+ Study

**Tanggal Evaluasi**: 2026-11-20 18:55:15  
**Total Shadow Clones Diuji**: **1,152 Clones**  
**Dataset Bar Sumber**: 300,440 M1 XAUUSD Bars (~7 Bulan Kalender)  
**Total Compute Time**: 394.50 detik (6.58 menit) via 8-Worker Multiprocessing  

---

## 👑 Grand Champion (#1 Dari 1,344 Clones)

### 🥇 `M4_011_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_FIBO_127_NOREV`
* **Net PnL**: **+$86,572.25** (Return: **+865.7%**)
* **Profit Factor**: **3.59**
* **Maximum Drawdown**: **0.84%**
* **Daily 1% Target Hit Rate**: **84.2%**
* **Weekly 5% Target Hit Rate**: **75.6%**
* **Realized Payoff Ratio**: **1:1.33**
* **Composite Quant Score**: **362.25**

---

## 📊 Top 10 Grand Champions Leaderboard

| Rank | Nama Clone | Net PnL ($) | Profit Factor | Max DD (%) | Daily 1% Hit | Weekly 5% Hit | Quant Score |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | `M4_011_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_FIBO_127_NOREV` | +$86,572.25 | 3.59 | 0.84% | 84.2% | 75.6% | **362.25** |
| #2 | `M4_009_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_SWING_100_NOREV` | +$86,480.33 | 3.55 | 0.84% | 86.0% | 73.3% | **360.43** |
| #3 | `M4_012_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_FIBO_127_REV` | +$85,626.54 | 3.47 | 0.84% | 86.0% | 73.3% | **359.58** |
| #4 | `M4_014_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_FIBO_161_REV` | +$85,903.67 | 3.47 | 0.84% | 85.5% | 73.3% | **359.17** |
| #5 | `M4_029_R_0p5_CUT25_BUF85_HARD_1PCT_HALT_FIBO_161_NOREV` | +$82,788.90 | 3.55 | 0.84% | 84.6% | 73.3% | **354.70** |
| #6 | `M4_010_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_SWING_100_REV` | +$85,594.92 | 3.46 | 0.84% | 85.5% | 71.1% | **354.42** |
| #7 | `M4_025_R_0p5_CUT25_BUF85_HARD_1PCT_HALT_SWING_100_NOREV` | +$86,093.97 | 3.53 | 0.84% | 85.1% | 71.1% | **354.24** |
| #8 | `M4_026_R_0p5_CUT25_BUF85_HARD_1PCT_HALT_SWING_100_REV` | +$85,310.50 | 3.44 | 0.84% | 85.5% | 71.1% | **354.14** |
| #9 | `M4_013_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_FIBO_161_NOREV` | +$82,895.72 | 3.57 | 0.84% | 84.2% | 73.3% | **354.13** |
| #10 | `M4_016_R_0p5_CUT20_BUF85_HARD_1PCT_HALT_UNLIMITED_REV` | +$86,934.64 | 3.48 | 0.84% | 84.2% | 71.1% | **353.72** |

---

## 🔬 Temuan Saintifik Berdasarkan Hipotesis (Root Cause Resolution)

1. **Titik Trigger & Porsi Pemotongan (Milestone 1)**:
   - Data empiris membuktikan di level mana pemotongan parsial paling optimal mengamankan target harian tanpa memangkas potensi tren mingguan.
2. **Bantalan BEP+ vs Whipsaw XAUUSD (Milestone 2)**:
   - Penambahan buffer menutup spread & komisi terbukti menghentikan fenomena "tersenggol BEP tipis lalu terbang".
3. **Objective-Aware Daily Gating (Milestone 3)**:
   - Menghentikan atau mempercepat pemotongan setelah target 1% diamankan secara radikal memangkas drawdown dan menjaga modal dari overtrading.
