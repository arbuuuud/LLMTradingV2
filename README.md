# LLMTradingV2: Decoupled Institutional Quantitative AI System

Sistem trading kuantitatif generasi kedua (**V2**) yang dirancang dengan memisahkan secara tegas antara **Deterministic High-Performance Computation** (Polars, NumPy, DuckDB) dan **LLM Cognitive Reasoning** (Tactician, Risk Governor, Guardian, Auditor).

Arsitektur ini dibangun ulang dari nol untuk menghilangkan kompleksitas berlebih pada versi sebelumnya, dengan fokus utama pada **5 Core Workflows** dan sistem pengujian mutasi strategi otomatis (**Naruto Shadow Clone / Kage Bunshin Testing**).

---

## 🏛️ Filosofi Arsitektur V2: "Separation of Math & Cognition"

1. **Deterministic Layer (Zero LLM, Zero Hallucination, Sub-millisecond)**:
   - Kalkulasi geometri market: Swing High/Low, BOS, CHoCH, Order Block (OB), Fair Value Gap (FVG), Inversion FVG (iFVG), OTE Fibonacci (0.618 - 0.786), Liquidity Sweeps.
   - Eksekusi backtest vector/event-driven berbasis Polars.
   - Hard circuit breaker & risk sizing enforcement.
2. **Cognitive Layer (LLM Structured Decision Making)**:
   - Evaluasi checklist kompleks & pembobotan confidence score.
   - Dynamic trailing & ForceClose structural invalidation analysis.
   - Automated hypothesis generation & ablation matrix (Shadow Cloning).
   - Post-mortem auditing & continuous playbook refinement.

---

## 🔄 5 Core Workflows + 3 Support Workflows

```text
                  [W0: Data Ingestion & Sanitization (Parquet)]
                                      │
                                      ▼
                      [W5: Brainstorming & Playbook Registry]
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
  [W2: Brutal Backtest]                            [W1: Live Data Feed]
  - Shadow Clone (Kage Bunshin)                    - 100% Deterministic Engine
  - Checklist Calibration                          - POI, Structure, Fibo, Patterns
  - ForceClose Stress Testing                      - MarketStateSnapshot Generator
               │                                             │
               ▼                                             │
  [W4: Forward Test (Incubator/Paper)]                       │
  - Live Validation Without Risk                             │
  - KPI Verification (Sharpe, Drawdown)                      │
               │                                             │
               └──────────────────────┬──────────────────────┘
                                      │
                                      ▼
                      [W3: Live Trading Execution]
                      - Checklist Evaluator (Tactician)
                      - Risk Governor (The Law / Handbrake)
                      - ForceClose Guardian (Dynamic Exit)
                                      │
                                      ▼
                      [W7: Post-Mortem & Audit Workflow]
```

### 1. W1: Live Data Feed Generation
Menghasilkan state data terstandarisasi (`MarketStateSnapshot` JSON) secara real-time dari data feed MT5/Broker. Mengkalkulasi POI (OB, FVG, iFVG), Struktur (Swing High/Low, BOS, CHoCH), Fibonacci OTE, dan pola rejection tanpa intervensi LLM.

### 2. W2: Backtest Workflow (Kage Bunshin Testing)
Pengujian brutal berbasis tick/bar menggunakan metode kloning strategi paralel (*Shadow Cloning*). Menguji ratusan kombinasi filter checklist dan mengevaluasi efektivitas *ForceClose Agent* saat kondisi pasar berbalik ekstrem.

### 3. W3: Live Trading Workflow
Alur kerja eksekusi modal riil. Menerapkan pengawasan berlapis:
`Data Feed Snapshot` $\to$ `Tactician Checklist Scoring` $\to$ `Risk Governor Approval/Veto` $\to$ `Execution Bridge` $\to$ `Guardian ForceClose Watcher`.

### 4. W4: Forward Test Workflow
Lingkungan *staging* (Paper / Demo Account). Setiap strategi/engine hasil optimasi backtest wajib lulus masa inkubasi forward test sebelum diizinkan mengelola modal riil.

### 5. W5: Brainstorming & Research Workflow
Manajemen ide dan eksperimen terstruktur. Setiap hipotesis, perubahan parameter, dan hasil uji tercatat rapi di `registry/` agar siklus riset terdokumentasi dan tidak terjadi regresi.

### Support Workflows
- **W0: Historical Data Ingestion & Sanitization** (Download, clean bad ticks, compress Parquet).
- **W6: Independent Circuit Breaker / Handbrake** (Pemutus sirkuit darurat di thread independen).
- **W7: Post-Mortem & Retrospective** (Audit otomatis performa dan jurnal harian).

---

## 🗂️ Struktur Direktori

```text
LLMTradingV2/
├── README.md                          # Dokumentasi overview proyek
├── BLUEPRINT.md                       # Single Source of Truth arsitektur sistem
├── requirements.txt                   # Dependensi Python
├── pyproject.toml                     # Konfigurasi packaging & toolchain
├── configs/                           # Konfigurasi aset & limit risiko
│   ├── assets/xauusd.yaml             # Spesifikasi instrumen XAUUSD
│   └── risk_limits.yaml               # Threshold circuit breaker & drawdowns
├── docs/                              # Dokumentasi mendalam tiap workflow & agent
│   ├── workflows/                     # Spesifikasi 5 Core Workflows + Support
│   └── agents/                        # Spesifikasi peran agent (Tactician, Guardian, Governor)
├── src/
│   ├── core/                          # Tipe data standar (Pydantic) & konstanta
│   ├── features/                      # Kalkulator teknikal murni (SMC, Structure, Fibo)
│   ├── engine/                        # Backtest engine, Checklist scoring, Shadow Clone
│   ├── bridge/                        # Konektor MetaTrader 5
│   ├── agents/                        # Cognitive agent interfaces
│   └── workflows/                     # Runner scripts untuk tiap workflow
├── data/                              # Penyimpanan data (raw, parquet, cache)
├── registry/                          # Katalog strategi & log eksperimen (Brainstorming)
└── tests/                             # Unit tests untuk memastikan integritas logika
```

---

## 🚀 Panduan Memulai

1. Buat virtual environment & install dependensi:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Jalankan test unit untuk verifikasi kalkulator deterministik:
   ```bash
   pytest tests/
   ```

Lihat detail lengkap spesifikasi teknis di **[BLUEPRINT.md](./BLUEPRINT.md)**.
