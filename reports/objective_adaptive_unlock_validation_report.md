# 🎯 LAPORAN VALIDASI EMPIRIS: LOGIKA OBJECTIVE-AWARE ADAPTIVE UNLOCK
**Tanggal Audit**: 2026-11-19 11:49:30
**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)
**Target Objektif**: 1% Profit/Hari & 5% Profit/Minggu

## 1. Tabel Komparasi Head-to-Head
| Model ID | Deskripsi Strategi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Weekly 5% Hit | Counter PnL ($) | Counter WR |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BASELINE_M1` | Baseline M1 (Gembok total saat dual-HTF searah) | **1.41** | **5.06%** | **$30,420.58** | **26.7%** | **20.0%** | $0.00 | 0.0% |
| `ADAPTIVE_M1_M1_M5_ONLY` | Opsi A Murni: (M1 + M5 Nested Confluence Saja, Risk 0.5x) | **1.41** | **5.50%** | **$34,335.38** | **29.0%** | **17.8%** | $2,185.65 | 45.0% |
| `ADAPTIVE_M1_BOS_M15_ONLY` | Opsi B Murni: (M15 BOS Saja, Risk 0.5x) | **1.38** | **5.81%** | **$30,619.03** | **26.7%** | **20.0%** | $515.08 | 50.7% |
| `ADAPTIVE_M1_M1M5_OR_M15BOS` | Kombinasi OR: (M1+M5 Nested) OR (M15 BOS) - Risk 0.5x | **1.38** | **7.91%** | **$32,530.74** | **28.5%** | **20.0%** | $1,021.59 | 46.9% |
| `ADAPTIVE_M1_M1M5_OR_M15M30BOS` | Kombinasi OR Lebar: (M1+M5 Nested) OR (M15/M30 BOS) - Risk 0.5x | **1.40** | **8.03%** | **$34,749.78** | **29.9%** | **22.2%** | $3,101.61 | 47.6% |
| `ADAPTIVE_M1_M1M5_AND_M15BOS` | Kombinasi AND (Strict): (M1+M5 Nested) AND (M15 BOS) - Risk 0.5x | **1.38** | **5.36%** | **$29,249.69** | **26.7%** | **15.6%** | $-382.04 | 43.6% |
| `ADAPTIVE_M1_TIERED_DYNAMIC_RISK` | Tiered Dynamic: Jika Kedua Syarat = 0.5x, Jika Salah Satu = 0.25x Risk | **1.39** | **5.01%** | **$31,712.59** | **27.6%** | **22.2%** | $848.38 | 47.3% |