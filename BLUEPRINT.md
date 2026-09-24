# Master Architecture Blueprint: LLMTradingV2

**Status**: Active Specification (SSOT)  
**Target Asset**: XAUUSD (Gold Spot), Cross-pairs & FX Majors  
**Execution Target**: MetaTrader 5 (Raw Spread ECN) / Institutional Fix API  
**Engine Stack**: Python 3.11+, Polars, PyArrow, DuckDB, Pydantic, NumPy  

---

## 1. Filosofi & Prinsip Desain V2

Sistem generasi pertama (**V1**) mengalami *complexity overload* karena mencampuradukkan perhitungan kuantitatif berbasis bar/tick dengan layer reasoning LLM. 

Di **V2**, kami menerapkan aturan arsitektur mutlak:
1. **"Never Ask an LLM to Calculate Math"**:
   - Deteksi FVG, Order Block, Swing High/Low, Fibonacci retracement, Breakeven, dan Risk/Reward dihitung **100% secara deterministik** menggunakan library berkecepatan tinggi (Polars/NumPy).
   - LLM hanya menerima data matang berbentuk `MarketStateSnapshot` (JSON terstruktur) untuk melakukan evaluasi kualitatif, sintesis checklist, dan penyesuaian strategi adaptif.
2. **"Stateless Feature Extractors, Stateful Risk Governance"**:
   - Modul deteksi teknikal bersifat murni fungsi matematika tanpa side-effects.
   - Manajemen risiko bersifat stateful dan independen dengan hak veto mutlak terhadap keputusan agent.
3. **"Strict Empirical Mandate: Zero Logic Mutation Without Kage Bunshin Exploitation" (MANDATORY)**:
   - **DILARANG KERAS** mengubah atau menambahkan logika trading di engine (`src/bridge/`, `src/features/`, `src/workflows/`, atau EA) hanya berdasarkan tebakan subjektif, asumsi, atau instruksi ad-hoc tanpa melalui proses eksplorasi empiris kuantitatif **Naruto Kage Bunshin**.
   - Setiap ide atau perubahan logika (sinyal pembalikan, trailing profit, filter kedalaman likuiditas, maupun format limit order) wajib diperlakukan sebagai **Hipotesis Eksperimen** yang diadu secara brutal (*ablation showdown*) di ribuan/ratusan ribu candle historis M1 XAUUSD.
   - Hanya konfigurasi atau mutasi yang **terbukti unggul secara data** (Sharpe Ratio, Profit Factor, dan Drawdown terverifikasi oleh Auditor Agent) yang memiliki hak dipromosikan ke Engine Live!
4. **"Shadow Clone Exploration (Kage Bunshin)"**:
   - Eksplorasi strategi tidak dilakukan manual satu per satu, melainkan di-kloning secara otomatis menjadi puluhan hingga ribuan variasi parameter matriks untuk menemukan checklist paling tangguh (*robust*) terhadap noise pasar.

---

## 2. Definisi Data Schema Standar (`src/core/types.py`)

Kunci keterpisahan sistem adalah kontrak data yang ketat via Pydantic:

### 2.1. `MarketStateSnapshot`
Dihasilkan oleh **W1 (Live Data Feed)** dan dikonsumsi oleh seluruh agent:
- `timestamp`: UTC ISO datetime.
- `symbol`: e.g. "XAUUSD".
- `htf_trend`: `BULLISH` | `BEARISH` | `RANGING`.
- `current_price`: `{ bid, ask, spread }`.
- `structure`:
  - `last_swing_high`: `{ price, timestamp, confirmed }`.
  - `last_swing_low`: `{ price, timestamp, confirmed }`.
  - `last_event`: `BOS_BULLISH` | `BOS_BEARISH` | `CHOCH_BULLISH` | `CHOCH_BEARISH` | `NONE`.
- `pois` (Points of Interest):
  - List of `OrderBlock` (`type: BULLISH|BEARISH`, `top`, `bottom`, `mitigated: bool`).
  - List of `FVG` (`type: BULLISH|BEARISH`, `top`, `bottom`, `inversion: bool`, `tested_count`).
- `fibonacci_ote`:
  - `anchor_high`, `anchor_low`, `level_618`, `level_705`, `level_786`, `in_ote_zone: bool`.
- `liquidity`:
  - `buy_side_swept: bool`, `sell_side_swept: bool`, `equal_highs: float`, `equal_lows: float`.

### 2.2. `ChecklistEvaluation`
Dihasilkan oleh **Tactician Agent**:
- `strategy_id`: ID checklist yang dievaluasi.
- `direction`: `BUY` | `SELL` | `WAIT`.
- `total_score`: 0.0 sampai 10.0.
- `passed`: Boolean (apakah melampaui `min_threshold`).
- `criteria_breakdown`: Key-value pairs dari tiap kriteria checklist dan status pemenuhannya.
- `confidence_rationale`: Ringkasan penalaran LLM mengapa setup ini valid atau ditolak.

### 2.3. `ForceCloseTrigger`
Dihasilkan oleh **Guardian Agent (ForceClose)**:
- `position_id`: Tiket posisi yang dipantau.
- `action`: `HOLD` | `MOVE_SL_BE` | `PARTIAL_CLOSE` | `FORCE_CLOSE_MARKET`.
- `reason`:
  - `STRUCTURAL_INVALIDATION`: iFVG ditembus ke arah berlawanan, atau muncul counter CHoCH.
  - `MOMENTUM_EXHAUSTION`: Muncul volume klimaks berlawanan atau stall berkepanjangan di area bahaya.
  - `TIME_DECAY`: Posisi tertahan melewati limit candle maksimum tanpa pergerakan impulsif.
  - `NEWS_FRONT_RUN`: Terdeteksi rilis berita berimpak tinggi dalam kurun waktu $\le$ 5 menit.

