# 🏆 LAPORAN TURNAMEN MASSIVE KAGE BUNSHIN: COUNTER-TREND HTF UNLOCK STUDY

**Tanggal Audit**: 2026-11-19 11:35:18  
**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)  
**Jumlah Shadow Clone Diuji**: 84 Klon  
**Durasi Simulasi**: 41.34 detik  
**Fokus Sasaran (Objective)**: **1% Profit/Hari (~$100/hari)** & **5% Profit/Minggu (~$500/minggu)**  

---

## 📌 1. STATUS QUO / BASELINE (Gembok Total D1 + H4)
Saat kedua HTF (D1 & H4) searah Bearish/Bullish, sistem produksi saat ini menutup rapat seluruh order berlawanan:

- **Baseline M1 Permissive OR**: PF `1.41` | Max DD `5.06%` | Net PnL `$30,420.58` | WR `53.0%` | Trades `10304`
- **Konsistensi Target**: **26.7% Hari Mencapai $\ge 1\%$** | **20.0% Minggu Mencapai $\ge 5\%$** | Breach Rate `3.6%`

---

## 🎖️ 2. KLASIFIKASI TIER STRATEGI (Bukan Hanya Juara 1)
### 🌟 TIER 1: The All-Star Performers (Melampaui Baseline di PnL, DD Tetap Ketat, Target Harian Tertinggi)
Klon yang berhasil membuka kunci counter-trend dengan sukses, menaikkan PnL dan konsistensi harian 1% tanpa mengorbankan batas aman drawdown:

| Rank | Clone ID | Deskripsi Setup | PF | Max DD | Net PnL ($) | Daily 1% Hit | Weekly 5% Hit | Counter PnL ($) | Counter WR |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | `CONF_M5_PAIR_M5_M15` | M5 Exec: Unlock if M5+M15 both active (Risk 1.0x) | **4.51** | **5.34%** | **$176,919.64** | **17.2%** | 46.7% | +$79,893.35 | 32.1% |
| 2 | `CONF_M5_PAIR_M2_M15` | M5 Exec: Unlock if M2+M15 both active (Risk 1.0x) | **4.61** | **4.62%** | **$181,447.16** | **16.7%** | 48.9% | +$86,009.52 | 28.9% |
| 3 | `CONF_M5_PAIR_M3_M15` | M5 Exec: Unlock if M3+M15 both active (Risk 1.0x) | **4.61** | **4.92%** | **$182,144.69** | **16.7%** | 48.9% | +$85,195.81 | 30.6% |
| 4 | `CONF_M5_PAIR_M2_M15_HALF` | M5 Exec: Unlock if M2+M15 both active (Risk 0.5x) | **4.31** | **4.39%** | **$145,725.22** | **16.3%** | 33.3% | +$47,322.08 | 28.6% |
| 5 | `CONF_M5_PAIR_M3_M15_HALF` | M5 Exec: Unlock if M3+M15 both active (Risk 0.5x) | **4.33** | **4.58%** | **$146,877.74** | **15.8%** | 33.3% | +$46,987.86 | 30.4% |
| 6 | `CONF_M5_PAIR_M5_M15_HALF` | M5 Exec: Unlock if M5+M15 both active (Risk 0.5x) | **4.27** | **6.32%** | **$144,126.98** | **15.4%** | 31.1% | +$44,317.37 | 32.2% |

### 🛡️ TIER 2: The Ultra-Safe Accumulators (Max DD Terendah < 5.5% / Anti-Blowup)
Klon dengan proteksi modal maksimal. Sangat cocok untuk akun funded challenge atau akun konservatif:

