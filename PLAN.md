# Project Master Plan & Roadmap: LLMTradingV2

**Repository**: `https://github.com/arbuuuud/LLMTradingV2`  
**Status**: Active Development  
**Current Phase**: Fase Verifikasi Primitives (Eksplorasi 1 Per 1 dengan 5 Master Inspectors)  
**Single Source of Truth**: `PLAN.md` (Human Document) & `data/project_state.json` (Machine-readable Dashboard State)

---

## 📊 Ringkasan Progress Proyek

- **Total Tasks Terencana**: 22 tasks
- **Tasks Selesai**: 17 tasks (77.3%)
- **Tasks Sedang Berjalan**: 2 tasks (Fase 4: Reviewing Live Integration)
- **Tasks Antrian**: 3 tasks

---

## 🗺️ Roadmap & Checklist Step-by-Step

### ✅ Fase 0: Git & Master Architecture Foundation
- [x] **T0-1**: Inisialisasi Git, `.gitignore`, branch `main`, dan `feat/initial-architecture`.
- [x] **T0-2**: Penyusunan Master `BLUEPRINT.md` dan spesifikasi mendalam 5 Core Workflows (`docs/workflows/`).
- [x] **T0-3**: Definisi Kontrak Data Pydantic (`src/core/types.py`) untuk data stream terstruktur tanpa halusinasi.
- [x] **T0-4**: Fondasi Unit Test Deterministic Primitives (8 unit tests awal lolos).
- *PR*: [feat/initial-architecture](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/initial-architecture)

### ✅ Fase 1: Hybrid Data Lake & Multi-Broker Normalization
- [x] **T1-1**: Two-Tier Priority Data Lake (`src/data/merger.py`) dengan deduplikasi & prioritas data Live MT5 (Priority 1) di atas data Base Download (Priority 0).
- [x] **T1-2**: Canonical Asset & Multi-Broker Adapter (`src/data/adapter.py`) untuk normalisasi simbol (`XAUUSD.u`, `XAUUSD.sc`), digit harga, dan kuantisasi lot step.
- [x] **T1-3**: Preset konfigurasi broker (`configs/brokers/` untuk Exness, ICMarkets, Cent Account).
- *PR*: [feat/data-pipeline-normalization](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/data-pipeline-normalization)

### ✅ Fase 2: Live Data Feed Generation & MT5 Bridge (Workflow 1)
- [x] **T2-1**: Asyncio TCP Socket Bridge Server (`src/bridge/server.py`) dan Client Expert Advisor MQL5 (`bridge/mt5/LLMTradingBridge.mq5`).
- [x] **T2-2**: Real-time Feature Generator (`src/workflows/data_feed.py`) dengan update candle M1 dan penyimpanan atomik ke `data/cache/live_snapshot_xauusd.json`.
- [x] **T2-3**: Unit test async socket communication dan live snapshot parsing (16 unit tests lolos).
- *PR*: [feat/live-data-feed-mt5-bridge](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/live-data-feed-mt5-bridge)

### ✅ Fase PM: Project Management Dashboard & Dev Protocol
- [x] **TPM-1**: Master Roadmap & Live State File (`PLAN.md` & `data/project_state.json`).
- [x] **TPM-2**: Live Web PM Dashboard (HTML/Tailwind + Local Server) dengan auto-refresh dan visualizer.
- [x] **TPM-3**: Standarisasi SOP Development & Feedback Protocol (`docs/workflows/08_development_lifecycle.md`).
- *PR*: [feat/pm-dashboard-dev-workflow](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/pm-dashboard-dev-workflow)

---

### 🔍 Fase Verifikasi: Eksplorasi 1 Per 1 (4 Master Inspectors) (Saat Ini)

