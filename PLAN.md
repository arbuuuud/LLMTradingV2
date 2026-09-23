# Project Master Plan & Roadmap: LLMTradingV2

**Repository**: `https://github.com/arbuuuud/LLMTradingV2`  
**Status**: Active Development  
**Current Phase**: Fase Verifikasi Primitives (Eksplorasi 1 Per 1 dengan 5 Master Inspectors)  
**Single Source of Truth**: `PLAN.md` (Human Document) & `data/project_state.json` (Machine-readable Dashboard State)

---

## 📊 Ringkasan Progress Proyek

- **Total Tasks Terencana**: 22 tasks
- **Tasks Selesai**: 14 tasks (63.6%)
- **Tasks Sedang Berjalan**: 0 task
- **Tasks Antrian**: 8 tasks

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

### ⏳ Fase 3: Backtest & Kage Bunshin Shadow Clone Matrix (Workflow 2)
- [ ] **T3-1**: High-Performance Vectorized / Event-Driven Bar Backtest Engine dengan Polars.
- [ ] **T3-2**: Kage Bunshin (Shadow Clone) Parallel Matrix Runner.
- [ ] **T3-3**: ForceClose Benchmark & Saved-R Analytics.

### ⏳ Fase 4: Forward Test Staging & Live Trading Engine (Workflow 4 & 3)
- [ ] **T4-1**: Incubation Staging Gate (Demo / Paper Trading Validator 50 trades).
- [ ] **T4-2**: Live Execution Pipeline (Tactician Agent $\to$ Risk Governor Veto $\to$ MT5 Bridge $\to$ ForceClose Guardian).
- [ ] **T4-3**: Independent Circuit Breaker Sentinel (Daemon kill switch Max Daily Drawdown 3%).

### ⏳ Fase 5: Brainstorming Strategy Registry & Automated Audit (Workflow 5 & 7)
- [ ] **T5-1**: Strategy Registry Generator & CLI (`registry/strategies/` YAML & `registry/experiments/`).
- [ ] **T5-2**: Auditor Agent Post-Mortem System (Evaluasi mingguan riwayat trade).

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
| **DEC-009** | 2025-09-22 | Candlestick POI Confirmation Filter | Seluruh 4 tipe pola lilin (Engulfing, Pin Bar, Morning/Evening Star, Momentum Marubozu) dihitung secara deterministik dan hanya digambar/diakui jika menyentuh atau berada di dalam area aktif POI (`InpFilterOnlyAtPOI = true`). Menghindari kebisingan chart dan menyajikan data konfirmasi murni untuk evaluasi matriks Kage Bunshin. | **CONFIRMED** |
