# Project Master Plan & Roadmap: LLMTradingV2

**Repository**: `https://github.com/arbuuuud/LLMTradingV2`  
**Status**: Active Development  
**Current Phase**: Fase Verifikasi Primitives (Eksplorasi 1 Per 1 POI, Structure, Patterns & Plan)  
**Single Source of Truth**: `PLAN.md` (Human Document) & `data/project_state.json` (Machine-readable Dashboard State)

---

## 📊 Ringkasan Progress Proyek

- **Total Tasks Terencana**: 34 tasks
- **Tasks Selesai**: 10 tasks (29.4%)
- **Tasks Sedang Berjalan**: 1 task (`POI-OB`)
- **Tasks Antrian**: 23 tasks

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

### 🔍 Fase Verifikasi: Eksplorasi 1 Per 1 POI, Structure, Patterns & Plan (Saat Ini)

#### A. POI (Points of Interest)
- [/] **POI-OB**: Order Block (OB) — Bullish & Bearish dengan tracking mitigasi harga. *(Sedang Dieksplorasi)*
- [ ] **POI-RBR-DBD**: Supply & Demand Continuation (Rally-Base-Rally & Drop-Base-Drop).
- [ ] **POI-FVG**: Fair Value Gap (FVG) — Deteksi celah harga 3-candle dan status mitigasi.
- [ ] **POI-IFVG**: Inversion Fair Value Gap (iFVG) — Pembalikan peran FVG yang ditembus body candle.
- [ ] **POI-BOS-CHOCH**: Break of Structure (BOS) & Change of Character (CHoCH).
- [ ] **POI-BB** *(Optional)*: Breaker Block (BB) — Order block yang gagal menahan harga setelah menyapu likuiditas.
- [ ] **POI-RBD-DBR** *(Optional)*: Supply & Demand Reversal (Rally-Base-Drop & Drop-Base-Rally).

#### B. Structure
- [ ] **STR-SWINGS**: Fractal Swing High & Swing Low points (window parametrik).
- [ ] **STR-HH-HL-LH-LL**: Klasifikasi urutan tren (Higher High, Higher Low, Lower High, Lower Low).

#### C. Fibonacci
- [ ] **FIB-RETRACEMENT**: Fibonacci Retracement (Equilibrium 50%, Golden Pocket OTE 0.618, 0.705, 0.786).
- [ ] **FIB-EXTENSION**: Fibonacci Extension (-0.272, -0.618, 1.272, 1.618 TP targets).

#### D. Candle Pattern
- [ ] **PAT-ENGULFING**: Bullish Engulfing & Bearish Engulfing.
- [ ] **PAT-DOJI**: Varian Doji (Standard, Dragonfly, Gravestone, Long-Legged).
- [ ] **PAT-STAR**: Formasi pembalikan 3-candle (Morning Star & Evening Star).
- [ ] **PAT-MOMENTUM**: Momentum / Displacement Candle (Marubozu ekspansi institusional).

#### E. Trading Plan
- [ ] **PLN-EQUILIBRIUM**: Equilibrium Area Mapping (Beli hanya di Discount <50%, Jual hanya di Premium >50%).

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
| **DEC-005** | 2025-09-22 | 1-by-1 POI & Structure Exploration Matrix | Seluruh POI (OB, RBR/DBD, FVG, iFVG, BOS/CHoCH, BB, RBD/DBR), Structure (Swings, HH/HL/LH/LL), Fibo (Retracement & Extension), Candle Patterns (Engulfing, Doji, Star, Momentum), dan Trading Plan (Equilibrium) dipecah menjadi sub-task individual dan diverifikasi satu per satu langsung di chart MT5. | **CONFIRMED** |