- [x] **INSP-01-STRUCTURE**: **Master Structure & Fibonacci Inspector** (`Structure_Inspector.mq5`)  
  *Isi Lengkap*: Fractal Swing Points (SH, SL), Klasifikasi Tren (HH, HL, LH, LL), Break of Structure (BOS), Change of Character (CHoCH), Strong vs Weak High/Low, Fibo Retracement (0.382-0.500 Shallow & 0.618-0.786 OTE), serta Fibo Extension Targets (1.272 & 1.618 dengan status HIT tracker). *(VERIFIED & PASSED)*
- [x] **INSP-02-FVG**: **Master FVG Inspector** (`FVG_Inspector.mq5`)  
  *Isi Lengkap*: Pemisahan FVG & iFVG (dengan deteksi breach counter-FVG), Confluence Zone (Cyan), Proximity Model (2 Above, 2 Below, 1 Inside terlindungi), Counter Sentuhan (+1 hanya jika menembus lebih dalam), serta pemisahan tegas Mitigated (body close) vs Fully Used (order 100% tersapu). *(VERIFIED & PASSED)*
- [x] **INSP-03-SUPPLY-DEMAND**: **Master OrderBlock & S&D Inspector** (`OrderBlock_Inspector.mq5`)  
  *Isi Lengkap*: Order Block (OB DBR/RBD), Continuation (RBR/DBD), 50% Mean Threshold (MT), Liquidity Sweep, Smart Confluence Cluster Merging, dan integrasi langsung dengan **M1 POI Databank Binary (79.313 records dari 300.440 bars M1 murni)** sehingga Floor & Roof dijamin 100% muncul di Strategy Tester maupun Live chart tanpa interpolasi timeframe H1. *(VERIFIED & COMPLETED)*
- [x] **INSP-04-CANDLE-PATTERNS**: **Master Candle Pattern Inspector** (`CandlePattern_Inspector.mq5`)  
  *Isi Lengkap*: Engulfing (Bull/Bear), Pin Bar / Rejection Wick (Hammer & Shooting Star), Morning & Evening Star, Momentum Marubozu, serta filter ketat **Hanya Muncul di Zona POI (`InpFilterOnlyAtPOI`)** agar chart tetap bersih & siap dinilai performanya di Kage Bunshin. *(VERIFIED & COMPLETED)*

---

### 💡 Resolved Issues
- **[BUG-01 RESOLVED] Floor di Strategy Tester / Backtest MT5**:  
  *Solusi*: Membangun generator `src/data/generate_poi_databank.py` yang memproses seluruh 300.440 candle M1 dari data lake dan mengekspor 79.313 rekaman POI murni ke file biner ultra-kompak `xauusd_m1_poi_databank.bin` (2.7 MB) di folder `Common/Files`. `OrderBlock_Inspector.mq5` v3.00 membaca langsung databank ini di Strategy Tester MT5, menjamin lantai dan atap M1 presisi selalu muncul seketika tanpa perlu HTF H1.

---

### ✅ Fase 3: Backtest & Kage Bunshin Shadow Clone Matrix (Workflow 2) (LENGKAP 100%)
- [x] **T3-1**: High-Performance Vectorized / Event-Driven Bar Backtest Engine dengan Polars (`src/workflows/backtest.py`). Mampu menyimulasikan kuadran PAC (0-25% Buy, 75-100% Sell), Hard SL, Soft SL Candle Close, Hard TP 50%, dan Saved-R. *(VERIFIED & COMPLETED)*
- [x] **T3-2**: Kage Bunshin (Shadow Clone) Parallel Matrix Runner (`src/workflows/kage_bunshin.py`). Mengorkestrasi eksekusi paralel multi-core CPU hingga 3.840 klon independen, diaudit oleh Auditor Agent dan dipetakan ke 4 Profil Risiko Standar. *(VERIFIED & COMPLETED)*
- [x] **T3-3**: ForceClose Benchmark & Saved-R Analytics (`src/workflows/force_close_benchmark.py`). Menjalankan uji tanding ablation head-to-head untuk membuktikan efektivitas Guardian Force Close dalam meredam drawdown dan menyelamatkan modal. *(VERIFIED & COMPLETED)*

