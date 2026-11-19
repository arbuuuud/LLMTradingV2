# 🎯 LAPORAN VALIDASI EMPIRIS: LOGIKA OBJECTIVE-AWARE ADAPTIVE UNLOCK
**Tanggal Audit**: 2026-11-19 11:44:59
**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)
**Target Objektif**: 1% Profit/Hari & 5% Profit/Minggu

## 1. Tabel Komparasi Head-to-Head
| Model ID | Deskripsi Strategi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Weekly 5% Hit | Counter PnL ($) | Counter WR |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BASELINE_M1` | Baseline M1 (Gembok total saat dual-HTF searah) | **1.41** | **5.06%** | **$30,420.58** | **26.7%** | **20.0%** | $0.00 | 0.0% |
| `ADAPTIVE_M1_STANDARD_1PCT` | Adaptive Unlock M1 (Kunci buka saat hunting < 1.0%, risk 0.5x, lock at +1.0% / -0.5%) | **1.41** | **7.31%** | **$36,230.96** | **30.3%** | **22.2%** | $3,849.54 | 48.2% |
| `ADAPTIVE_M1_BOS_ONLY_GUARD` | Adaptive Unlock M1 (Hanya buka jika M15/M30 BOS valid, lock at +1.0%, risk 0.5x) | **1.38** | **5.81%** | **$30,619.03** | **26.7%** | **20.0%** | $515.08 | 50.7% |
| `ADAPTIVE_M1_M1_M5_NESTED_ONLY` | Adaptive Unlock M1 (Hanya buka jika M1+M5 Nested Confluence, lock at +1.0%, risk 0.5x) | **1.41** | **5.50%** | **$34,335.38** | **29.0%** | **17.8%** | $2,185.65 | 45.0% |
| `ADAPTIVE_M1_SHALLOW_TP` | Adaptive Unlock M1 dengan Shallow TP (0.382 Mean Reversion Quick Escape) | **1.38** | **9.07%** | **$32,645.37** | **28.5%** | **22.2%** | $2,492.50 | 54.6% |
| `ADAPTIVE_M1_GREED_1_5PCT` | Adaptive Unlock M1 (Lock target di 1.5% profit harian) | **1.40** | **7.89%** | **$36,154.55** | **29.9%** | **24.4%** | $3,950.73 | 48.1% |
| `ADAPTIVE_M5_INTRADAY` | Adaptive Unlock M5 (M5 Execution dengan Nested/BOS, lock at +1.0%) | **4.21** | **9.83%** | **$141,139.15** | **17.6%** | **33.3%** | $38,921.42 | 34.6% |