# RUNBOOK: Production Operations & Diagnostics Protocol
**LLMTradingV2 Institutional Live Ops Standard Operating Procedure (SOP)**

Dokumen ini adalah **panduan rujukan resmi (Single Source of Truth)** bagi Operator maupun AI Coding Assistant (dalam sesi baru atau pasca context compaction) ketika diminta untuk:
- *"Tolong check production"*
- *"Bagaimana kondisi akun / floating sekarang?"*
- *"Tolong download dan audit data forward test VPS"*

---

## 🌐 1. Konfigurasi Endpoint Server Production (VPS)

- **Host IP**: `http://103.59.160.228`
- **Dashboard Web Port**: `8080` (`http://103.59.160.228:8080/`)
- **Bridge TCP Socket Port**: `5555` (Internal communication antara MT5 EA $\leftrightarrow$ Python Brain)
- **Akun Fleet Aktif (4 Akun)**:
  1. `ACC-113137266` $\to$ **Prop Firm ($100K)** | Risk 0.25% per trade (~0.11L - 0.43L)
  2. `ACC-113137116` $\to$ **Sweet Spot ($10K)** | Risk 0.50% per trade (~0.02L - 0.08L)
  3. `ACC-5056446504` $\to$ **Aggressive ($3K)** | Risk 1.00% per trade (~0.01L - 0.05L)
  4. `ACC-5056446633` $\to$ **YOLO ($500)** | Risk 2.00% per trade (0.01L)

---

## 🕵️‍♂️ 2. Secret Internal Diagnostic Endpoints (AI Inspection APIs)

AI Coding Assistant **WAJIB** menggunakan endpoint-endpoint berikut saat diminta melakukan audit / pengecekan production:

### A. Live Brain Execution Logs (Streaming Log)
- **URL**: `http://103.59.160.228:8080/api/internal/bridge-logs?tail=60`
- **Fungsi**: Membaca streaming log dari `logs/bridge.log` di VPS.
- **Isi Data**:
  - Deteksi koneksi MT5 (`MT5 EA Client connected`).
  - Sinyal PAC M1 (`BAR SYNC`, `Latest Close`).
  - Perintah kirim order (`⚡ [MULTI-ACCOUNT GRID DISPATCH]`).
  - Status sesi (`🏁 [SESSION TRANSITION] ASIAN Active`).
  - Proteksi risiko (`🛑 [SESSION CIRCUIT BREAKER]`).

### B. Live Open Positions & Pending Orders (Floating Monitor)
- **URL**: `http://103.59.160.228:8080/api/internal/live-positions`
- **Fungsi**: Menginspeksi posisi yang sedang floating dan limit order yang sedang menunggu di-fill.
- **Isi Data**:
  - `open_positions`: Tiket, simbol, arah (BUY/SELL), lot, harga masuk, harga saat ini, SL, TP, profit ($).
  - `pending_orders`: Tiket, tipe (BUY_LIMIT / SELL_LIMIT), harga limit, SL, TP, lot per akun.
  - `accounts`: Live balance dan live equity masing-masing akun.

### C. Direct Raw Telemetry Download
- **URL**: `http://103.59.160.228:8080/api/internal/download-vps-trades`
- **Fungsi**: Mengunduh file mentah `forward_trades_vps.json` langsung dari VPS ke mesin lokal untuk audit disparitas, benchmarking, atau verifikasi performa.

### D. Radar Cockpit State
- **URL**: `http://103.59.160.228:8080/api/radar`
- **Fungsi**: Memeriksa harga mid XAUUSD, status kuadran PAC M1-M5, dan status `session_budget`.

---

## 🛠️ 3. SOP Cek Produksi Cepat (Quick Diagnostic Flow)

Ketika pengguna bertanya *"Tolong check production"*, langkah otomatis yang dijalankan:

1. **Tarik Log Terkini**:
   ```bash
   curl -s "http://103.59.160.228:8080/api/internal/bridge-logs?tail=30"
   ```
   *Pastikan bridge aktif dan menerima tick dari MT5 tanpa crash.*

2. **Periksa Posisi & Order Menggantung**:
   ```bash
   curl -s "http://103.59.160.228:8080/api/internal/live-positions"
   ```
   *Laporkan apakah ada posisi floating atau 3-layer grid limit orders yang sedang aktif.*

3. **Periksa Status Sesi & Health Radar**:
   ```bash
   curl -s "http://103.59.160.228:8080/api/radar"
   ```
   *Laporkan sesi aktif (Asian / London / NY), status budget (Active vs Halted), dan harga emas saat ini.*
