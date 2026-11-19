# 🥷 HASIL TOURNAMENT: HYBRIDISASI OPSI A OR OPSI B DENGAN TUJUAN PROFIT HARIAN & MINGGUAN
**Tanggal Backtest**: 2026-11-19 11:55:23
**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)
**Target Objektif**: 1% Profit/Hari & 5% Profit/Minggu

## 1. Tabel Komparasi Penuh
| Model ID | Deskripsi Strategi | PF | Max DD | Net PnL ($) | **Daily 1% Hit** | **Weekly 5% Hit** | Counter Trades | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BASELINE_STATUS_QUO` | Baseline M1: Gembok total saat dual HTF sepakat searah | **1.41** | **5.06%** | **$30,420.58** | **26.7%** | **20.0%** | 0 | $0.00 |
| `OPSI_A_STANDALONE` | Opsi A Murni: (M1 + M5 Confluence Saja, Risk 0.5x) | **1.41** | **5.50%** | **$34,335.38** | **29.0%** | **17.8%** | 3029 | $2,185.65 |
| `OPSI_B_STANDALONE` | Opsi B Murni: (M1..M3 + M5/M15 Confluence OR M15/M30 BOS, Risk 0.5x) | **1.41** | **7.31%** | **$36,230.96** | **30.3%** | **22.2%** | 4036 | $3,849.54 |
| `HYBRID_1_PURE_OR_FLAT` | Hybrid 1: Opsi A OR Opsi B (Flat 0.5x Risk) | **1.41** | **7.31%** | **$36,230.96** | **30.3%** | **22.2%** | 4036 | $3,849.54 |
| `HYBRID_2_DYNAMIC_WEIGHTED` | Hybrid 2: Opsi A -> 0.5x Risk | Opsi B -> 0.25x Risk | **1.42** | **7.03%** | **$35,533.33** | **29.9%** | **22.2%** | 4052 | $3,896.49 |
| `HYBRID_3_STATE_GATED_OR` | Hybrid 3: Red Day -> Opsi A Only | Green Day -> Opsi A OR Opsi B | **1.40** | **7.00%** | **$34,009.37** | **29.9%** | **20.0%** | 3648 | $2,365.15 |
| `HYBRID_4_ASYMMETRIC_TP_OR` | Hybrid 4: Opsi A -> Full EQ TP | Opsi B -> Quick Shallow TP (0.382) | **1.40** | **5.59%** | **$35,378.30** | **30.8%** | **22.2%** | 4224 | $3,807.09 |
| `HYBRID_5_MASTER_CHAMPION` | Hybrid 5 (Master): Red Day (Opsi A 0.35x) + Green Day (Opsi A 0.5x OR Opsi B 0.25x Shallow) | **1.41** | **6.59%** | **$34,507.49** | **28.5%** | **22.2%** | 3834 | $2,164.82 |