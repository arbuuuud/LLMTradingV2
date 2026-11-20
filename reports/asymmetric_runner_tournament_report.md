# 🥋 Kage Bunshin Tournament Report: Asymmetric TP & Whale Runner Architecture

**Tanggal Pengujian:** 2026-11-20 17:13:24  
**Dataset:** 300,440 M1 XAUUSD Bars (~1.5 Tahun Data M1 Tanpa Celah)  
**Starting Balance:** $10,000.00 | **Risk Baseline:** 0.50% per trade ($50.00)  
**Total Clones Dievaluasi:** 12 Shadow Clones  

---

## 🏆 HASIL JUARA UMUM (CHAMPION)

### **🥇 CLONE_02_SWING100_AUTO_BEP**
* **Konsep:** Fixed Swing 100% Runner with Auto-BEP upon TP1.
* **Net PnL:** **$+59,828.47** (vs Baseline $+60,898.03 -> **-1.8%**)
* **Profit Factor:** **1.77** (vs Baseline 1.72)
* **Max Drawdown:** **2.09%** (vs Baseline 2.12% -> Delta -0.03%)
* **Realized R:R:** **1:2.22** (Avg Win: +2.22R | Avg Loss: -1.0R)
* **Weekly 5% Hit Rate:** **40.0%** (vs Baseline 35.6% -> Delta +4.4%)
* **Daily 1% Hit Rate:** **38.9%** (vs Baseline 38.9% -> Delta +0.0%)
* **Daily Loss Breach (<-1.0%):** **0.9%** (vs Baseline 0.9%)
* **Quant Composite Score:** **191.29** (vs Baseline 183.51)

---

## 📊 LEADERBOARD LENGKAP 12 SHADOW CLONES

| Rank | Clone Name | Net PnL ($) | Profit Factor | Max DD (%) | Realized R:R | Daily 1% Hit | Weekly 5% Hit | BEP Auto-Locks | Quant Score |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **#1** | `CLONE_02_SWING100_AUTO_BEP` | $+59,828.47 | 1.77 | 2.09% | 1:2.22 | 38.9% | 40.0% | 681 | **191.29** |
| **#2** | `CLONE_08_REGIME_AWARE_SWING100` | $+61,578.67 | 1.78 | 2.09% | 1:2.18 | 36.7% | 40.0% | 513 | **189.74** |
| **#3** | `CLONE_03_FIBO127_AUTO_BEP` | $+59,795.86 | 1.80 | 2.04% | 1:2.26 | 37.6% | 37.8% | 662 | **186.22** |
| **#4** | `CLONE_01_SWING100_NO_BEP` | $+58,415.45 | 1.72 | 2.09% | 1:2.25 | 38.5% | 37.8% | 0 | **184.88** |
| **#5** | `CLONE_11_REGIME_AWARE_SWING100_LOCK0p5R` | $+59,620.72 | 1.75 | 2.09% | 1:2.17 | 37.1% | 37.8% | 509 | **183.98** |
| **#6** | `CLONE_00_BASELINE_DEC043` | $+60,898.03 | 1.72 | 2.12% | 1:2.07 | 38.9% | 35.6% | 0 | **183.51** |
| **#7** | `CLONE_09_REGIME_AWARE_FIBO127` | $+61,342.76 | 1.80 | 2.04% | 1:2.22 | 35.7% | 35.6% | 508 | **180.51** |
| **#8** | `CLONE_06_SASUKE_REVERSAL_FORCE_TP` | $+60,964.36 | 1.76 | 2.07% | 1:2.02 | 33.9% | 35.6% | 590 | **176.18** |
| **#9** | `CLONE_04_FIBO161_AUTO_BEP` | $+50,548.69 | 1.73 | 2.03% | 1:2.22 | 35.3% | 31.1% | 598 | **160.13** |
| **#10** | `CLONE_10_REGIME_AWARE_SASUKE_MASTER` | $+37,271.11 | 1.50 | 2.07% | 1:1.91 | 30.8% | 22.2% | 1 | **122.23** |
| **#11** | `CLONE_07_SASUKE_MASTER_FULL` | $+33,916.14 | 1.46 | 2.09% | 1:1.87 | 28.1% | 20.0% | 2 | **110.39** |
| **#12** | `CLONE_05_SASUKE_STEPPED_TRAILING` | $+32,438.08 | 1.45 | 2.15% | 1:1.88 | 27.6% | 20.0% | 2 | **106.84** |

---

## 🔍 TEMUAN KUANTITATIF & PEMBELAJARAN ARSITEKTURAL

1. **Dampak Nyata Asymmetric TP pada R:R Riil**:
   * Pada Baseline DEC-043, realized R:R berada di kisaran **1:2.07**.
   * Dengan melepas L3 & L4 sebagai runner (menuju Swing 100% atau Trailing Sasuke), realized R:R melonjak menjadi **1:2.22**!
2. **Peran Kritis Auto-BEP**:
   * Memindahkan SL sisa runner ke BEP begitu L1 & L2 menyentuh Equilibrium 50% menyelamatkan profit harian tanpa mengorbankan modal.
3. **Regime-Aware Protection (Pemisahan Trend vs Counter-Trend)**:
   * Mengunci runner hanya untuk setup searah tren (Trend-Following) dan memaksa counter-trend tetap panen cepat (Full TP 50%/38.2%) terbukti melindungi akun dari reversal ganas arus D1/H4.

---
*Laporan di-generate secara otomatis oleh Naruto Kage Bunshin Backtesting Framework.*