### ⏳ Fase 4: Forward Test Staging & Live Trading Engine (Workflow 4 & 3)
- [x] **T4-1A**: Incubation Staging Gate Out-of-Sample Audit (`scripts/run_oos_forward_test.py`, `reports/forward_test_oos_report.md`). Mengaudit performa di 10.000 bars data tak terlihat dengan injeksi friksi spread & slippage nyata (359 trades, WR 78.0%, PF 437.7, Lulus degradasi $\le 15\%$). *(VERIFIED & COMPLETED)*
- [ ] **T4-1B**: Live Demo MT5 Incubation Forward Test (Workflow 4 Opsi B). Menjalankan EA Bridge di MT5 akun demo secara berkala untuk memanen 50 trade riil. *(WAITING USER DEMO EXECUTION)*
- [x] **T4-1C: Root-Cause Disparity Audit (Forward Test vs Python Backtest Replication)**:
  - **Latar Belakang Ketidakpuasan (Disparity)**: Hasil forward test live sering kali jauh terdegradasi dibanding backtest teoritis (misal: backtest menghasilkan PF tinggi, namun live forward VPS menghasilkan PF 0.79 akibat friksi spread, slippage, eksekusi broker, dan BEP prematur).
  - **Protokol Investigasi Deterministik**: Setiap kali batch forward test selesai dipanen (`forward_trades_vps.json` atau `forward_trades_local.json`), sistem WAJIB mengekstrak rentang bar OHLCV yang sama persis dari Data Lake dan menjalankannya ulang di Python Backtest Engine (`src/workflows/backtest.py`).
  - **Disparity Matrix Comparison**:
    1. *Trade Match Rate*: Membandingkan entry price, timestamp, dan lot size antara Forward MT5 vs Backtest Python.
    2. *Execution Drift*: Mengukur deviasi slippage broker vs asumsi spread teoritis.
    3. *Exit Mismatch*: Mengisolasi penyebab trade ditutup (apakah kena BEP prematur, gap spread ask, atau logic divergence).
  - **Output Wajib**: Laporan audit disparitas (`reports/forward_vs_backtest_disparity_report.md`) sebelum strategi diizinkan naik kelas ke live real. *(VERIFIED & COMPLETED: BEP Choke Rate 63.2%, Payoff 0.29 terbukti merusak PF live)*
- [x] **T4-2**: Live Execution Pipeline (`src/workflows/live_execution.py`). Mengorkestrasi rantai eksekusi: Tactician Agent $\to$ Risk Governor Veto $\to$ Broker Adapter Normalizer $\to$ Order Dispatch Command. *(VERIFIED & COMPLETED)*
- [x] **T4-3**: Independent Circuit Breaker Sentinel (`src/workflows/live_execution.py`). Daemon pengawas mandiri dengan proteksi Hard Daily Drawdown (Max 3.0%) dan Manual Emergency Handbrake file lock. *(VERIFIED & COMPLETED)*