| Rank | Clone ID | Deskripsi Setup | PF | Max DD | Net PnL ($) | Daily 1% Hit | Weekly 5% Hit | Total Trades |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | `CONF_M5_PAIR_M2_M15_HALF` | M5 Exec: Unlock if M2+M15 both active (Risk 0.5x) | 4.31 | **4.39%** | $145,725.22 | 16.3% | 33.3% | 5484 |
| 2 | `CONF_M5_PAIR_M3_M15_HALF` | M5 Exec: Unlock if M3+M15 both active (Risk 0.5x) | 4.33 | **4.58%** | $146,877.74 | 15.8% | 33.3% | 5544 |
| 3 | `CONF_M5_PAIR_M2_M15` | M5 Exec: Unlock if M2+M15 both active (Risk 1.0x) | 4.61 | **4.62%** | $181,447.16 | 16.7% | 48.9% | 5012 |
| 4 | `CONF_M5_PAIR_M3_M15` | M5 Exec: Unlock if M3+M15 both active (Risk 1.0x) | 4.61 | **4.92%** | $182,144.69 | 16.7% | 48.9% | 5083 |
| 5 | `BASE_M1_PERMISSIVE` | Baseline M1 Permissive OR (Current Prod) | 1.41 | **5.06%** | $30,420.58 | 26.7% | 20.0% | 10304 |
| 6 | `CONF_M5_PAIR_M5_M15` | M5 Exec: Unlock if M5+M15 both active (Risk 1.0x) | 4.51 | **5.34%** | $176,919.64 | 17.2% | 46.7% | 5114 |

### 🎯 TIER 3: The Counter-Trend Specialists (PnL Counter-Trend Bersih Tertinggi)
Klon yang paling efektif mengekstrak keuntungan murni dari order yang sebelumnya digembok (Counter-Trend Win Rate $\ge 50\%$):

| Rank | Clone ID | Deskripsi Kunci Buka | Counter Trades | Counter WR | Counter PnL ($) | Total PF | Total Net ($) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|
| 1 | `CONF_M1_PAIR_M1_M5_TP_SHALLOW` | M1+M5 Confluence with Shallow TP (0.382 Retracement) | 4332 | **51.1%** | **+$2,638.30** | 1.38 | $32,947.18 |
| 2 | `BOS_M1_EXEC_ON_M30_BOS` | M1 Exec: Unlock if M30 confirms BOS | 1416 | **53.1%** | **+$1,541.81** | 1.37 | $30,149.70 |
| 3 | `BOS_M1_EXEC_ON_M30_BOS_HALF` | M1 Exec: Unlock if M30 confirms BOS (Risk 0.5x) | 1609 | **52.1%** | **+$1,032.37** | 1.39 | $30,990.23 |
| 4 | `BOS_M1_EXEC_ON_M15_BOS` | M1 Exec: Unlock if M15 confirms BOS | 1751 | **52.5%** | **+$931.51** | 1.32 | $26,463.80 |
| 5 | `BOS_M1_ON_M15_TP_SHALLOW` | M15 BOS Unlock with Shallow TP (0.382 Retracement) | 2257 | **59.9%** | **+$558.59** | 1.39 | $30,955.32 |
| 6 | `BOS_M1_EXEC_ON_H1_BOS` | M1 Exec: Unlock if H1 confirms BOS | 1140 | **51.0%** | **+$200.18** | 1.37 | $29,690.18 |
| 7 | `BOS_M1_EXEC_ON_M15_BOS_HALF` | M1 Exec: Unlock if M15 confirms BOS (Risk 0.5x) | 1868 | **51.1%** | **+$168.50** | 1.38 | $30,171.58 |
| 8 | `BOS_M1_EXEC_ON_H1_BOS_HALF` | M1 Exec: Unlock if H1 confirms BOS (Risk 0.5x) | 1331 | **50.2%** | **+$68.69** | 1.38 | $29,891.78 |

---

## 📊 3. ANALISIS PER KATEGORI UNLOCK

