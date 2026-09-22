# Project Master Plan & Roadmap: LLMTradingV2

**Repository**: `https://github.com/arbuuuud/LLMTradingV2`  
**Status**: Active Development  
**Current Phase**: Phase PM (Project Management Dashboard & Dev Protocol)  
**Single Source of Truth**: `PLAN.md` (Human Document) & `data/project_state.json` (Machine-readable Dashboard State)

---

## 📊 Ringkasan Progress Proyek

- **Total Tasks Terencana**: 16 tasks
- **Tasks Selesai**: 7 tasks (43.75%)
- **Tasks Sedang Berjalan**: 3 tasks (Fase PM)
- **Tasks Antrian**: 6 tasks

---

## 🗺️ Roadmap & Checklist Step-by-Step

### ✅ Fase 0: Git & Master Architecture Foundation
- [x] **T0-1**: Inisialisasi Git, `.gitignore`, branch `main`, dan `feat/initial-architecture`.
- [x] **T0-2**: Penyusunan Master `BLUEPRINT.md` dan spesifikasi mendalam 5 Core Workflows (`docs/workflows/`).
- [x] **T0-3**: Definisi Kontrak Data Pydantic (`src/core/types.py`) untuk data stream terstruktur tanpa halusinasi.
- [x] **T0-4**: Modul kalkulator deterministik dasar (SMC, Structure, OTE, Checklist, ForceClose) + 8 Pytest unit tests.
- *PR*: [feat/initial-architecture](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/initial-architecture)

### ✅ Fase 1: Hybrid Data Lake & Multi-Broker Normalization
- [x] **T1-1**: Two-Tier Priority Data Lake (`src/data/merger.py`) dengan mekanisme deduplikasi & prioritas data Live MT5 (Priority 1) di atas data Base Download (Priority 0).
- [x] **T1-2**: Canonical Asset & Multi-Broker Adapter (`src/data/adapter.py`) untuk normalisasi simbol (`XAUUSD.u`, `XAUUSD.sc`), digit harga, dan kuantisasi lot step.
- [x] **T1-3**: Preset konfigurasi broker (`configs/brokers/` untuk Exness, ICMarkets, Cent Account) + 6 unit tests.
- *PR*: [feat/data-pipeline-normalization](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/data-pipeline-normalization)

### ✅ Fase 2: Live Data Feed Generation & MT5 Bridge (Workflow 1)
- [x] **T2-1**: Asyncio TCP Socket Bridge Server (`src/bridge/server.py`) dan Client Expert Advisor MQL5 (`bridge/mt5/LLMTradingBridge.mq5`).
- [x] **T2-2**: Real-time Feature Generator (`src/workflows/data_feed.py`) dengan update candle M1 dan penyimpanan atomik ke `data/cache/live_snapshot_xauusd.json`.
- [x] **T2-3**: Unit test async socket communication dan live snapshot parsing (total 16 unit tests lolos).
- *PR*: [feat/live-data-feed-mt5-bridge](https://github.com/arbuuuud/LLMTradingV2/pull/new/feat/live-data-feed-mt5-bridge)

### 🔄 Fase PM: Project Management Dashboard & Development Protocol (Saat Ini)
- [x] **TPM-1**: Penyusunan `PLAN.md` dan `data/project_state.json` sebagai SSOT pelacakan live status.
- [x] **TPM-2**: Pembuatan Live Web Project Management Dashboard (UI modern dengan checklist interaktif, progress tracker, decision log, dan live snapshot viewer).
- [x] **TPM-3**: Standarisasi SOP Development & Feedback Protocol (`docs/workflows/08_development_lifecycle.md`).
- *Branch Aktif*: `feat/pm-dashboard-dev-workflow`

### ⏳ Fase 3: Backtest & Kage Bunshin Shadow Clone Matrix (Workflow 2)
- [ ] **T3-1**: High-Performance Vectorized / Event-Driven Bar Backtest Engine dengan Polars.
- [ ] **T3-2**: Kage Bunshin (Shadow Clone) Parallel Matrix Runner (eksplorasi ratusan mutasi checklist secara paralel).
- [ ] **T3-3**: ForceClose Benchmark & Saved-R Analytics (analisis kuantitatif pemotongan kerugian dini vs Fixed SL).

### ⏳ Fase 4: Forward Test Staging & Live Trading Engine (Workflow 4 & 3)
- [ ] **T4-1**: Incubation Staging Gate (Demo / Paper Trading Validator dengan syarat minimum 50 trades dan toleransi slippage).
- [ ] **T4-2**: Live Execution Pipeline (Tactician Agent $\to$ Risk Governor Veto $\to$ MT5 Bridge $\to$ ForceClose Guardian).
- [ ] **T4-3**: Independent Circuit Breaker Sentinel (Daemon kill switch dengan batas Max Daily Drawdown 3%).

### ⏳ Fase 5: Brainstorming Strategy Registry & Automated Audit (Workflow 5 & 7)
- [ ] **T5-1**: Strategy Registry Generator & CLI (`registry/strategies/` YAML dan `registry/experiments/` Markdown).
- [ ] **T5-2**: Auditor Agent Post-Mortem System (Evaluasi mingguan riwayat trade dan perbaikan bobot checklist).

---

## 📝 Catatan & Notulen Keputusan Arsitektur (Decisions Log)

Setiap keputusan yang disepakati dengan pengguna dicatat di sini secara kronologis:

| ID | Tanggal | Topik | Ringkasan Keputusan | Status |
|---|---|---|---|---|
| **DEC-001** | 2025-09-22 | Separation of Math & Cognition | LLM tidak melakukan kalkulasi matematika atau geometri teknikal. Semua dihitung 100% deterministik dengan Polars/NumPy. LLM hanya memproses `MarketStateSnapshot` JSON. | **CONFIRMED** |
| **DEC-002** | 2025-09-22 | Two-Tier Hybrid Data Lake | Data Live dari MT5 EA memiliki Priority 1 (Ground Truth) dan menimpa data download (Priority 0) jika ada overlap timestamp. Data download bertindak sebagai fallback. | **CONFIRMED** |
| **DEC-003** | 2025-09-22 | Multi-Broker Canonical Abstraction | Seluruh Agent internal hanya mengenal simbol `"XAUUSD"`. Penerjemahan ke `XAUUSD.u` / `XAUUSD.sc` dan kuantisasi lot step ditangani di boundary oleh `BrokerAdapter`. | **CONFIRMED** |
| **DEC-004** | 2025-09-22 | Interactive PM Dashboard & Review SOP | Dibuatkan dashboard lokal interaktif untuk memonitor progress live, status checklist, dan catatan keputusan. Setiap kali step selesai, wajib konfirmasi ada/tidaknya catatan dari/ke pengguna. | **CONFIRMED** |

---

## 🔄 Development & Feedback Workflow Protocol

Setelah setiap task/step selesai dikerjakan, jalankan alur kerja berikut:
1. **Verifikasi Teknis**: Pastikan kode baru memiliki unit test dan seluruh test lulus (`pytest tests/`).
2. **Update Status State**: Update `data/project_state.json` dan `PLAN.md` (tandai task terkait sebagai selesai / checkmark).
3. **Konfirmasi Catatan & Feedback**:
   - Tanyakan ke pengguna: *"Apakah ada catatan / penyesuaian untuk step ini?"*
   - Jika ada usulan catatan baru dari asisten atau pengguna, konfirmasikan untuk dicatat ke tabel *Decisions Log*.
4. **Git Protocol**: Commit ke branch `feat/` yang sedang aktif, push ke remote, dan sediakan tautan Pull Request.