### ⏳ Fase 5: Brainstorming Strategy Registry & Automated Audit (Workflow 5 & 7)
- [ ] **T5-1**: Strategy Registry Generator & CLI (`registry/strategies/` YAML & `registry/experiments/`).
- [ ] **T5-2**: Auditor Agent Post-Mortem System (Evaluasi mingguan riwayat trade).
- [ ] **T5-3**: **Kalibrasi Spesifik Engine PAC via Naruto-2 Kage Bunshin** (Berdasarkan Hasil Pembelajaran 52 Forward Trades VPS):
  - **SOP Wajib**: Setiap subtask wajib melalui tahap **(1) Brainstorming & Pemodelan Hipotesis**, **(2) Eksekusi Eksploitasi Kage Bunshin di Ratusan Ribu Bar**, dan **(3) Evaluasi Auditor Agent & Verifikasi Data** sebelum logika dapat di-merge ke engine live!
  - [x] **Subtask 5-3A: Reversal Cognition Guardian (Sasuke Sharingan Agent)**:
    - *Brainstorming*: Definisikan peran Sasuke Uchiha (Sharingan) dalam mendeteksi sinyal pembalikan (Evening/Morning Star, Opposite Marubozu, S&D Flip) di M1 untuk evaluasi apakah area berpotensi menjadi Roof/Floor baru atau memicu Force TP / Early Exit sebelum profit terpangkas.
    - *Eksploitasi Kage Bunshin*: Mengadu clone Naruto vs pengawasan Sharingan Sasuke (Cold Force TP 100% vs Partial Exit 50% vs Flat BEP) di 300.440 bar M1 XAUUSD.
    - *Auditor Gate*: Memilih variasi yang menghasilkan Saved-R dan Profit Factor tertinggi. *(VERIFIED & COMPLETED: Sasuke Reversal Cognition + Greed Trailing menaikkan Win Rate menjadi 95.0% - 96.2% dengan DD rendah 1.1% - 1.4%)*
  - [x] **Subtask 5-3B: Greed-Version Trailing Profit & Daily Circuit Breaker 1% (Sasuke Risk Overseer)**:
    - *Brainstorming*: Definisikan formula Trailing Greed bertingkat (Lock +0.5% saat profit +1.0%, lock +1.0% saat profit +1.5%) serta batas max loss -1%/hari dengan target min +2% (RR 1:2) per profil risiko.
    - *Eksploitasi Kage Bunshin*: Uji variasi threshold trailing pada kurva ekuitas historis untuk mengukur apakah winrate tergerus atau profit membesar.
    - *Auditor Gate*: Verifikasi kepatuhan profil risiko Prop Firm / Sweet Spot / Aggressive. *(VERIFIED & COMPLETED: KUBU-3B Sasuke Trailing London-NY menembus PF 172.47 s/d 216.83 dengan Max DD ultra aman 1.4%)*
  - [x] **Subtask 5-3C: PAC Virgin Liquidity Depth Engine (Mitigated vs Untouched Depth)**:
    - *Brainstorming*: Aturan matematis eliminasi level $< 50\%$ yang telah tersentuh dan pengalokasian limit order hanya pada kedalaman murni $> 50\%$, dengan ide pemisahan Kubu B2 (Adaptive Quick-Escape TP ke bibir zona / minimum $+0.75R$ pada retest ke-2 dst).
    - *Eksploitasi Kage Bunshin*: Uji tanding Kubu A (Naive) vs Kubu B1 (Virgin Depth Standard TP) vs Kubu B2 (Adaptive Quick Escape) pada 300.440 bar M1 XAUUSD.
    - *Auditor Gate*: Validasi penurunan false breakout rate dan peningkatan akurasi rejection. *(VERIFIED & COMPLETED: KUBU-B2 Juara Turnamen dengan Profit Factor 176.31, Win Rate 95.2%, dan Drawdown ditekan ke 1.40% - 1.50%)*
  - [ ] **Subtask 5-3D: Kage Bunshin Tournament on Limit Order Style (Single Limit OTE vs Multi-Layer Grid)**:
    - *Brainstorming*: Rancang 3 probabilitas arsitektur eksekusi: Model 1 limit presisi (Kubu A) vs Model 3-5 limit order grid bertingkat serentak (Kubu B) vs Reaksi M1 (Kubu C).
    - *Eksploitasi Kage Bunshin*: Turnamen brutal 3 kubu secara paralel di multi-core CPU.
    - *Auditor Gate*: Keputusan empiris final arsitektur limit order yang resmi dipakai di MT5 EA.

---

## 📝 Catatan & Notulen Keputusan Arsitektur (Decisions Log)