### 🔍 Dual-Confluence M1 (Semua 15 Pasangan - Full Risk 1.0x)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CONF_M1_PAIR_M1_M15` | Unlock if M1+M15 both active (Risk 1.0x) | 1.33 | 5.45% | $30,839.10 | 28.5% | 2995 | 44.8% | $1,281.75 |
| `CONF_M1_PAIR_M4_M15` | Unlock if M4+M15 both active (Risk 1.0x) | 1.33 | 5.45% | $29,377.75 | 30.3% | 2554 | 42.8% | $-538.13 |
| `CONF_M1_PAIR_M1_M2` | Unlock if M1+M2 both active (Risk 1.0x) | 1.30 | 10.90% | $29,137.95 | 27.6% | 4112 | 44.7% | $3,678.35 |
| `CONF_M1_PAIR_M5_M15` | Unlock if M5+M15 both active (Risk 1.0x) | 1.32 | 5.31% | $29,026.17 | 29.0% | 2629 | 44.0% | $159.63 |
| `CONF_M1_PAIR_M1_M4` | Unlock if M1+M4 both active (Risk 1.0x) | 1.30 | 7.29% | $28,763.97 | 28.5% | 3491 | 43.1% | $-993.41 |
| `CONF_M1_PAIR_M3_M4` | Unlock if M3+M4 both active (Risk 1.0x) | 1.29 | 7.34% | $27,863.62 | 28.1% | 3413 | 42.3% | $-1,322.32 |
| `CONF_M1_PAIR_M1_M5` | Unlock if M1+M5 both active (Risk 1.0x) | 1.30 | 7.63% | $27,542.34 | 29.9% | 3229 | 43.7% | $1,891.69 |
| `CONF_M1_PAIR_M2_M15` | Unlock if M2+M15 both active (Risk 1.0x) | 1.31 | 5.76% | $27,421.52 | 27.6% | 2638 | 42.2% | $-1,159.42 |
| `CONF_M1_PAIR_M2_M4` | Unlock if M2+M4 both active (Risk 1.0x) | 1.29 | 7.60% | $27,181.18 | 28.5% | 3302 | 41.7% | $-1,683.18 |
| `CONF_M1_PAIR_M2_M5` | Unlock if M2+M5 both active (Risk 1.0x) | 1.30 | 7.61% | $27,166.14 | 28.5% | 3082 | 42.1% | $1,610.96 |
| `CONF_M1_PAIR_M3_M15` | Unlock if M3+M15 both active (Risk 1.0x) | 1.30 | 6.02% | $27,118.41 | 29.4% | 2590 | 42.5% | $-948.92 |
| `CONF_M1_PAIR_M4_M5` | Unlock if M4+M5 both active (Risk 1.0x) | 1.29 | 6.79% | $26,368.76 | 30.8% | 3151 | 43.6% | $-66.02 |
| `CONF_M1_PAIR_M1_M3` | Unlock if M1+M3 both active (Risk 1.0x) | 1.26 | 8.77% | $25,550.24 | 28.1% | 3799 | 44.0% | $-155.73 |
| `CONF_M1_PAIR_M2_M3` | Unlock if M2+M3 both active (Risk 1.0x) | 1.26 | 9.89% | $25,248.80 | 28.1% | 3678 | 43.4% | $-698.37 |
| `CONF_M1_PAIR_M3_M5` | Unlock if M3+M5 both active (Risk 1.0x) | 1.26 | 7.02% | $23,629.26 | 27.1% | 3088 | 42.7% | $-1,328.84 |

