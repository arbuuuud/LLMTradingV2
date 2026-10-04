# 🔬 Laporan Audit Disparitas Komprehensif: Live Production MT5 vs Backtest Engine
**Dataset Diekstrak**: 889 Closed Deals dari Production VPS (`http://103.59.160.228:8080`)  
**Periode Live**: 25 September 2026 s/d 02 Oktober 2026 (7 Hari Trading Nyata)  
**Metodologi**: Head-to-Head Replikasi Backtest Kage Bunshin vs Telemetri Riil 5 Akun Fleet  
**Mandat Keputusan**: DEC-019 (Empirical Mandate) & DEC-020 (Forward vs Backtest Disparity Protocol)

---

## 1. Papan Komparasi Utama: Harapan Backtest vs Fakta Production

| Metrik Evaluasi | Target Kage Bunshin Backtest | Realized Live Production (VPS) | Status Disparitas & Gap |
|---|:---:|:---:|:---:|
| **Sample Trades** | 56,000+ Baris | **889 Trades (127 Gelombang)** | ✅ Sampel Sangat Cukup & Signifikan |
| **Win Rate (Signal Level)** | **96.5%** | **56.7%** (72W / 55L) | 🔴 **Drop -39.8%** |
| **Win Rate (Sub-Trades)** | **95.2%** | **49.4%** (439W / 450L) | 🔴 **Drop -45.8%** |
| **Profit Factor (PF)** | **136.17 s/d 269.66** | **0.58** | 🔴 **Degradasi Kritis** |
| **Net Realized PnL** | Stabil Bertumbuh | **-$5,386.25** | 🔴 Mengalami Drawdown Nyata |
| **Payoff Ratio (W/L)** | **> 1.50** | **0.59** (Avg Win $16.81 vs Loss $28.36) | 🔴 Asimetri Negatif |
| **Average Trade Duration** | 2.5 s/d 6.0 Menit | **5.4 Menit** (Median 3.4 Menit) | ✅ Replikasi Timing Selaras |

---

## 2. Rincian Performa 5 Akun Fleet di Production

| No | Nomor Akun | Profil Risiko | Total Trade | Win Rate | Gross Profit | Gross Loss | Net Realized PnL | Rata-rata Lot |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **#113137116** | **Sweet Spot ($10K)** | 245 | **52.7%** | +$1,220.76 | -$1,611.52 | **-$390.76** | 0.04 Lot |
| 2 | **#5056446504** | **Aggressive ($3K)** | 233 | **51.1%** | +$583.53 | -$826.00 | **-$242.47** | 0.02 Lot |
| 3 | **#5056446633** | **YOLO ($500)** | 146 | **54.1%** | +$169.28 | -$255.30 | **-$86.02** | 0.01 Lot |
| 4 | **#33848251** | **Sweet Spot Cent (PU Prime)** | 36 | **27.8%** | +$18.50 | -$334.53 | **-$316.03** | 0.03 Lot |
| 5 | **#113137266** | **Prop Firm ($100K)** | 229 | **44.5%** | +$5,385.72 | -$9,736.69 | **-$4,350.97** | 0.22 Lot |
| **TOTAL** | **FLEET COMBINED** | **5 ACCOUNTS** | **889** | **49.4%** | **+$7,377.79** | **-$12,764.04** | **-$5,386.25** | — |

---

## 3. Otopsi 3 Akar Masalah Utama (Root Causes Disparity)

Melalui audit mendalam per tiket transaksi dan rekonstruksi pergerakan harga:

### 🔴 1. Fenomena "Layer 3 Breakout Trap" (Penyumbang 66.6% Kerugian)
Dalam simulasi backtest teoritis, ketika harga menyentuh Layer 3 di dasar diskon (0%), model mengasumsikan harga memantul kembali ke Equilibrium 50% sehingga bobot 50% lot di Layer 3 memberikan keuntungan berlipat.
**Namun data riil di production membuktikan kebalikannya**:
- Saat harga hanya menjemput **1 Layer** (L1 Bibir): Menang 21x, Kalah 2x (**Win Rate 91.3%**, Net PnL **+$798.71**).
- Saat harga menjemput **2 Layer** (L1 + L2): Menang 13x, Kalah 3x (**Win Rate 81.2%**, Net PnL **+$1,352.36**).
- **SAAT HARGA TEMBUS MENJEMPUT LAYER 3**: Menang 19x, Kalah 39x (**Win Rate HANCUR ke 32.8%**, Net PnL **-$6,502.04**)!
> **Fakta Lapangan**: Di pasar nyata, ketika harga menembus sampai ke Layer 3 (Dasar 0%), 67.2% kasusnya **BUKANLAH RETEST, MELAINKAN BREAKOUT TEMBUS LEVEL**. Menaruh bobot lot terbesar (50%) di titik yang paling dekat dengan jurang Stop Loss terbukti menjadi sumber utama kehancuran akun!

### 🔴 2. Disparitas Directional: BUY (-$4,401.95) vs SELL (-$984.30)
- Posisi **SELL** mencatatkan Win Rate **57.0%** (290 Menang / 219 Kalah).
- Posisi **BUY** terpuruk di Win Rate **39.2%** (149 Menang / 231 Kalah) dan menelan kerugian bersih **-$4,401.95** (81.7% total rugi)!
> **Penyebab**: Selama periode 25 September – 02 Oktober, harga emas mengalami gelombang *flash dump* berulang kali dari $4316 turun ke $4135. Tanpa filter rem anti-pisau jatuh (*falling knife*), sistem terus-menerus membeli di zona diskon yang sedang dibantai oleh seller institusi.

### 🔴 3. Asimetri Payoff Ratio (Avg Win $16.81 vs Avg Loss $28.36)
- Rata-rata pergerakan saat Win adalah **$2.35 poin**.
- Rata-rata pergerakan saat Stop Loss adalah **$3.77 poin**.
- Sistem sering menutup posisi saat retrace kecil menyentuh bibir (Quick Escape) menghasilkan laba moderat, namun saat tren lawan menerjang, 3 layer tersapu penuh di SL. Payoff ratio 0.59 menuntut Win Rate minimal 63% hanya untuk sekadar impas (BEP).