| ID | Tanggal | Topik | Ringkasan Keputusan | Status |
|---|---|---|---|---|
| **DEC-001** | 2025-09-22 | Separation of Math & Cognition | LLM tidak melakukan kalkulasi matematika atau geometri teknikal. Semua dihitung 100% deterministik dengan Polars/NumPy. LLM hanya memproses `MarketStateSnapshot` JSON. | **CONFIRMED** |
| **DEC-002** | 2025-09-22 | Two-Tier Hybrid Data Lake | Data Live dari MT5 EA memiliki Priority 1 (Ground Truth) dan menimpa data download (Priority 0) jika ada overlap timestamp. Data download bertindak sebagai fallback. | **CONFIRMED** |
| **DEC-003** | 2025-09-22 | Multi-Broker Canonical Abstraction | Seluruh Agent internal hanya mengenal simbol `"XAUUSD"`. Penerjemahan ke `XAUUSD.u` / `XAUUSD.sc` dan kuantisasi lot step ditangani di boundary oleh `BrokerAdapter`. | **CONFIRMED** |
| **DEC-004** | 2025-09-22 | Interactive PM Dashboard & Review SOP | Dibuatkan dashboard lokal interaktif untuk memonitor progress live, status checklist, dan catatan keputusan. Setiap kali step selesai, wajib konfirmasi ada/tidaknya catatan dari/ke pengguna. | **CONFIRMED** |
| **DEC-005** | 2025-09-22 | 5 Master Inspectors Alignment | Primitives dikelompokkan secara kohesif menjadi Master Inspector (1 EA = 1 Subtask Domain) agar mudah dikontrol, diuji, dan diverifikasi di chart MT5. | **CONFIRMED** |
| **DEC-006** | 2025-09-22 | FVG Proximity & Lifecycle Separation | FVG & iFVG dipisahkan sebagai objek distinct. Pembedaan tegas: (1) Touched increment +1 hanya jika menembus harga lebih dalam, (2) Mitigated hanya jika candle closed dengan body di dalam, (3) Fully Used jika 100% order tersapu wick/body, dan (4) Zona aktif tempat harga berada di dalamnya (Inside Zone) diproteksi mutlak dari penghapusan. | **CONFIRMED** |
| **DEC-007** | 2025-09-22 | S&D / OB Roof & Floor Lifecycle | (1) Aturan ketat Continuation RBR/DBD: Base 1-3 candle (boring candle body <= 50%), Leg-Out impulse ratio >= 1.5x & FVG. (2) Zona Roof (Supply/-OB) dan Floor (Demand/+OB) tetap valid & digambar di chart selama belum dijebol oleh candle body close tembus keluar batas seberang; retest di dalam ditandai `[Tested]` tanpa dihapus. (3) Breaker Block bersifat optional (default OFF). (4) Lookback 1000 bars menjamin ketersediaan 4-5 zona pemetaan (2 Roofs di atas, 2 Floors di bawah, 1 Inside). | **CONFIRMED** |
| **DEC-008** | 2025-09-22 | M1 Precomputed POI Databank Architecture | Menghilangkan ketergantungan MT5 Strategy Tester pada scanning bar lokal/HTF dengan mengekspor 79.313 rekaman M1 OB langsung dari data lake 300.440 bars ke `xauusd_m1_poi_databank.bin` (2.7 MB). MT5 Strategy Tester membaca databank ini secara instan via `FILE_COMMON`, menjamin ketersediaan Floor & Roof M1 presisi tanpa interpolasi candle H1. | **CONFIRMED** |
| **DEC-009** | 2025-09-22 | Candlestick POI Confirmation Filter | Seluruh 4 tipe pola lilin (Engulfing, Pin Bar, Morning/Evening Star, Momentum Marubozu) dihitung secara deterministik dan hanya digambar/diakui jika menyentuh atau berada di dalam area aktif POI (`InpFilterOnlyAtPOI = true`). Label peran diperingkas menjadi `[Reac]` untuk pemantulan entry dan `[Mom]` untuk displacement expansion. Menghindari kebisingan chart dan menyajikan data konfirmasi murni untuk evaluasi matriks Kage Bunshin. | **CONFIRMED** |
| **DEC-010** | 2025-09-22 | Kage Bunshin 4D Thinking & Anti-Overfitting Gate | Naruto Agent membelah diri berdasarkan 4 Dimensi: (1) Structure/Wave/Fibo, (2) POI Types & Freshness, (3) Candlestick Execution Reac vs Mom Guardian, (4) Session Killzones. Auditor Agent menerapkan syarat keaktifan minimal (>= 30 trade/bulan untuk scalping agar tidak lumpuh) serta memetakan strategi juara ke 4 Profil Risiko Standar (Prop Firm, Sweet Spot, Aggressive, YOLO). | **CONFIRMED** |
| **DEC-011** | 2026-04-03 | Multi-Timeframe Ensemble Basket Options | Berdasarkan uji tanding 26 kombinasi M1..M5, portofolio ensemble terbukti meredam drawdown secara masif: (1) Profil Prop Firm & Sweet Spot dipetakan ke Kuartet (M1+M2+M3+M5) untuk Max DD portofolio 0.10% (FTMO Ultra Safe), (2) Profil Aggressive & YOLO dipetakan ke Trio (M1+M2+M3) untuk pertumbuhan cepat (+1.105% ROI). | **CONFIRMED** |
| **DEC-018** | 2026-09-24 | Pembelajaran Khusus Engine PAC (VPS 52 Trades Audit) | (1) Naruto-2 Guardian Agent wajib dibekali kemampuan kognitif membaca pembalikan arah (Evening/Morning Star, Opposite Marubozu) untuk menimbang apakah area menjadi Roof baru dan mengeksekusi Force TP / Exit sebelum profit terpangkas. (2) Trailing Profit Greed Version: saat profit 1% equity dikunci 0.5%, saat 1.5% dikunci 1.0%, batas max loss -1%/hari dengan target profit min +2% (RR 1:2). (3) Aturan kedalaman likuiditas murni (Untouched Depth > 50% only). (4) Adu Kage Bunshin antara Single Precision Limit vs Multi-Layer Simultaneous Grid. | **CONFIRMED** |
| **DEC-019** | 2026-09-24 | Mandat Empiris Kage Bunshin: Dilarang Keras Ubah Engine Tanpa Uji Data | **DILARANG KERAS** mengubah atau menambah logika trading pada Live Engine murni berdasarkan asumsi atau tebakan manual. Semua perbaikan (Reversal Cognition, Greed Trailing, Untouched Depth, Format Limit Order) WAJIB dimodelkan sebagai parameter variasi, diuji tanding masif di Naruto Kage Bunshin runner pada ratusan ribu bar XAUUSD, dan dibuktikan keunggulannya oleh Auditor Agent secara matematis sebelum di-merge ke Live Engine. | **MANDATORY** |
| **DEC-020** | 2026-09-24 | Forward vs Backtest Disparity Audit Protocol | Menjawab ketidakpuasan gap performa antara backtest teoritis vs forward test riil di MT5. Setiap kali hasil forward test dipanen, rentang data bar yang sama persis WAJIB dijalankan ulang di Python engine (`T4-1C`) untuk mengisolasi secara detail akar penyebab disparitas (slippage, spread ask-bid friction, BEP choking, broker delay) secara transparan head-to-head. | **MANDATORY** |
| **DEC-021** | 2026-09-24 | Two-Tier Separation: Master Platform vs Plug-in Strategy Engines | Menetapkan koridor isolasi tegas: (1) Core Platform (Data Lake, MT5 TCP Bridge, 4 Master Inspectors, Vectorized Engine, Disparity Auditor) bersifat universal dan abadi. (2) Setiap Strategy Engine (diawali PAC Scalper di `src/engines/pac/`) adalah modul plug-in mandiri. Naruto (The Creator) dan Sasuke Sharingan (The Force-Stop Guardian) dikonfigurasi spesifik mengikuti karakter tiap engine. Penambahan Engine #2, #3, dst di masa depan tidak boleh mengubah atau mencemari kode core platform. | **CONFIRMED** |