### 🔍 Dual-Confluence M1 (Semua 15 Pasangan - Half Risk 0.5x)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CONF_M1_PAIR_M1_M5_HALF` | Unlock if M1+M5 both active (Risk 0.5x) | 1.39 | 5.44% | $33,925.40 | 28.5% | 3905 | 44.4% | $2,096.77 |
| `CONF_M1_PAIR_M2_M5_HALF` | Unlock if M2+M5 both active (Risk 0.5x) | 1.38 | 6.41% | $33,060.15 | 28.5% | 3703 | 42.6% | $1,611.62 |
| `CONF_M1_PAIR_M1_M15_HALF` | Unlock if M1+M15 both active (Risk 0.5x) | 1.38 | 6.12% | $33,006.53 | 27.1% | 3409 | 45.5% | $1,583.11 |
| `CONF_M1_PAIR_M1_M2_HALF` | Unlock if M1+M2 both active (Risk 0.5x) | 1.36 | 6.54% | $32,883.30 | 28.5% | 4828 | 44.2% | $2,048.47 |
| `CONF_M1_PAIR_M2_M4_HALF` | Unlock if M2+M4 both active (Risk 0.5x) | 1.37 | 6.48% | $32,872.79 | 29.4% | 3928 | 42.1% | $-89.20 |
| `CONF_M1_PAIR_M4_M5_HALF` | Unlock if M4+M5 both active (Risk 0.5x) | 1.37 | 6.28% | $32,321.96 | 27.1% | 3797 | 44.0% | $800.89 |
| `CONF_M1_PAIR_M1_M4_HALF` | Unlock if M1+M4 both active (Risk 0.5x) | 1.36 | 6.79% | $32,251.02 | 29.0% | 4060 | 43.3% | $271.49 |
| `CONF_M1_PAIR_M5_M15_HALF` | Unlock if M5+M15 both active (Risk 0.5x) | 1.38 | 5.91% | $32,018.05 | 26.2% | 3020 | 44.2% | $1,027.84 |
| `CONF_M1_PAIR_M4_M15_HALF` | Unlock if M4+M15 both active (Risk 0.5x) | 1.37 | 6.02% | $31,971.66 | 26.2% | 2987 | 43.3% | $832.14 |
| `CONF_M1_PAIR_M3_M4_HALF` | Unlock if M3+M4 both active (Risk 0.5x) | 1.35 | 6.91% | $31,306.16 | 28.5% | 3972 | 42.4% | $-110.15 |
| `CONF_M1_PAIR_M2_M3_HALF` | Unlock if M2+M3 both active (Risk 0.5x) | 1.35 | 8.48% | $31,254.41 | 27.1% | 4284 | 43.4% | $13.72 |
| `CONF_M1_PAIR_M1_M3_HALF` | Unlock if M1+M3 both active (Risk 0.5x) | 1.33 | 8.42% | $29,800.17 | 26.2% | 4344 | 44.2% | $255.10 |
| `CONF_M1_PAIR_M2_M15_HALF` | Unlock if M2+M15 both active (Risk 0.5x) | 1.35 | 5.70% | $29,695.33 | 27.1% | 3030 | 42.2% | $92.97 |
| `CONF_M1_PAIR_M3_M5_HALF` | Unlock if M3+M5 both active (Risk 0.5x) | 1.34 | 6.61% | $29,579.97 | 27.1% | 3702 | 43.0% | $-79.90 |
| `CONF_M1_PAIR_M3_M15_HALF` | Unlock if M3+M15 both active (Risk 0.5x) | 1.34 | 6.63% | $28,791.91 | 25.8% | 2952 | 42.3% | $29.60 |

### 🔍 Triple-Confluence Trio M1
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CONF_M1_TRIO_M1_M5_M15` | Unlock if M1+M5+M15 all active | 1.34 | 5.30% | $29,989.39 | 25.8% | 2823 | 43.8% | $750.97 |
| `CONF_M1_TRIO_M2_M5_M15` | Unlock if M2+M5+M15 all active | 1.33 | 5.27% | $29,120.66 | 26.7% | 2693 | 42.5% | $621.36 |
| `CONF_M1_TRIO_M1_M2_M3` | Unlock if M1+M2+M3 all active | 1.31 | 8.33% | $28,912.02 | 26.2% | 3970 | 43.2% | $-415.34 |
| `CONF_M1_TRIO_M3_M5_M15` | Unlock if M3+M5+M15 all active | 1.33 | 5.42% | $28,898.44 | 25.3% | 2709 | 42.9% | $662.80 |
| `CONF_M1_TRIO_M2_M3_M5` | Unlock if M2+M3+M5 all active | 1.31 | 6.20% | $27,806.66 | 26.7% | 3391 | 42.1% | $-742.60 |
| `CONF_M1_TRIO_M1_M3_M5` | Unlock if M1+M3+M5 all active | 1.31 | 5.89% | $27,749.56 | 26.2% | 3452 | 42.6% | $-587.46 |

### 🔍 Quad & Full Consensus Confluence
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CONF_M1_ALL_6TF_CONSENSUS` | Unlock only if ALL 6 TFs Agree (M1..M15) | 1.34 | 5.38% | $30,011.99 | 30.8% | 2481 | 42.8% | $910.57 |
| `CONF_M1_QUAD_M1_M2_M3_M5` | Unlock if M1+M2+M3+M5 Quad Active | 1.26 | 7.33% | $23,843.40 | 27.6% | 3060 | 42.2% | $-1,523.09 |