---

## 3. Detail 5 Core Workflows

### 3.1. Workflow 1: Live Data Feed Generation (Feature Engine)
- **Tujuan**: Mengubah raw ticks dan bar M1/M5/M15 dari MT5 menjadi `MarketStateSnapshot` real-time.
- **Mekanisme**:
  1. Engine membaca bar terbaru secara event-driven (setiap new candle close atau per-N ticks).
  2. Modul `src/features/` memindai Swing Point, BOS/CHoCH, FVG/iFVG, dan Order Block.
  3. Memvalidasi status mitigasi dari POI sebelumnya.
  4. Menerbitkan snapshot ke message bus / shared memory / disk cache untuk dikonsumsi agent.

### 3.2. Workflow 2: Backtest & Shadow Clone Testing (Kage Bunshin)
- **Tujuan**: Pengujian brutal strategi berbasis data historis masif (tick & bar Parquet).
- **Mekanisme Shadow Cloning (Kage Bunshin)**:
  1. Ambil 1 Base Strategy Checklist (misal: *Trend Pullback Scalper*).
  2. Spawn $N$ variasi mutasi:
     - Mutasi A: Bobot FVG lebih besar dari OB.
     - Mutasi B: Wajib ada Liquidity Sweep sebelum entry vs tanpa sweep.
     - Mutasi C: Fibonacci OTE entry (0.618 vs 0.705).
     - Mutasi D: Dynamic ForceClose vs Fixed SL/TP.
  3. Eksekusi semua variasi secara paralel menggunakan Vectorized Polars Backtester.
  4. **ForceClose Agent Benchmark**: Mengukur performa jika posisi di-exit saat structural invalidation vs membiarkan mengenai Stop Loss awal. (Menghitung *Saved R*).
  5. Output: Tabel ranking variasi terbaik berdasarkan Sharpe, Profit Factor, Max Drawdown, dan Calmar Ratio.

### 3.3. Workflow 3: Live Trading Workflow
- **Tujuan**: Eksekusi live pada akun riil dengan disiplin institusional tanpa emosi.
- **Pipeline Eksekusi**:
  1. **Listener**: Menangkap `MarketStateSnapshot` terbaru dari W1.
  2. **Tactician (Checklist Scorer)**: Mengevaluasi apakah ada setup yang lolos kriteria skor.
  3. **Risk Governor (The Law)**: Memverifikasi saldo, margin, batas risiko harian (-3%), dan menghitung ukuran lot presisi. Memiliki hak VETO mutlak.
  4. **Execution Bridge**: Mengirimkan limit/market order ke MT5.
  5. **Guardian (ForceClose Sentinel)**: Begitu order terisi (*FILLED*), Guardian aktif memantau tick-by-tick hingga trade selesai.

### 3.4. Workflow 4: Forward Test Workflow (Incubation Staging)
- **Tujuan**: Menjembatani hasil backtest W2 ke live W3 melalui simulasi live tanpa risiko modal riil.
- **Aturan Promosi (Graduation Gate)**:
  - Strategi harus aktif di akun Demo/Paper minimal 30 hari atau 50 trade.
  - Winrate, Max Drawdown, dan Slippage tidak boleh menyimpang lebih dari 15% dari ekspektasi backtest.
  - Jika lulus, status strategi diubah menjadi `LIVE_APPROVED`.

### 3.5. Workflow 5: Brainstorming & Research Registry
- **Tujuan**: Mencatat seluruh siklus hidup ide strategi agar tidak ada inovasi yang hilang atau terulang secara sia-sia.
- **Struktur Dokumen**:
  - `registry/strategies/STRAT-XXX.yaml`: Berisi definisi checklist, rule entry/exit, dan versi.
  - `registry/experiments/EXP-XXX.md`: Berisi hipotesis, dataset yang diuji, hasil shadow cloning, kesimpulan, dan link ke commit code terkait.

---

## 4. Tiga Support Workflows Tambahan

- **W0: Historical Data Ingestion & Sanitization**: Mengunduh tick dan bar MT5, membuang weekend gaps / bad ticks, konversi ke Parquet terkompresi ZSTD.
- **W6: Independent Circuit Breaker**: Daemon independen (watchdog) yang memonitor equity drawdown. Jika daily loss > 3%, paksa tutup semua posisi (*kill switch*) dan cabut otorisasi execution bridge.
- **W7: Post-Mortem & Retrospective**: Scheduler mingguan yang mengekstrak semua trade logs, meminta Auditor Agent menganalisis kesalahan eksekusi vs variasi market, lalu memperbarui memo perbaikan.

---

## 5. Matriks Peran Agent (Single Responsibility Principle)

| Agent | Scope | Input | Output | Sifat |
|---|---|---|---|---|
| **Researcher Agent** | Riset & Brainstorming | Log pasar, ide baru | Definisi hipotesis & variasi matriks Kage Bunshin | Proaktif / Batch |
| **Tactician Agent** | Entry Evaluation | `MarketStateSnapshot` | `ChecklistEvaluation` (Score & Reason) | Event-Driven (Per Bar) |
| **Risk Governor** | Guardrail & Sizing | Signal, Portfolio State | `ApprovedOrder` atau `VETO_REJECT` | Deterministic Gatekeeper |
| **ForceClose Guardian**| Active Position Watch | Open Positions + Bar/Ticks | `ForceCloseTrigger` (Exit / BE / Hold) | Real-time Stream |
| **Auditor Agent** | Post-Mortem Review | Closed Trades History | Research Memo & Rule Tuning Notes | Scheduled (EOD/EOW) |