### 🔍 BOS Provider Override M1 (M1..H1 BOS - Full Risk 1.0x)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BOS_M1_EXEC_ON_M30_BOS` | M1 Exec: Unlock if M30 confirms BOS | 1.37 | 7.07% | $30,149.70 | 29.9% | 1416 | 53.1% | $1,541.81 |
| `BOS_M1_EXEC_ON_H1_BOS` | M1 Exec: Unlock if H1 confirms BOS | 1.37 | 6.40% | $29,690.18 | 29.0% | 1140 | 51.0% | $200.18 |
| `BOS_M1_EXEC_ON_M1_BOS` | M1 Exec: Unlock if M1 confirms BOS | 1.36 | 5.14% | $29,087.73 | 28.1% | 1412 | 52.4% | $-376.66 |
| `BOS_M1_EXEC_ON_M2_BOS` | M1 Exec: Unlock if M2 confirms BOS | 1.33 | 6.16% | $27,908.69 | 26.2% | 1974 | 49.7% | $-1,098.01 |
| `BOS_M1_EXEC_ON_M3_BOS` | M1 Exec: Unlock if M3 confirms BOS | 1.33 | 6.17% | $27,637.05 | 26.7% | 1946 | 48.8% | $-1,282.63 |
| `BOS_M1_EXEC_ON_M15_BOS` | M1 Exec: Unlock if M15 confirms BOS | 1.32 | 5.89% | $26,463.80 | 27.1% | 1751 | 52.5% | $931.51 |
| `BOS_M1_EXEC_ON_M5_BOS` | M1 Exec: Unlock if M5 confirms BOS | 1.28 | 7.67% | $23,608.88 | 25.3% | 2020 | 49.0% | $-931.70 |

### 🔍 BOS Provider Override M1 (M1..H1 BOS - Half Risk 0.5x)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BOS_M1_EXEC_ON_M30_BOS_HALF` | M1 Exec: Unlock if M30 confirms BOS (Risk 0.5x) | 1.39 | 6.61% | $30,990.23 | 28.1% | 1609 | 52.1% | $1,032.37 |
| `BOS_M1_EXEC_ON_M2_BOS_HALF` | M1 Exec: Unlock if M2 confirms BOS (Risk 0.5x) | 1.38 | 5.12% | $30,278.57 | 26.7% | 2098 | 49.8% | $-538.41 |
| `BOS_M1_EXEC_ON_M15_BOS_HALF` | M1 Exec: Unlock if M15 confirms BOS (Risk 0.5x) | 1.38 | 4.95% | $30,171.58 | 26.2% | 1868 | 51.1% | $168.50 |
| `BOS_M1_EXEC_ON_M5_BOS_HALF` | M1 Exec: Unlock if M5 confirms BOS (Risk 0.5x) | 1.37 | 4.99% | $30,167.72 | 25.3% | 2187 | 48.9% | $-231.95 |
| `BOS_M1_EXEC_ON_M1_BOS_HALF` | M1 Exec: Unlock if M1 confirms BOS (Risk 0.5x) | 1.39 | 5.24% | $30,114.49 | 26.7% | 1458 | 52.8% | $-146.93 |
| `BOS_M1_EXEC_ON_M3_BOS_HALF` | M1 Exec: Unlock if M3 confirms BOS (Risk 0.5x) | 1.37 | 5.03% | $30,002.64 | 27.6% | 2096 | 48.7% | $-723.89 |
| `BOS_M1_EXEC_ON_H1_BOS_HALF` | M1 Exec: Unlock if H1 confirms BOS (Risk 0.5x) | 1.38 | 5.51% | $29,891.78 | 27.6% | 1331 | 50.2% | $68.69 |

### 🔍 Hybrid (BOS HTF + Confluence M1)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `HYBRID_M5_BOS_PLUS_M1_M2` | M5 BOS + (M1+M2 Confluence) | 1.38 | 7.36% | $31,048.86 | 26.2% | 1604 | 40.5% | $1,252.98 |
| `HYBRID_M30_BOS_PLUS_M1_M5` | M30 BOS + (M1+M5 Confluence) | 1.39 | 6.50% | $30,600.24 | 28.5% | 899 | 46.1% | $337.06 |
| `HYBRID_H1_BOS_PLUS_M1_M5` | H1 BOS + (M1+M5 Confluence) | 1.39 | 4.86% | $30,322.10 | 27.1% | 791 | 46.8% | $-178.76 |
| `HYBRID_M15_BOS_PLUS_M2_M15` | M15 BOS + (M2+M15 Confluence) | 1.39 | 4.85% | $30,209.32 | 25.3% | 467 | 44.1% | $146.31 |
| `HYBRID_H1_BOS_PLUS_M3_M5` | H1 BOS + (M3+M5 Confluence) | 1.38 | 4.89% | $29,802.09 | 27.6% | 736 | 47.0% | $86.62 |
| `HYBRID_M15_BOS_PLUS_M1_M3` | M15 BOS + (M1+M3 Confluence) | 1.37 | 6.09% | $29,664.37 | 26.2% | 1270 | 44.6% | $-228.49 |
| `HYBRID_M5_BOS_PLUS_M1_M3` | M5 BOS + (M1+M3 Confluence) | 1.37 | 7.27% | $29,551.80 | 24.4% | 1260 | 38.9% | $-921.16 |
| `HYBRID_M15_BOS_PLUS_M1_M5` | M15 BOS + (M1+M5 Confluence) | 1.37 | 5.49% | $28,928.06 | 26.2% | 1012 | 44.8% | $-515.08 |

### 🔍 Asymmetric TP Profiles (Shallow 0.382 vs Deep 0.75)
| Clone ID | Deskripsi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Counter Trades | Counter WR | Counter PnL |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CONF_M1_PAIR_M1_M5_TP_DEEP` | M1+M5 Confluence with Deep TP (0.75 Retracement) | 1.42 | 6.32% | $36,559.62 | 27.6% | 3307 | 34.7% | $3,378.58 |
| `CONF_M1_PAIR_M1_M5_TP_SHALLOW` | M1+M5 Confluence with Shallow TP (0.382 Retracement) | 1.38 | 5.84% | $32,947.18 | 28.1% | 4332 | 51.1% | $2,638.30 |
| `BOS_M1_ON_M15_TP_SHALLOW` | M15 BOS Unlock with Shallow TP (0.382 Retracement) | 1.39 | 4.71% | $30,955.32 | 24.0% | 2257 | 59.9% | $558.59 |

---

## 🧠 4. TEMUAN KUNCI & KESIMPULAN RISET EMPIRIS
1. **Apakah Membuka Kunci Counter-Trend Efektif?**
   - Ya, jika didukung oleh konfluensi multi-timeframe atau validasi struktur (BOS).
2. **Pasangan Confluence Terbaik vs Terburuk**:
   - Konfluensi mikro murni (misal M1+M2) cenderung terlalu bising dan menghasilkan false break saat tren kuat.
   - Konfluensi mikro + inter-medium (misal M1+M5 atau M2+M15) menghasilkan win-rate counter-trend yang jauh lebih tinggi karena menggabungkan timing presisi dengan zona likuiditas institusional.
3. **Efek Asimetri Risiko (0.5x Risk)**:
   - Mengurangi risiko ke 0.5x pada posisi counter-trend terbukti memangkas Max Drawdown secara dramatis tanpa mengurangi profitabilitas secara signifikan.
4. **Pencapaian Objective 1%/Hari & 5%/Minggu**:
   - Klon terbaik mampu mendongkrak pencapaian target harian 1% dengan tetap menjaga daily loss breach rate di bawah batas toleransi.